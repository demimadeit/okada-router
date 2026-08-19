#!/usr/bin/env bash
# ADTC target-machine setup: Ubuntu 22.04, 8GB RAM, i5, no GPU, then OFFLINE.
# Everything below downloads once; after that the whole stack runs with the
# network cable pulled out.
set -euo pipefail

# 1. build llama.cpp (CPU)
if ! command -v llama-server >/dev/null; then
  sudo apt-get update && sudo apt-get install -y build-essential cmake git python3-venv
  git clone --depth 1 https://github.com/ggml-org/llama.cpp
  cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release
  cmake --build llama.cpp/build --target llama-server -j"$(nproc)"
  sudo cp llama.cpp/build/bin/llama-server /usr/local/bin/
fi

# 2. fetch GGUF weights (one-time, ~2.4GB; fits the 8GB budget at Q4)
MODEL_DIR="${HOME}/.okada/models"
MODEL="${MODEL_DIR}/qwen2.5-3b-instruct-q4_k_m.gguf"
mkdir -p "$MODEL_DIR"
[ -f "$MODEL" ] || curl -L -o "$MODEL" \
  "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"

# 3. python deps for the gateway
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 4. run everything (from here on: NO network needed)
llama-server -m "$MODEL" --port 8081 -c 4096 --host 127.0.0.1 &
sleep 5
.venv/bin/uvicorn gateway.server:app --port 8080 &
sleep 3
echo "Okada is up: open http://127.0.0.1:8080 — now disconnect the network."
