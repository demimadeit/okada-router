# Okada Router

**An AI resilience gateway for networks you can't trust.**

Most AI applications assume `app → stable internet → cloud API → response`. In Lagos — and on ships, farms, mines, and rural roads everywhere — that assumption fails daily: Nigeria logged 27,000+ fibre cuts in 2025 and ~190 days/year of grid downtime. Okada Router sits between the application and the model providers and always finds a way through:

```
                        ┌──────────────────────────────┐
  app (OpenAI SDK) ───▶ │        Okada Gateway         │
  base_url = okada      │  cache ─ routing engine      │
                        └──────┬───────────┬───────────┘
                          network OK   network bad/none
                               │           │
                     cloud-large/small   local model (Ollama)
                     alternate provider  offline queue → sync
```

Routing is driven by **network conditions** (latency, packet loss, offline), not just provider cost — that is the difference from OpenRouter/LiteLLM/Portkey, which route on provider-side signals and fail when *your* link dies.

## The degraded-mode ladder

| Network state | Route |
|---|---|
| healthy | primary cloud model |
| degraded (>600ms / >5% loss) | smaller cloud model |
| primary provider failing | alternate provider |
| repeat question | exact cache (semantic cache: week 2) |
| severe (>2.5s / >25% loss) or offline | local quantized model (qwen2.5:0.5b via Ollama) |
| offline + no local model | queue; auto-replayed on reconnect |

Every request returns an `okada` block (route, reason, network state, fallback/retry counts) and writes one JSONL telemetry line — the seed of the routing dataset.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# optional but recommended (local fallback):
brew install ollama && ollama serve & ollama pull qwen2.5:0.5b
.venv/bin/uvicorn gateway.server:app --port 8080
```

Point any OpenAI client at it:

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8080/v1", api_key="okada")
client.chat.completions.create(model="auto", messages=[{"role": "user", "content": "hello"}])
```

With no API keys set, cloud roles bind to a **clearly-labelled mock provider** (still subject to the simulated network) so routing behaviour is fully exercisable. Export `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` to use real providers — no code changes.

### Demo & network simulation

```bash
.venv/bin/python demo/chat.py          # terminal chat; /network 3g, /network offline, /stats
curl -X POST localhost:8080/okada/network -H 'content-type: application/json' \
     -d '{"profile": "offline"}'       # profiles: excellent 4g 3g edge high-latency packet-loss intermittent offline
```

Week-1 simulation is application-level (latency, loss and outages injected into outbound cloud calls) — deterministic, cross-platform, runtime-switchable. OS-level shaping (Toxiproxy/netem) is planned for realism testing.

### Benchmark & tests

```bash
.venv/bin/python -m pytest tests/ -q       # 19 tests
.venv/bin/python scripts/benchmark.py      # direct cloud vs Okada, per network profile
```

`x-okada-mode: direct` header bypasses all resilience (single attempt, no cache, no fallback) — that is the "naive app" baseline the benchmark compares against. Benchmark results are synthetic (simulated network, mock cloud unless keys are set) and are labelled as such.

## Endpoints

| | |
|---|---|
| `POST /v1/chat/completions` | OpenAI-compatible (incl. `stream: true` via SSE) |
| `GET /v1/models` | configured routes |
| `GET/POST /okada/network` | read / switch simulated network profile |
| `GET /okada/stats` | telemetry summary (answered rate, p50/p95, routes) |
| `GET /okada/queue`, `GET /okada/queue/{id}` | offline queue status / queued result |
| `GET /okada/health` | provider/route health |

## Honest limitations (week 1)

- Cache is exact-match, single-tenant, no PII handling — not multi-tenant safe yet.
- Streaming is wrap-of-complete-response, not true incremental relay.
- Network sensing is simulated or single-probe; no passive RTT/loss estimation yet.
- No auth, no encryption-at-rest for queue/telemetry, single process.
- A gateway cannot fix a dead radio link or a powered-off tower — it can only survive them (local model, queue-and-sync). That is the honest scope of the product.

## Repository

```
gateway/    server (FastAPI), routing engine, telemetry, queue, config
providers/  openai, anthropic, ollama (local), mock
network/    health monitor, condition simulator
cache/      exact-match TTL cache
tests/      routing-policy unit tests + end-to-end gateway tests
demo/       terminal chat client
scripts/    resilience benchmark
```

*Okada: the Lagos motorbike taxi that gets through when the road is blocked.*
