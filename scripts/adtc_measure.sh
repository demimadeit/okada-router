#!/usr/bin/env bash
# One command to produce every number the ADTC report needs, on the target box.
#   ./scripts/adtc_measure.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== host ==="
(lscpu | grep -E "Model name|^CPU\(s\)" || sysctl -n machdep.cpu.brand_string) 2>/dev/null
(free -h | head -2 || vm_stat | head -2) 2>/dev/null
echo

echo "=== local model throughput + RSS (under the 8GB cap) ==="
.venv/bin/python scripts/measure_local.py --n 5

echo
echo "=== resilience benchmark: direct vs okada ==="
.venv/bin/python scripts/benchmark.py --n 8

echo
echo "=== OFFLINE PROOF: cutting all outbound traffic, then asking ==="
echo "(run this manually if you want the hard proof:)"
echo "  sudo ip link set eth0 down; curl -s localhost:8080/v1/chat/completions ... ; sudo ip link set eth0 up"
