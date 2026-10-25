"""Per-request telemetry: one JSON line per request to logs/telemetry.jsonl.

These records are the seed of the routing dataset (network state ->
decision -> outcome). Nothing here leaves the machine, and no prompt text is
stored: prompts are hashed, so re-asks and duplicates can be found without
retaining personal data.

What a learned routing policy would need, and now gets:
- prompt_sha256 / last_user_sha256 (join keys, not content), prompt_chars
- lang: a stopword heuristic over the last user message (en, pcm, yo, ha,
  ig, sw, fr); explicitly labelled as a heuristic in lang_method
- quality labels: explicit via POST /okada/feedback, implicit negative when
  the same user re-asks the same thing within 60 s (reask_of)
- real costs per provider/model, both at list price (list_cost_usd) and as
  actually billed (est_cost_usd, zero for providers in OKADA_FREE_TIER_PROVIDERS)
- per-tenant spend
"""
import hashlib
import json
import os
import re
import time
from collections import deque
from dataclasses import asdict
from pathlib import Path
from statistics import median

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# USD per 1M tokens (input, output). List prices as of Oct 2026 where the
# research could verify them; entries marked "verify" were taken from
# secondary sources. Run scripts/check_models.py against live pricing pages
# before quoting savings to a customer.
COST_PER_M = {
    # Groq (free tier exists; paid list prices)
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.10, 0.50),           # verify
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    # Anthropic
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-5-5": (3.00, 15.00),            # verify
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-5-5": (0.10, 0.50),              # verify (third-party report, Oct 2026)
    # Google (free tier exists)
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-3.5-flash-lite": (0.30, 2.50),         # verify
    # OpenRouter
    "openai/gpt-oss-20b:free": (0.0, 0.0),
}

# providers whose usage is currently inside a free tier -> est_cost 0
FREE_TIER_PROVIDERS = {p.strip() for p in os.getenv("OKADA_FREE_TIER_PROVIDERS", "").split(",")
                       if p.strip()}

REASK_WINDOW_S = 60.0

# tiny stopword lists; enough to tag a corpus, not to ship a language product
_LANG_WORDS = {
    "en": {"the", "is", "are", "and", "what", "how", "please", "can", "you", "with", "for", "to"},
    "pcm": {"abeg", "wetin", "dey", "una", "na", "sabi", "wahala", "don", "sef", "comot", "oga",
            "pikin", "make", "dem", "no", "wan"},
    "yo": {"bawo", "ni", "jọwọ", "jowo", "ṣe", "se", "mo", "kí", "ki", "ẹ", "ọmọ", "omo", "owó",
           "owo", "ilé", "ile", "dára", "dara", "kini", "nibo", "àwọn", "awon"},
    "ha": {"sannu", "ina", "yaya", "don", "allah", "kai", "ke", "mu", "nawa", "lafiya", "kuma",
           "wannan", "abin", "yana", "gida", "ruwa"},
    "ig": {"kedu", "biko", "nnoo", "ndewo", "gịnị", "gini", "ego", "nwanne", "ụlọ", "ulo", "ihe",
           "anyị", "anyi", "ọ", "dị", "di", "bụ", "bu", "onye"},
    "sw": {"habari", "asante", "tafadhali", "nini", "ni", "na", "kwa", "wewe", "mimi", "sasa",
           "pesa", "jambo", "ndiyo", "hapana", "kazi", "shule"},
    "fr": {"le", "la", "les", "est", "et", "vous", "pour", "comment", "merci", "bonjour", "je",
           "une", "des", "pas", "avec"},
}


def detect_lang(text: str) -> str:
    words = re.findall(r"[^\W\d_]+", (text or "").lower())
    if not words:
        return "und"
    scores = {lang: sum(1 for w in words if w in vocab) for lang, vocab in _LANG_WORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "und"


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class Telemetry:
    def __init__(self, path: Path | None = None, feedback_path: Path | None = None):
        self.path = path or (LOG_DIR / "telemetry.jsonl")
        self.feedback_path = feedback_path or (LOG_DIR / "feedback.jsonl")
        self.path.parent.mkdir(exist_ok=True, parents=True)
        self.records: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._recent: deque = deque(maxlen=2000)   # (ts, tenant, last_user_sha, request_id)

    @staticmethod
    def cost(model: str, provider: str, usage: dict) -> tuple[float, float]:
        in_tok = usage.get("prompt_tokens", 0) or 0
        out_tok = usage.get("completion_tokens", 0) or 0
        rates = COST_PER_M.get(model.removeprefix("local/"), (0.0, 0.0))
        if model.startswith("local/") or provider.startswith("mock"):
            rates = (0.0, 0.0)
        list_cost = round(in_tok / 1e6 * rates[0] + out_tok / 1e6 * rates[1], 6)
        est = 0.0 if provider in FREE_TIER_PROVIDERS else list_cost
        return list_cost, est

    def reask_of(self, tenant: str, last_user_sha: str, request_id: str) -> str | None:
        """Implicit negative label: same user, same question, within 60 s."""
        now = time.time()
        prev = None
        for ts, t, sha, rid in reversed(self._recent):
            if now - ts > REASK_WINDOW_S:
                break
            if t == tenant and sha == last_user_sha and rid != request_id:
                prev = rid
                break
        self._recent.append((now, tenant, last_user_sha, request_id))
        return prev

    def record(self, *, request_id: str, network: dict, decision: dict, attempts: list,
               final_route: str, cache_hit: bool, queued: bool, retry_count: int,
               fallback_count: int, request_bytes: int, response_bytes: int,
               usage: dict, model: str, total_ms: float, success: bool,
               messages: list | None = None, provider: str = "", tenant: str = "default",
               streamed: bool = False, resumed: int = 0, response_text: str = "") -> dict:
        messages = messages or []
        last_user = next((m.get("content", "") for m in reversed(messages)
                          if m.get("role") == "user"), "")
        last_user_sha = _sha(last_user) if last_user else ""
        list_cost, est_cost = self.cost(model, provider, usage)
        rec = {
            "ts": time.time(),
            "request_id": request_id,
            "tenant": tenant,
            "network": network,
            "decision": decision,
            "attempts": [asdict(a) for a in attempts],
            "final_route": final_route,
            "provider": provider,
            "model": model,
            "cache_hit": cache_hit,
            "queued": queued,
            "streamed": streamed,
            "resumed": resumed,
            "retry_count": retry_count,
            "fallback_count": fallback_count,
            "request_bytes": request_bytes,
            "response_bytes": response_bytes,
            "prompt_sha256": _sha([(m.get("role"), m.get("content")) for m in messages]) if messages else "",
            "last_user_sha256": last_user_sha,
            "prompt_chars": sum(len(m.get("content") or "") for m in messages),
            "response_chars": len(response_text or ""),
            "n_messages": len(messages),
            "lang": detect_lang(last_user),
            "lang_method": "stopword-heuristic",
            "prompt_tokens": usage.get("prompt_tokens", 0) or 0,
            "completion_tokens": usage.get("completion_tokens", 0) or 0,
            "list_cost_usd": list_cost,
            "est_cost_usd": est_cost,
            "total_ms": round(total_ms, 1),
            "success": success,
            "reask_of": self.reask_of(tenant, last_user_sha, request_id) if last_user_sha else None,
            "quality": None,          # filled by POST /okada/feedback
        }
        if rec["reask_of"]:
            self._implicit_negative(rec["reask_of"], request_id)
        self.records.append(rec)
        self._by_id[request_id] = rec
        with open(self.path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec

    def _implicit_negative(self, prev_request_id: str, new_request_id: str):
        evt = {"ts": time.time(), "request_id": prev_request_id, "rating": "down",
               "source": "implicit", "reason": f"re-asked within {int(REASK_WINDOW_S)}s",
               "reask_request_id": new_request_id}
        prev = self._by_id.get(prev_request_id)
        if prev is not None and prev.get("quality") is None:
            prev["quality"] = "down(implicit)"
        with open(self.feedback_path, "a") as f:
            f.write(json.dumps(evt) + "\n")

    def feedback(self, request_id: str, rating: str, comment: str = "",
                 tenant: str = "default") -> bool:
        rec = self._by_id.get(request_id)
        evt = {"ts": time.time(), "request_id": request_id, "rating": rating,
               "comment": (comment or "")[:500], "source": "explicit", "tenant": tenant,
               "known_request": rec is not None}
        if rec is not None:
            rec["quality"] = rating
        with open(self.feedback_path, "a") as f:
            f.write(json.dumps(evt) + "\n")
        return rec is not None

    def tenant_spend(self, tenant: str, since_ts: float = 0.0) -> float:
        return round(sum(r["est_cost_usd"] for r in self.records
                         if r["tenant"] == tenant and r["ts"] >= since_ts), 6)

    def summary(self) -> dict:
        n = len(self.records)
        if n == 0:
            return {"requests": 0}
        lat = sorted(r["total_ms"] for r in self.records)
        routes: dict[str, int] = {}
        langs: dict[str, int] = {}
        tenants: dict[str, dict] = {}
        for r in self.records:
            routes[r["final_route"]] = routes.get(r["final_route"], 0) + 1
            langs[r["lang"]] = langs.get(r["lang"], 0) + 1
            t = tenants.setdefault(r["tenant"], {"requests": 0, "est_cost_usd": 0.0,
                                                 "list_cost_usd": 0.0})
            t["requests"] += 1
            t["est_cost_usd"] = round(t["est_cost_usd"] + r["est_cost_usd"], 6)
            t["list_cost_usd"] = round(t["list_cost_usd"] + r["list_cost_usd"], 6)
        answered = sum(1 for r in self.records if r["success"])
        local_or_cache = sum(1 for r in self.records if r["final_route"] in ("local", "cache"))
        return {
            "requests": n,
            "answered": answered,
            "answered_rate": round(answered / n, 3),
            "queued": sum(1 for r in self.records if r["queued"]),
            "cache_hits": sum(1 for r in self.records if r["cache_hit"]),
            "served_without_cloud_rate": round(local_or_cache / n, 3),
            "routes": routes,
            "langs": langs,
            "p50_ms": round(median(lat), 1),
            "p95_ms": round(lat[max(0, int(n * 0.95) - 1)], 1),
            "total_retries": sum(r["retry_count"] for r in self.records),
            "total_fallbacks": sum(r["fallback_count"] for r in self.records),
            "stream_resumes": sum(r["resumed"] for r in self.records),
            "reasks": sum(1 for r in self.records if r["reask_of"]),
            "feedback": {"up": sum(1 for r in self.records if r["quality"] == "up"),
                         "down": sum(1 for r in self.records
                                     if r["quality"] and str(r["quality"]).startswith("down"))},
            "list_cost_usd": round(sum(r["list_cost_usd"] for r in self.records), 4),
            "est_cost_usd": round(sum(r["est_cost_usd"] for r in self.records), 4),
            "tenants": tenants,
        }
