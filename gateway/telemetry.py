"""Per-request telemetry: one JSON line per request to logs/telemetry.jsonl.

These records are the seed of the routing dataset (network state -> decision
-> outcome). Nothing here leaves the machine.
"""
import json
import time
from dataclasses import asdict
from pathlib import Path
from statistics import median

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# rough public list prices, USD per 1M tokens (input, output); estimates
COST_PER_M = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}


class Telemetry:
    def __init__(self, path: Path | None = None):
        self.path = path or (LOG_DIR / "telemetry.jsonl")
        self.path.parent.mkdir(exist_ok=True)
        self.records: list[dict] = []

    def record(self, *, request_id: str, network: dict, decision: dict, attempts: list,
               final_route: str, cache_hit: bool, queued: bool, retry_count: int,
               fallback_count: int, request_bytes: int, response_bytes: int,
               usage: dict, model: str, total_ms: float, success: bool):
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        rates = COST_PER_M.get(model, (0.0, 0.0))
        rec = {
            "ts": time.time(),
            "request_id": request_id,
            "network": network,
            "decision": decision,
            "attempts": [asdict(a) for a in attempts],
            "final_route": final_route,
            "cache_hit": cache_hit,
            "queued": queued,
            "retry_count": retry_count,
            "fallback_count": fallback_count,
            "request_bytes": request_bytes,
            "response_bytes": response_bytes,
            "prompt_tokens": in_tok,
            "completion_tokens": out_tok,
            "est_cost_usd": round(in_tok / 1e6 * rates[0] + out_tok / 1e6 * rates[1], 6),
            "total_ms": round(total_ms, 1),
            "success": success,
        }
        self.records.append(rec)
        with open(self.path, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def summary(self) -> dict:
        n = len(self.records)
        if n == 0:
            return {"requests": 0}
        lat = sorted(r["total_ms"] for r in self.records)
        routes: dict[str, int] = {}
        for r in self.records:
            routes[r["final_route"]] = routes.get(r["final_route"], 0) + 1
        answered = sum(1 for r in self.records if r["success"])
        return {
            "requests": n,
            "answered": answered,
            "answered_rate": round(answered / n, 3),
            "queued": sum(1 for r in self.records if r["queued"]),
            "cache_hits": sum(1 for r in self.records if r["cache_hit"]),
            "routes": routes,
            "p50_ms": round(median(lat), 1),
            "p95_ms": round(lat[max(0, int(n * 0.95) - 1)], 1),
            "total_retries": sum(r["retry_count"] for r in self.records),
            "total_fallbacks": sum(r["fallback_count"] for r in self.records),
            "est_cost_usd": round(sum(r["est_cost_usd"] for r in self.records), 4),
        }
