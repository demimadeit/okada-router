# Deploying Okada Cloud on a VPS (OVHcloud or any Ubuntu box)

Two sizes. Pick by whether the box should also run the **on-device model**
(the offline rung) or only the gateway + console.

| Profile | What runs | RAM | vCPU | Disk | OVH tier (check current names/prices) |
|---|---|---|---|---|---|
| **Gateway only** | FastAPI gateway, console, SQLite, routing to cloud providers; offline rung lives on customers' own boxes | 2 GB | 1 | 20 GB | smallest VPS |
| **Gateway + local model** | the above plus llama.cpp serving Qwen2.5-1.5B Q4 (~1 GB file, ~2 GB RAM at 4K context) | 4 GB | 2 | 40 GB | one tier up |

Disk actually used: Python image ~250 MB, llama.cpp CPU image ~200 MB, model
1 GB (1.5B) or 2.4 GB (3B), Docker overhead ~1 GB, logs and SQLite grow slowly
(telemetry is ~1 KB per request, so 1 GB is a million requests). 20 GB is
comfortable for gateway-only; 40 GB leaves room to try a 3B–4B model.

Start with **gateway only**. The product people sign up to is the console and
the resilient cloud routing; the local-model rung is the thing you run on a
shop's own hardware, not on the VPS. Add the model later with one compose flag.

## 1. Server

Ubuntu 24.04, root or a sudo user. Point a DNS A record (e.g. `okada.yourdomain.com`)
at the VPS IP before step 4 so HTTPS can issue.

```bash
apt update && apt install -y docker.io docker-compose-v2 git caddy
systemctl enable --now docker
```

## 2. Code and secrets

```bash
git clone https://github.com/demimadeit/okada-router /opt/okada && cd /opt/okada
cat > .env <<'ENV'
GROQ_API_KEY=gsk_...                 # any of GROQ/GEMINI/OPENROUTER/OPENAI/ANTHROPIC; first found = primary
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
OKADA_ADMIN_TOKEN=$(openssl rand -hex 24)   # paste the generated value, keep it private
OKADA_QUEUE_KEY=$(openssl rand -hex 32)     # encrypts queued prompts at rest
OKADA_SIGNUP=1                               # 0 = invite-only
OKADA_FREE_TIER_PROVIDERS=groq,gemini,openrouter
ENV
chmod 600 .env
```

(Run the two `openssl rand` commands yourself and paste the outputs; `.env`
does not expand `$(...)`.)

## 3. Run

Gateway only (recommended first):

```bash
docker compose up -d --no-deps --build gateway
```

Gateway + local model (4 GB box):

```bash
docker compose up -d --build
```

Check: `curl -s localhost:8080/okada/health | head -c 300`. Data lives in the
`okada-logs` volume (accounts, queue, telemetry) and survives restarts and
rebuilds.

## 4. HTTPS

```bash
sed "s/okada.example.com/okada.yourdomain.com/" deploy/Caddyfile > /etc/caddy/Caddyfile
systemctl reload caddy
```

Open `https://okada.yourdomain.com/console`, create your account, and send the
link to the first tester. Your own key for curl/SDK tests comes from the Keys tab.

## 5. Keep it healthy

```bash
docker compose logs -f gateway                 # live log
docker compose pull && docker compose up -d    # only after bumping pinned tags on purpose
.venv/bin/python scripts/check_models.py --complete   # after any provider deprecation email
```

Back up the volume occasionally: `docker run --rm -v okada-router_okada-logs:/d -v $PWD:/b alpine tar czf /b/okada-backup.tgz /d`.

## Cost control

Groq, Gemini and OpenRouter free tiers are per-org daily limits; the gateway
rotates down the ladder on 429s. Set a daily budget per tenant in the console
so one tester cannot exhaust the pooled keys. Nothing else on the VPS costs
money: no managed database, no GPU.
