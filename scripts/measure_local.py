#!/usr/bin/env python3
"""Measure the local backend against the ADTC judging criteria:
throughput (tokens/sec) and memory efficiency (peak RSS of the model server).

Usage: python scripts/measure_local.py [--url http://127.0.0.1:8081] [--n 5]
Works against llama-server (preferred, GGUF) at :8081.
"""
import argparse
import json
import statistics
import subprocess
import time

import httpx

PROMPTS = [
    "Explain in two sentences why fibre cuts affect mobile internet in Lagos.",
    "Draft a polite one-line SMS telling a customer their order is ready for pickup.",
    "List three documents a delivery rider typically needs to register with a platform.",
    "Summarise in one sentence: the generator ran out of diesel so the clinic closed early.",
    "Translate to Nigerian Pidgin: 'The network is down, please try again later.'",
]


def rss_mb(pattern: str) -> float | None:
    """Peak-ish RSS of the model server process (macOS/Linux ps)."""
    try:
        out = subprocess.check_output(["pgrep", "-f", pattern]).decode().split()
        total = 0
        for pid in out:
            rss = subprocess.check_output(["ps", "-o", "rss=", "-p", pid]).decode().strip()
            total += int(rss)
        return round(total / 1024, 1) if total else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8081")
    ap.add_argument("--n", type=int, default=5)
    args = ap.parse_args()

    tps_list, ttft_note = [], None
    with httpx.Client(timeout=180) as client:
        for i in range(args.n):
            prompt = PROMPTS[i % len(PROMPTS)]
            t0 = time.perf_counter()
            r = client.post(f"{args.url}/v1/chat/completions",
                            json={"messages": [{"role": "user", "content": prompt}],
                                  "max_tokens": 200, "temperature": 0.7})
            elapsed = time.perf_counter() - t0
            r.raise_for_status()
            data = r.json()
            # llama-server reports precise timings; fall back to wall-clock
            timings = data.get("timings", {})
            tps = timings.get("predicted_per_second")
            if tps is None:
                completion = data.get("usage", {}).get("completion_tokens", 0)
                tps = completion / elapsed if elapsed > 0 else 0
            tps_list.append(tps)
            print(f"run {i+1}: {tps:.1f} tok/s (wall {elapsed:.1f}s)")

    result = {
        "runs": args.n,
        "tokens_per_second_median": round(statistics.median(tps_list), 1),
        "tokens_per_second_min": round(min(tps_list), 1),
        "server_rss_mb": rss_mb("llama-server"),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
