"""Routing engine v0 — deterministic policy, every decision logged.

Deliberately rule-based for week 1: rules are debuggable, explainable to a
design partner, and produce the labelled decision log that a learned policy
would later train on. Learned routing without data is astrology.

Policy (first match wins):
  1. exact cache hit                          -> cache
  2. offline                                  -> local, else queue
  3. primary cloud provider unhealthy         -> alternate, else cloud-small
  4. latency/loss beyond 'local' thresholds   -> local (online fallback to cloud-small)
  5. latency/loss beyond 'small' thresholds   -> cloud-small
  6. otherwise                                -> cloud-large

execute() then walks a fallback chain from the chosen rung downward, so a
mid-request failure degrades instead of erroring.
"""
import time
from dataclasses import dataclass, field

from gateway.providers import Registry
from network.health import NetworkState


@dataclass
class Decision:
    route: str
    reason: str


@dataclass
class Attempt:
    route: str
    provider: str
    model: str
    ok: bool
    ms: float
    error: str = ""


@dataclass
class ExecutionResult:
    response: dict | None
    route: str
    decision: Decision
    attempts: list[Attempt] = field(default_factory=list)
    fallback_count: int = 0
    retry_count: int = 0
    queued: bool = False


class RoutingEngine:
    def __init__(self, registry: Registry, routing_cfg: dict):
        self.registry = registry
        self.cfg = routing_cfg

    def _healthy(self, route: str) -> bool:
        role = self.registry.get(route)
        if role is None:
            return False
        return role.provider.health.healthy(
            self.cfg["provider_failure_threshold"], self.cfg["provider_cooldown_s"]
        )

    def _local_ready(self) -> bool:
        role = self.registry.get("local")
        return role is not None and role.provider.available()

    def decide(self, state: NetworkState, cache_hit: bool) -> Decision:
        if cache_hit:
            return Decision("cache", "exact cache hit")

        if not state.online:
            if self._local_ready():
                return Decision("local", "network offline; local model available")
            return Decision("queue", "network offline; no local model — queue for sync")

        if not self._healthy("cloud-large"):
            if self.registry.get("alternate") and self._healthy("alternate"):
                return Decision("alternate", "primary cloud provider unhealthy; failover")
            return Decision("cloud-small", "primary unhealthy, no alternate; degrade to small")

        if (state.latency_ms >= self.cfg["local_latency_ms"]
                or state.packet_loss >= self.cfg["local_loss"]):
            if self._local_ready():
                return Decision(
                    "local",
                    f"network severely degraded ({state.latency_ms:.0f}ms, "
                    f"{state.packet_loss:.0%} loss); local model faster than retry storm",
                )
            return Decision("cloud-small", "network severely degraded; no local model")

        if (state.latency_ms >= self.cfg["small_latency_ms"]
                or state.packet_loss >= self.cfg["small_loss"]):
            return Decision(
                "cloud-small",
                f"network degraded ({state.latency_ms:.0f}ms, "
                f"{state.packet_loss:.0%} loss); smaller model cuts transfer + cost",
            )

        return Decision("cloud-large", "network healthy")

    def chain(self, decision: Decision, state: NetworkState) -> list[str]:
        """Fallback ladder from the decided rung downward."""
        if decision.route == "queue":
            return ["queue"]
        if decision.route == "local":
            ladder = ["local"]
            if state.online:
                ladder.append("cloud-small")  # local runtime may be missing/broken
            ladder.append("queue")
            return ladder
        ladders = {
            "cloud-large": ["cloud-large", "cloud-small", "alternate", "local", "queue"],
            "cloud-small": ["cloud-small", "alternate", "local", "queue"],
            "alternate":   ["alternate", "cloud-small", "local", "queue"],
        }
        ladder = ladders[decision.route]
        return [r for r in ladder if r == "queue" or self.registry.get(r) is not None]

    async def execute(self, decision: Decision, state: NetworkState, messages: list,
                      max_tokens: int, temperature: float) -> ExecutionResult:
        result = ExecutionResult(response=None, route=decision.route, decision=decision)
        rungs = self.chain(decision, state)
        for i, route in enumerate(rungs):
            if route == "queue":
                result.route = "queue"
                result.queued = True
                result.fallback_count = i
                return result
            role = self.registry.get(route)
            if not role.provider.available():
                continue
            tries = 2 if route == "cloud-large" else 1
            for t in range(tries):
                t0 = time.perf_counter()
                try:
                    resp = await role.provider.chat(messages, role.model, max_tokens, temperature)
                    ms = (time.perf_counter() - t0) * 1000
                    role.provider.health.record_success()
                    result.attempts.append(Attempt(route, role.provider.name, role.model, True, ms))
                    result.response = resp
                    result.route = route
                    result.fallback_count = i
                    result.retry_count = sum(1 for a in result.attempts if not a.ok)
                    return result
                except Exception as e:
                    ms = (time.perf_counter() - t0) * 1000
                    role.provider.health.record_failure(str(e))
                    result.attempts.append(
                        Attempt(route, role.provider.name, role.model, False, ms, str(e)[:200]))
        result.route = "queue"
        result.queued = True
        result.retry_count = sum(1 for a in result.attempts if not a.ok)
        result.fallback_count = len(rungs)
        return result
