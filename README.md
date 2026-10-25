# Okada Router

**An AI resilience gateway for networks you can't trust.**

Most AI applications assume `app → stable internet → cloud API → response`. In Lagos — and on ships, farms, mines, and rural roads everywhere — that assumption fails daily. The NCC counted 27,000+ fibre cuts in Nigeria in Jan–Nov 2025 and 5,000+ more in the first half of 2026; the best mobile network delivers "consistent quality" in only 18.5% of Opensignal's July 2026 tests; 36% of active lines are still on 2G; and 82.5% of Nigerian firms told the 2025 World Bank Enterprise Survey they face frequent power outages. Okada Router sits between the application and the model providers and always finds a way through:

```
                        ┌──────────────────────────────┐
  app (OpenAI SDK) ───▶ │        Okada Gateway         │
  base_url = okada      │  cache ─ routing engine      │
                        └──────┬───────────┬───────────┘
                          network OK   network bad/none
                               │           │
                     cloud-large/small   local GGUF model (llama.cpp)
                     alternate provider  offline queue → sync
```

Routing is driven by **network conditions** (latency, packet loss, offline), not just provider cost — that is the difference from OpenRouter/LiteLLM/Portkey, which route on provider-side signals and fail when *your* link dies.

## The degraded-mode ladder

| Condition | Route |
|---|---|
| healthy | primary cloud model |
| degraded (>600ms / >5% loss) | smaller cloud model **with a response cap** (the cap, not the model swap, is what cuts bytes) |
| primary provider failing, or its model **retired** | alternate provider |
| repeat question | exact cache (per tenant) |
| severe (>2.5s / >25% loss) or offline | local quantized GGUF model via llama.cpp (Ollama as optional fallback) |
| a streamed answer dies mid-sentence | next rung continues from the partial text; the client sees one answer |
| offline + no local model | durable queue; auto-replayed on reconnect **and after a restart** |

Every request returns an `okada` block (route, reason, network state, fallback/retry counts, `request_id`) and writes one JSONL telemetry line — the seed of the routing dataset.

## Quickstart — Docker (one command)

```bash
GROQ_API_KEY=gsk_your_key docker compose up
```

That starts the gateway *and* a local llama.cpp model. Open
<http://localhost:8080> for the demo app, or point any OpenAI client at
`http://localhost:8080/v1`. The model downloads once into a volume; after
that the offline route works with no internet at all. Any of
`GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
`OPENROUTER_API_KEY` works — the first one found becomes the primary cloud,
the second becomes automatic failover. Set `OKADA_API_KEY` to require auth on
a public deployment, and `OKADA_QUEUE_KEY` to encrypt the offline queue at rest.

The llama.cpp image and every Python dependency are **pinned** (`docker-compose.yml`,
`requirements.lock`). Bump them on purpose and test; the LiteLLM 1.107.0 supply-chain
incident of 24 Oct 2026 is why a floating tag is not an option for a gateway that
holds provider keys.

Optional, unverified upgrade to Qwen3.5 with speculative decoding:
`docker compose -f docker-compose.yml -f docker-compose.qwen35.yml up` (read the file first).

## Quickstart — from source

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.lock
# local model (recommended): llama-server from llama.cpp, any GGUF
llama-server -hf Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M --port 8081 -c 4096 &
.venv/bin/uvicorn gateway.server:app --port 8080
```

llama-server's own default port moved from 8080 to **9931** in llama.cpp v0.7.0
(Oct 2026), and 8080 is the gateway's port. Pass `--port 8081` as above, or
leave the default: the gateway tries the configured URL, then 9931, then 8080,
and logs which one answered. Ollama (`ollama pull qwen2.5:0.5b`) still works as
a fallback local backend if no llama-server is found.

Point any OpenAI client at it:

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8080/v1", api_key="okada")
client.chat.completions.create(model="auto", messages=[{"role": "user", "content": "hello"}])
```

With no API keys set, cloud roles bind to a **clearly-labelled mock provider** (still subject to the simulated network) so routing behaviour is fully exercisable. Export any provider key to use real providers — no code changes.

### Demo & network simulation

```bash
.venv/bin/python demo/chat.py          # terminal chat; /network 3g, /network offline, /stats
curl -X POST localhost:8080/okada/network -H 'content-type: application/json' \
     -d '{"profile": "offline"}'       # profiles: excellent 4g 3g edge high-latency packet-loss intermittent offline real
```

Simulation is application-level (latency, loss and outages injected into outbound cloud calls) — deterministic, cross-platform, runtime-switchable. Profile `real` switches to continuous probes of real endpoints, one per configured provider.

### Benchmark & tests

```bash
.venv/bin/python -m pytest tests/ -q       # 46 tests
.venv/bin/python scripts/benchmark.py      # direct cloud vs Okada, per network profile
.venv/bin/python scripts/check_models.py --complete   # are the configured model IDs still alive?
```

`x-okada-mode: direct` header bypasses all resilience (single attempt, no cache, no fallback) — that is the "naive app" baseline the benchmark compares against. Network conditions are simulated; cloud and local inference are real when keys are set. Measured result (Groq gpt-oss-120b/20b + local Qwen GGUF, 8 requests × 7 profiles, 56 requests): **direct 69.6% answered vs Okada 100%**; offline 0% vs 100%. That is engineering evidence from a small run, not a market statistic.

## Models rot: path health is not model health

Groq retired its Llama 3.x free-tier models on 16 Aug 2026 and `qwen3.6-27b` on 14 Sep 2026, each with about a month's notice. A `GET /models` probe stays green while every completion returns 404. So the gateway:

- probes each cloud **path** (network/health.py) *and* each configured **model** with a real one-token completion every `model_probe_interval_s` (default 5 min);
- classifies upstream errors: 404/410/"decommissioned" marks the *model* gone (the provider is fine, the rung is skipped, the next successful probe re-enables it); 429 moves down the ladder without retrying the same free tier; anything else counts against provider health.

`GET /okada/health` shows `model_ok` per route; `POST /okada/probe/models` runs the probe now.

## Okada Cloud console

Open `/console` on any running gateway. It is the product surface on top of the
gateway: create an account, get a tenant and a key, watch what the gateway is
doing for you, and try it without writing code.

- **Accounts and tenants.** One account owns many tenants (one per app or
  customer); each tenant has its own keys, budget, cache namespace and routing
  flags. Keys are shown once and stored hashed. Signup creates a first tenant
  and key so the dashboard is never empty. `OKADA_SIGNUP=0` makes it invite-only.
- **Overview.** Requests by route over time, answered rate, p50 latency, the
  network as the gateway saw it (offline bands), spend versus list price, and a
  recent-requests table with the routing reason for each. No prompt text is
  ever stored or shown.
- **Playground.** Chat as the tenant through the console session (no raw key
  needed), see each rung the router tries, thumbs-up/down labels go straight
  into the routing dataset. On a mock-provider gateway any user can flip the
  simulated network; on a live one that needs `OKADA_ADMIN_TOKEN`.
- **Setup.** curl / Python / JavaScript snippets with the right base URL.
- **Admin.** `GET /console/api/admin/overview` with header `x-okada-admin`.

Accounts live in `logs/accounts.sqlite` (`OKADA_ACCOUNTS_DB` to move it). The
gateway is open (no auth) only until the first key exists anywhere — in the
environment, in `OKADA_KEYS_FILE`, or created in the console.

## Tenants, virtual keys, budgets

- No keys configured → open gateway (local dev), one tenant `default`.
- `OKADA_API_KEY` → one bearer key, as before.
- `OKADA_KEYS_FILE=config/keys.yaml` → one virtual key per tenant with `max_budget_usd` (daily/monthly/total), `models_allowed`, `degraded_max_tokens`, `no_offshore` (cache/local/queue only — prompts never leave the box), and optional per-tenant `upstream_keys`. See `config/keys.example.yaml`.
- `x-okada-upstream-key` header: bring-your-own provider key for a single call.
- `x-okada-idempotency-key` header: a client retry after reconnecting gets the same queue id back instead of running twice.
- Cache keys are namespaced by tenant. Budgets are enforced against `est_cost_usd`, which is zero for providers listed in `OKADA_FREE_TIER_PROVIDERS` (default in compose: `groq,gemini,openrouter`); `list_cost_usd` always carries list price so savings can be reported honestly.

## Telemetry and the routing dataset

Each request writes one line to `logs/telemetry.jsonl` with the network state, decision, every attempt (route, provider, model, ms, error class), final route, bytes, tokens, `list_cost_usd` / `est_cost_usd`, tenant, and — new — `prompt_sha256` / `last_user_sha256` (hashes, never text), `prompt_chars`, a stopword-heuristic `lang` tag (en/pcm/yo/ha/ig/sw/fr), `reask_of` (implicit negative: same user re-asked the same thing within 60 s) and `quality` (explicit via `POST /okada/feedback {request_id, rating: up|down}`). That is the minimum a learned routing policy or a local-model fine-tune would need; nothing leaves the machine.

## Running alongside other services

If the server also hosts someone else's production workload, cap Okada so the
local model cannot starve its neighbours:

```bash
docker compose -f docker-compose.yml -f docker-compose.shared-host.yml up -d
```

For a systemd install, the equivalent is a drop-in at
`/etc/systemd/system/okada.service.d/limits.conf`:

```ini
[Service]
MemoryMax=512M
CPUQuota=50%
Nice=10
```

llama.cpp will use every core it is given, so an uncapped local model on a
shared box is the one genuine risk this project poses to co-tenants.

## Endpoints

| | |
|---|---|
| `POST /v1/chat/completions` | OpenAI-compatible; `stream: true` relays provider tokens as they arrive, with mid-stream failover |
| `GET /v1/models` | configured routes, with `model_ok` |
| `GET/POST /okada/network` | read / switch network profile (`real` = live probes) |
| `GET /okada/stats` | telemetry summary (answered rate, p50/p95, routes, langs, per-tenant spend) |
| `POST /okada/feedback` | `{request_id, rating: up\|down, comment?}` quality label |
| `GET /okada/queue`, `GET /okada/queue/{id}` | offline queue status / queued result |
| `GET /okada/health` | provider path health, model liveness, probe results |
| `POST /okada/probe/models` | run the real-completion model probe now |
| `GET /okada/tenant` | who am I, what is my budget window spend |
| `/console`, `/console/api/*` | Okada Cloud console and its API (accounts, tenants, keys, stats, playground) |

## Honest limitations

Done: bearer auth and virtual keys with budgets, real network sensing (per-provider path probes), real model probes, multi-provider failover, true streaming relay with mid-stream continuation, durable encrypted offline queue with restart replay and idempotency, pinned dependencies and image, Docker install.

Still missing before this is production infrastructure:

- Cache is exact-match with no PII scrubbing; semantic caching needs a CPU embedding model, a per-workload threshold study and a cache-poisoning threat model first.
- Encryption at rest covers the queue only when `OKADA_QUEUE_KEY` is set; telemetry holds hashes, not text, but is unencrypted. Single process, no per-tenant rate limiting.
- No mobile SDK yet, so end-user phones cannot use the offline route — only machines running Okada themselves can.
- No WhatsApp/SMS channel for delivering queued answers to feature phones.
- Local-language quality is unmeasured: a 1.5B model is English-and-Swahili class; Hausa/Yoruba/Igbo need 3–4B and an evaluation set that does not exist yet.
- A gateway cannot fix a dead radio link or an unpowered tower. It can only survive them (local model, queue-and-sync). That is the honest scope of the product.

## Repository

```
gateway/    server (FastAPI), routing engine, model probe, telemetry, queue, tenants, accounts, config
providers/  openai-compatible (OpenAI/Groq/Gemini/OpenRouter), anthropic, llama.cpp, ollama, mock
network/    health monitor (path probes), condition simulator
cache/      exact-match TTL cache, tenant-namespaced
tests/      routing-policy unit tests + end-to-end gateway and console tests (46)
app/        demo chat app (/app) and the Okada Cloud console (/console)
demo/       terminal chat client
scripts/    resilience benchmark, model-ID checker, local-model measurement, key installer
docs/       whitepaper, Oct 2026 roadmap and the research behind it
adtc/       ADTC 2026 submission materials (the challenge concluded 19 Oct 2026)
```

*Okada: the Lagos motorbike taxi that gets through when the road is blocked.*
