"""Tenants and virtual keys.

Three ways to configure, from simplest to most complete:
  (none)            open gateway (local dev); every request is tenant "default"
  OKADA_API_KEY     one bearer key, one tenant ("default") — unchanged behaviour
  OKADA_KEYS_FILE   YAML with one entry per virtual key:
      keys:
        - key: ok_live_abc123
          tenant: lagos-pharmacy-1
          max_budget_usd: 5.00        # optional
          budget_duration: daily      # daily | monthly | total (default total)
          models_allowed: [openai/gpt-oss-20b]   # optional allow-list
          no_offshore: true           # only cache/local/queue — never a cloud call
          degraded_max_tokens: 200    # per-tenant cap on degraded rungs
          upstream_keys:              # optional BYO provider keys for this tenant
            groq: gsk_...

A per-request header `x-okada-upstream-key` overrides the upstream provider
key for that one call (bring-your-own-key without storing it).

Budgets are enforced against telemetry's est_cost_usd, so a tenant on a
free-tier provider spends 0 and never trips; set OKADA_FREE_TIER_PROVIDERS
accordingly.
"""
import hmac
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Tenant:
    id: str
    key: str | None = None
    max_budget_usd: float | None = None
    budget_duration: str = "total"           # daily | monthly | total
    models_allowed: list[str] | None = None
    no_offshore: bool = False
    degraded_max_tokens: int | None = None
    upstream_keys: dict = field(default_factory=dict)

    def budget_window_start(self, now: float | None = None) -> float:
        now = now or time.time()
        if self.budget_duration == "daily":
            return now - (now % 86400)
        if self.budget_duration == "monthly":
            t = time.gmtime(now)
            return time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, 0)) - time.timezone
        return 0.0

    def public(self) -> dict:
        return {"tenant": self.id, "max_budget_usd": self.max_budget_usd,
                "budget_duration": self.budget_duration, "no_offshore": self.no_offshore,
                "models_allowed": self.models_allowed,
                "degraded_max_tokens": self.degraded_max_tokens}


OPEN_TENANT = Tenant(id="default")


class TenantRegistry:
    """Static keys (env / YAML) plus, optionally, the console's account store
    (gateway/accounts.py) for keys created at runtime."""

    def __init__(self, tenants: list[Tenant], store=None):
        self.by_key = {t.key: t for t in tenants if t.key}
        self.store = store

    @property
    def open(self) -> bool:
        """Open (no auth) only while no key exists anywhere: none in env/YAML
        and none created in the console. Creating the first key closes it."""
        if self.by_key:
            return False
        return self.store is None or not self.store.has_keys()

    def authenticate(self, authorization: str | None) -> Tenant | None:
        """Return the tenant for a bearer header, OPEN_TENANT when no keys are
        configured anywhere, or None when the key is missing/invalid."""
        if self.open:
            return OPEN_TENANT
        if not authorization or not authorization.lower().startswith("bearer "):
            return None
        presented = authorization[7:].strip()
        for key, tenant in self.by_key.items():
            if hmac.compare_digest(presented, key):
                return tenant
        if self.store is not None:
            return self.store.tenant_for_key(presented)
        return None


def load_tenants() -> TenantRegistry:
    tenants: list[Tenant] = []
    single = os.getenv("OKADA_API_KEY")
    if single:
        tenants.append(Tenant(id="default", key=single))
    path = os.getenv("OKADA_KEYS_FILE")
    if path and Path(path).exists():
        with open(path) as f:
            doc = yaml.safe_load(f) or {}
        for entry in doc.get("keys", []):
            if not entry.get("key"):
                continue
            tenants.append(Tenant(
                id=str(entry.get("tenant") or entry["key"][:8]),
                key=str(entry["key"]),
                max_budget_usd=entry.get("max_budget_usd"),
                budget_duration=str(entry.get("budget_duration", "total")),
                models_allowed=entry.get("models_allowed"),
                no_offshore=bool(entry.get("no_offshore", False)),
                degraded_max_tokens=entry.get("degraded_max_tokens"),
                upstream_keys=entry.get("upstream_keys") or {},
            ))
    return TenantRegistry(tenants)
