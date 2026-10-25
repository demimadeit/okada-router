"""Routing engine v0 — deterministic policy, every decision logged.

Deliberately rule-based: rules are debuggable, explainable to a design
partner, and produce the labelled decision log that a learned policy would
later train on. Learned routing without data is astrology.

Policy (first match wins):
  1. exact cache hit                          -> cache
  2. tenant is local-only (no-offshore)       -> local, else queue
  3. offline                                  -> local, else queue
  4. primary cloud provider unhealthy         -> alternate, else cloud-small
  5. latency/loss beyond 'local' thresholds   -> local (online fallback to cloud-small)
  6. latency/loss beyond 'small' thresholds   -> cloud-small
  7. otherwise                                -> cloud-large

execute() then walks a fallback chain from the chosen rung downward, so a
mid-request failure degrades instead of erroring. Failure classes matter:
  ModelNotFoundError  the model is gone, the provider is fine: mark the
                      role's model dead, skip the rung, don't punish the provider
  RateLimitedError    the free tier is spent: one attempt, then next rung
  anything else       provider health failure (counts towards cooldown)
"""
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

from gateway.providers import ModelNotFoundError, RateLimitedError, Registry
from network.health import NetworkState

CONTINUE_PROMPT = ("Your previous reply was cut off by a network failure. Continue exactly "
                   "from where it stopped, without repeating anything already written.")


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
    error_class: str = ""   # "" | "model_gone" | "rate_limited" | "provider"


@dataclass
class ExecutionResult:
    response: dict | None
    route: str
    decision: Decision
    attempts: list[Attempt] = field(default_factory=list)
    fallback_count: int = 0
    retry_count: int = 0
    queued: bool = False
    resumed: int = 0        # number of mid-stream continuations (streaming only)


def _classify(e: Exception) -> str:
    if isinstance(e, ModelNotFoundError):
        return "model_gone"
    if isinstance(e, RateLimitedError):
        return "rate_limited"
    return "provider"


class RoutingEngine:
    def __init__(self, registry: Registry, routing_cfg: dict):
        self.registry = registry
        self.cfg = routing_cfg

    def _healthy(self, route: str) -> bool:
        role = self.registry.get(route)
        if role is None or not role.model_ok:
            return False
        return role.provider.health.healthy(
            self.cfg["provider_failure_threshold"], self.cfg["provider_cooldown_s"]
        )

    def _local_ready(self) -> bool:
        role = self.registry.get("local")
        return role is not None and role.provider.available()

    def decide(self, state: NetworkState, cache_hit: bool, local_only: bool = False) -> Decision:
        if cache_hit:
            return Decision("cache", "exact cache hit")

        if local_only:
            if self._local_ready():
                return Decision("local", "tenant is local-only (no-offshore); on-device model")
            return Decision("queue", "tenant is local-only (no-offshore); no local model — queue")

        if not state.online:
            if self._local_ready():
                return Decision("local", "network offline; local model available")
            return Decision("queue", "network offline; no local model — queue for sync")

        if not self._healthy("cloud-large"):
            why = "primary cloud model retired" if (
                self.registry.get("cloud-large") and not self.registry.get("cloud-large").model_ok
            ) else "primary cloud provider unhealthy"
            if self.registry.get("alternate") and self._healthy("alternate"):
                return Decision("alternate", f"{why}; failover")
            return Decision("cloud-small", f"{why}, no alternate; degrade to small")

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
                f"{state.packet_loss:.0%} loss); smaller model + capped response "
                f"(lower cost, fewer response bytes; prompt unchanged)",
            )

        return Decision("cloud-large", "network healthy")

    def chain(self, decision: Decision, state: NetworkState, allow_cloud: bool = True,
              allowed_models: set | None = None) -> list[str]:
        """Fallback ladder from the decided rung downward."""
        ladder = self._chain(decision, state, allow_cloud)
        if allowed_models is None:
            return ladder
        out = []
        for r in ladder:
            role = self.registry.get(r)
            if r in ("queue", "local") or (role and role.model in allowed_models):
                out.append(r)
        return out

    def _chain(self, decision: Decision, state: NetworkState, allow_cloud: bool) -> list[str]:
        if decision.route == "queue":
            return ["queue"]
        if decision.route == "local":
            ladder = ["local"]
            if state.online and allow_cloud:
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

    def _cap(self, route: str, role, max_tokens: int, degraded_cap: int | None) -> int:
        # Byte reduction has to be DONE, not assumed. Switching to a smaller
        # model lowers cost per token but does not by itself send fewer
        # bytes — the prompt is unchanged and the reply may be just as long.
        # So degraded rungs carry an explicit response cap, which is the part
        # that actually shrinks the transfer.
        if role.provider.kind == "local":
            cap = self.cfg.get("local_max_tokens", 512)
        elif route in ("cloud-small", "alternate"):
            cap = degraded_cap or self.cfg.get("degraded_max_tokens", 300)
        else:
            cap = max_tokens
        return min(max_tokens, cap)

    def _record(self, result: ExecutionResult, route: str, role, ok: bool, ms: float,
                err: Exception | None = None):
        cls = "" if ok else _classify(err)
        if ok:
            role.provider.health.record_success()
        elif cls == "model_gone":
            role.mark_model_gone(str(err))       # provider path is fine; model is not
        else:
            role.provider.health.record_failure(str(err))
        result.attempts.append(Attempt(route, role.provider.name, role.model, ok, ms,
                                       "" if ok else str(err)[:200], cls))

    async def execute(self, decision: Decision, state: NetworkState, messages: list,
                      max_tokens: int, temperature: float,
                      degraded_cap: int | None = None, allow_cloud: bool = True,
                      allowed_models: set | None = None) -> ExecutionResult:
        result = ExecutionResult(response=None, route=decision.route, decision=decision)
        rungs = self.chain(decision, state, allow_cloud, allowed_models)
        for i, route in enumerate(rungs):
            if route == "queue":
                break
            role = self.registry.get(route)
            if not role.provider.available() or not role.model_ok:
                continue
            rung_max_tokens = self._cap(route, role, max_tokens, degraded_cap)
            tries = 2 if route == "cloud-large" else 1
            for _ in range(tries):
                t0 = time.perf_counter()
                try:
                    resp = await role.provider.chat(messages, role.model, rung_max_tokens, temperature)
                    self._record(result, route, role, True, (time.perf_counter() - t0) * 1000)
                    result.response = resp
                    result.route = route
                    result.fallback_count = i
                    result.retry_count = sum(1 for a in result.attempts if not a.ok)
                    return result
                except Exception as e:
                    self._record(result, route, role, False, (time.perf_counter() - t0) * 1000, e)
                    if isinstance(e, (ModelNotFoundError, RateLimitedError)):
                        break   # retrying the same rung cannot help
        result.route = "queue"
        result.queued = True
        result.retry_count = sum(1 for a in result.attempts if not a.ok)
        result.fallback_count = len(rungs)
        return result

    async def execute_stream(self, decision: Decision, state: NetworkState, messages: list,
                             max_tokens: int, temperature: float,
                             degraded_cap: int | None = None, allow_cloud: bool = True,
                             allowed_models: set | None = None) -> AsyncIterator[tuple[str, object]]:
        """Token-level relay with mid-stream failover.

        Yields ("route", route_name) when a rung starts producing,
        ("delta", text) per increment, and finally ("done", ExecutionResult).
        If a rung dies after emitting text, the next rung is asked to continue
        from the partial answer, so the client never sees a restart.
        """
        result = ExecutionResult(response=None, route=decision.route, decision=decision)
        rungs = self.chain(decision, state, allow_cloud, allowed_models)
        partial = ""
        usage: dict = {}
        model_used = ""
        finished = False
        for i, route in enumerate(rungs):
            if route == "queue" or finished:
                break
            role = self.registry.get(route)
            if not role.provider.available() or not role.model_ok:
                continue
            rung_max_tokens = self._cap(route, role, max_tokens, degraded_cap)
            msgs = messages
            if partial:
                msgs = messages + [{"role": "assistant", "content": partial},
                                   {"role": "user", "content": CONTINUE_PROMPT}]
                result.resumed += 1
            t0 = time.perf_counter()
            emitted = 0
            try:
                yield ("route", route)
                async for chunk in role.provider.chat_stream(msgs, role.model,
                                                             rung_max_tokens, temperature):
                    if chunk.model:
                        model_used = chunk.model
                    if chunk.usage:
                        usage = chunk.usage
                    if chunk.text:
                        partial += chunk.text
                        emitted += len(chunk.text)
                        yield ("delta", chunk.text)
                    if chunk.finish_reason:
                        finished = True
                self._record(result, route, role, True, (time.perf_counter() - t0) * 1000)
                result.route = route
                result.fallback_count = i
                finished = True
                break
            except Exception as e:
                self._record(result, route, role, False, (time.perf_counter() - t0) * 1000, e)
                # keep whatever was streamed; the next rung continues it
                continue
        result.retry_count = sum(1 for a in result.attempts if not a.ok)
        if finished or partial:
            result.response = {
                "id": "chatcmpl-stream",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model_used or (self.registry.get(result.route).model
                                        if self.registry.get(result.route) else "okada"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": partial},
                             "finish_reason": "stop" if finished else "length"}],
                "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
            if not finished:
                # text came out but every remaining rung failed: do not hide it
                result.route = next((a.route for a in reversed(result.attempts) if a.ok),
                                    result.route)
        else:
            result.route = "queue"
            result.queued = True
            result.fallback_count = len(rungs)
        yield ("done", result)
