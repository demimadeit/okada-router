"""Model liveness probe: a real one-token completion per configured cloud
model, on a slow interval.

Why: the network probe (network/health.py) measures the PATH to a provider
with GET /models, and any status below 500 counts as healthy. That proves
nothing about the configured MODEL. Groq retired llama-3.x on 16 Aug 2026
and qwen3.6-27b on 14 Sep 2026; developers saw health checks pass while
every completion 404'd. One tiny completion every few minutes costs
nothing at free-tier rates and catches exactly that.

Only ModelNotFoundError changes state here (role.model_ok = False, so the
router skips the rung and the next successful probe re-enables it).
Transport errors and rate limits are the network/health layers' business.
"""
import asyncio
import logging
import time

from gateway.providers import ModelNotFoundError, Registry

log = logging.getLogger("okada.model_probe")
PROBE_MESSAGES = [{"role": "user", "content": "ping"}]


class ModelProbe:
    def __init__(self, registry: Registry, interval_s: float = 300.0, enabled: bool = True):
        self.registry = registry
        self.interval_s = interval_s
        self.enabled = enabled
        self.last_run: float = 0.0
        self.last_results: dict[str, dict] = {}

    async def probe_role(self, route: str, role) -> dict:
        if role.provider.kind != "cloud" or not role.provider.available():
            return {"skipped": True}
        t0 = time.perf_counter()
        try:
            await role.provider.chat(PROBE_MESSAGES, role.model, 1, 0.0)
            role.mark_model_ok()
            out = {"ok": True, "ms": round((time.perf_counter() - t0) * 1000, 1)}
        except ModelNotFoundError as e:
            role.mark_model_gone(str(e))
            log.error("route %s: model %r is gone at %s: %s", route, role.model,
                      role.provider.name, e)
            out = {"ok": False, "model_gone": True, "error": str(e)[:200]}
        except Exception as e:
            # path/health problems are handled by the network monitor and the
            # fallback chain; do not flip model_ok on them
            out = {"ok": False, "model_gone": False, "error": str(e)[:200]}
        self.last_results[route] = {**out, "model": role.model, "provider": role.provider.name,
                                    "ts": time.time()}
        return out

    async def probe_all(self) -> dict:
        self.last_run = time.time()
        seen = set()
        for route, role in list(self.registry.roles.items()):
            key = (role.provider.name, role.model)
            if key in seen:
                continue
            seen.add(key)
            await self.probe_role(route, role)
        return self.last_results

    async def loop(self):
        while True:
            await asyncio.sleep(self.interval_s)
            if not self.enabled:
                continue
            try:
                await self.probe_all()
            except Exception as e:      # never let the probe loop die
                log.warning("model probe failed: %s", e)
