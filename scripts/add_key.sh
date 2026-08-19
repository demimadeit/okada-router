#!/usr/bin/env bash
# Install a cloud provider key on the local gateway and (optionally) the droplet.
#
#   ./scripts/add_key.sh GROQ_API_KEY gsk_xxx            # local only
#   ./scripts/add_key.sh GROQ_API_KEY gsk_xxx --droplet  # local + droplet
#
# Keys go into .env (gitignored) — never into the repo.
set -euo pipefail

VAR="${1:?usage: add_key.sh <ENV_VAR_NAME> <key> [--droplet]}"
KEY="${2:?missing key}"
REMOTE="${3:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

touch "$ROOT/.env"
# replace any existing line for this var, then append the new one
grep -v "^${VAR}=" "$ROOT/.env" > "$ROOT/.env.tmp" 2>/dev/null || true
mv "$ROOT/.env.tmp" "$ROOT/.env"
echo "${VAR}=${KEY}" >> "$ROOT/.env"
echo "local: ${VAR} installed in .env"

if [ -f "$ROOT/.venv/bin/uvicorn" ]; then
  pkill -f "uvicorn gateway.server" 2>/dev/null || true
  sleep 1
  (cd "$ROOT" && nohup .venv/bin/uvicorn gateway.server:app --port 8080 > logs/server.log 2>&1 &)
  sleep 4
  echo "local gateway restarted; mock_mode now: $(curl -s -m 5 localhost:8080/okada/health | python3 -c 'import json,sys; print(json.load(sys.stdin)["mock_mode"])' 2>/dev/null || echo '?')"
fi

if [ "$REMOTE" = "--droplet" ]; then
  ssh -i ~/.ssh/tla_droplet_ed25519 -o BatchMode=yes root@165.22.124.9 "
    F=/home/deploy/okada-router/.env
    grep -v '^${VAR}=' \$F > \$F.tmp 2>/dev/null || true; mv \$F.tmp \$F
    echo '${VAR}=${KEY}' >> \$F
    chown deploy:deploy \$F && systemctl restart okada && sleep 4
    curl -s -m 5 localhost:8090/okada/health | head -c 120"
  echo
  echo "droplet: ${VAR} installed, okada restarted"
fi
