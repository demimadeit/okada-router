#!/usr/bin/env python3
"""Repeatable resilience benchmark: direct cloud calls vs Okada routing,
across simulated network profiles, against a running gateway.

Usage: python scripts/benchmark.py [--n 25] [--url http://127.0.0.1:8080]

Honesty notes (also printed with results):
- Network conditions are simulated at the application layer, not a real
  Nigerian network. The comparison isolates ROUTING BEHAVIOUR under identical
  conditions; absolute latencies are synthetic.
- In mock-cloud mode the "cloud" is a canned responder behind the simulator.
  Re-run with real API keys for provider-realistic numbers.
"""
import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx

PROFILES = ["excellent", "4g", "3g", "high-latency", "packet-loss", "intermittent", "offline"]
PROMPTS = [
    "Summarise: the delivery van broke down on Ikorodu road, reschedule stops.",
    "Draft a two-line reply confirming the customer's order was received.",
    "What documents does a rider need to register on the platform?",
    "Classify this message as complaint, question or praise: 'my order is late again'",
    "Translate to simple English: payment reconciliation is pending network sync.",
]


async def run_mode(client, url, mode, n):
    ok, latencies, routes = 0, [], {}
    headers = {"x-okada-mode": "direct"} if mode == "direct" else {}
    for i in range(n):
        payload = {"model": "auto",
                   "messages": [{"role": "user", "content": f"[{mode}-{i}] {PROMPTS[i % len(PROMPTS)]}"}]}
        t0 = time.perf_counter()
        try:
            r = await client.post(f"{url}/v1/chat/completions", json=payload,
                                  headers=headers, timeout=40)
            ms = (time.perf_counter() - t0) * 1000
            if r.status_code == 200:
                body = r.json()
                route = body.get("okada", {}).get("route", "?")
                # a queued request is NOT a served answer; count separately
                if route == "queue":
                    routes["queue"] = routes.get("queue", 0) + 1
                else:
                    ok += 1
                    latencies.append(ms)
                    routes[route] = routes.get(route, 0) + 1
            else:
                routes["error"] = routes.get("error", 0) + 1
        except Exception:
            routes["timeout"] = routes.get("timeout", 0) + 1
    return {
        "answered": ok,
        "n": n,
        "answered_rate": round(ok / n, 3),
        "p50_ms": round(statistics.median(latencies), 1) if latencies else None,
        "p95_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 1) if latencies else None,
        "routes": routes,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    args = ap.parse_args()

    results = {}
    async with httpx.AsyncClient() as client:
        for profile in PROFILES:
            r = await client.post(f"{args.url}/okada/network", json={"profile": profile})
            r.raise_for_status()
            await client.post(f"{args.url}/okada/cache/clear")
            direct = await run_mode(client, args.url, "direct", args.n)
            await client.post(f"{args.url}/okada/cache/clear")
            okada = await run_mode(client, args.url, "okada", args.n)
            results[profile] = {"direct": direct, "okada": okada}
            print(f"{profile:>13} | direct {direct['answered_rate']:>5.0%} "
                  f"p50={str(direct['p50_ms']):>7}ms | okada {okada['answered_rate']:>5.0%} "
                  f"p50={str(okada['p50_ms']):>7}ms | okada routes={okada['routes']}")
        await client.post(f"{args.url}/okada/network", json={"profile": "excellent"})

    out = Path(__file__).resolve().parent.parent / "logs" / f"bench-{int(time.time())}.json"
    out.write_text(json.dumps({"n_per_cell": args.n, "results": results,
                               "note": "application-level simulation; mock cloud unless API keys set"}, indent=2))
    print(f"\nsaved: {out}")


if __name__ == "__main__":
    asyncio.run(main())
