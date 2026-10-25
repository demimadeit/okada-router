#!/usr/bin/env bash
# Run Okada + the Cloud console on this machine with no Docker and no keys
# needed (mock providers; add real keys to .env to use them).
#
#   ./scripts/run_local.sh          # starts on http://localhost:8080
#   ./scripts/run_local.sh 8090     # another port
#
# Console: http://localhost:<port>/console    Demo chat: http://localhost:<port>/app
set -euo pipefail
PORT="${1:-8080}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null; then echo "python3 is required (3.11+)"; exit 1; fi
if [ ! -x .venv/bin/python ]; then
  echo "• creating virtualenv"; python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.lock
mkdir -p logs

if [ -f .env ]; then echo "• using keys from .env"; else
  echo "• no .env: cloud roles run on mock providers (routing still real)."
  echo "  add keys with:  ./scripts/add_key.sh GROQ_API_KEY gsk_..."
fi

# optional local model: any llama-server on 8081 / 9931 / 8080 is auto-detected
if command -v llama-server >/dev/null && ! curl -s -m 1 localhost:8081/health >/dev/null; then
  echo "• llama-server found but not running; start it in another terminal for the offline rung:"
  echo "    llama-server -hf Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M --port 8081 -c 4096"
fi

export OKADA_ADMIN_TOKEN="${OKADA_ADMIN_TOKEN:-local-admin}"
echo "• gateway  http://localhost:$PORT/v1"
echo "• console  http://localhost:$PORT/console   (create an account there)"
echo "• admin token: $OKADA_ADMIN_TOKEN"
exec .venv/bin/uvicorn gateway.server:app --host 127.0.0.1 --port "$PORT"
