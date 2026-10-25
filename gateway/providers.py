"""Provider abstraction, per-provider health tracking and the role registry.

Roles map routing decisions to concrete (provider, model) pairs:
  cloud-large  -> best cloud model available
  cloud-small  -> cheaper/faster cloud model
  alternate    -> a different cloud provider (failover)
  local        -> on-device model (llama.cpp llama-server, else Ollama)

With no API keys in the environment the cloud roles bind to a mock provider
so routing behaviour can be exercised end-to-end; responses are clearly
labelled [mock]. Adding GROQ_API_KEY / OPENAI_API_KEY / ... switches the
same roles to real providers with no code changes.

Error taxonomy (matters for routing):
  ProviderError        transport / 5xx / unknown      -> provider health failure
  ModelNotFoundError   404 / 410 / "model not found"  -> the PATH is fine, the
                       MODEL is gone (retired); mark the role's model dead,
                       skip the rung, do not blame the provider
  RateLimitedError     429                            -> provider degraded for
                       now; no retry on this rung, move down the ladder
"""
import contextvars
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator

# Per-request bring-your-own upstream key (header x-okada-upstream-key).
# A contextvar so provider code never has to thread it through signatures.
upstream_key_override: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "okada_upstream_key", default=None)


def resolve_upstream_key(provider_name: str, env_var: str) -> str | None:
    """BYO key precedence: per-request header ("*"), tenant key for this
    provider, then the gateway's own environment."""
    ov = upstream_key_override.get() or {}
    return ov.get("*") or ov.get(provider_name) or os.getenv(env_var)


class ProviderError(Exception):
    pass


class ModelNotFoundError(ProviderError):
    """The provider answered, but the requested model does not exist (any
    more). Groq retired two model families in Aug–Sep 2026 with ~30 days'
    notice; a path probe stays green while completions 404."""


class RateLimitedError(ProviderError):
    """HTTP 429. Free tiers are per-org daily/minute budgets; retrying the
    same rung immediately only burns the budget faster."""


_MODEL_GONE_MARKERS = (
    "model_not_found", "does not exist", "not found", "decommissioned",
    "has been retired", "no longer supported", "is not supported", "unknown model",
)


def classify_http_error(provider: str, status: int, text: str) -> ProviderError:
    """Map an upstream HTTP error to the routing-relevant exception."""
    snippet = (text or "")[:300]
    low = snippet.lower()
    if status == 429:
        return RateLimitedError(f"{provider} 429 rate limited: {snippet[:160]}")
    if status in (404, 410) or (status == 400 and "model" in low
                                and any(m in low for m in _MODEL_GONE_MARKERS)):
        return ModelNotFoundError(f"{provider} {status} model unavailable: {snippet[:160]}")
    return ProviderError(f"{provider} {status}: {snippet[:200]}")


@dataclass
class ProviderHealth:
    consecutive_failures: int = 0
    last_failure_ts: float = 0.0
    last_error: str = ""
    total_success: int = 0
    total_failure: int = 0

    def record_success(self):
        self.consecutive_failures = 0
        self.total_success += 1

    def record_failure(self, err: str):
        self.consecutive_failures += 1
        self.total_failure += 1
        self.last_failure_ts = time.time()
        self.last_error = err[:200]

    def healthy(self, threshold: int, cooldown_s: float) -> bool:
        if self.consecutive_failures < threshold:
            return True
        # after the cooldown, allow one probe attempt again
        return (time.time() - self.last_failure_ts) > cooldown_s


@dataclass
class StreamChunk:
    """One increment of a streamed answer."""
    text: str = ""
    finish_reason: str | None = None
    usage: dict | None = None
    model: str = ""


class Provider(ABC):
    name: str = "base"
    kind: str = "cloud"  # "cloud" | "local"

    def __init__(self):
        self.health = ProviderHealth()

    @abstractmethod
    async def chat(self, messages: list, model: str, max_tokens: int, temperature: float) -> dict:
        """Return an OpenAI chat-completions-shaped response dict."""

    async def chat_stream(self, messages: list, model: str, max_tokens: int,
                          temperature: float) -> AsyncIterator[StreamChunk]:
        """Default: no native streaming — run chat() and emit it as one
        chunk. Providers that speak SSE override this."""
        resp = await self.chat(messages, model, max_tokens, temperature)
        text = resp["choices"][0]["message"].get("content") or ""
        yield StreamChunk(text=text, finish_reason="stop", usage=resp.get("usage", {}),
                          model=resp.get("model", model))

    def available(self) -> bool:
        return True


@dataclass
class Role:
    provider: Provider
    model: str
    model_ok: bool = True        # False once a real completion said "model not found"
    model_error: str = ""
    model_checked_at: float = 0.0

    def mark_model_gone(self, err: str):
        self.model_ok = False
        self.model_error = err[:200]
        self.model_checked_at = time.time()

    def mark_model_ok(self):
        self.model_ok = True
        self.model_error = ""
        self.model_checked_at = time.time()


@dataclass
class Registry:
    roles: dict = field(default_factory=dict)  # route -> Role
    mock_mode: bool = False

    def get(self, route: str):
        return self.roles.get(route)


# (env var, provider name, OpenAI-compatible base URL)
COMPAT_SOURCES = [
    ("OPENAI_API_KEY", "openai", "https://api.openai.com/v1"),
    ("ANTHROPIC_API_KEY", "anthropic", None),
    ("GROQ_API_KEY", "groq", "https://api.groq.com/openai/v1"),
    ("GEMINI_API_KEY", "gemini", "https://generativelanguage.googleapis.com/v1beta/openai"),
    ("OPENROUTER_API_KEY", "openrouter", "https://openrouter.ai/api/v1"),
]


def build_registry(cfg: dict) -> Registry:
    # imports here so tests can build registries with pure mocks
    from providers.openai_provider import OpenAIProvider
    from providers.anthropic_provider import AnthropicProvider
    from providers.local_chain import LocalChainProvider
    from providers.mock_provider import MockCloudProvider

    models = cfg["models"]
    reg = Registry()
    cloud = []  # (provider, large_model, small_model)

    # first env var found wins the primary slot; the next becomes alternate
    for key_env, name, base_url in COMPAT_SOURCES:
        if not os.getenv(key_env) or name not in models:
            continue
        if name == "anthropic":
            p = AnthropicProvider()
        else:
            p = OpenAIProvider(name=name, base_url=base_url, key_env=key_env)
        cloud.append((p, models[name]["large"], models[name]["small"]))

    if not cloud:
        reg.mock_mode = True
        primary = MockCloudProvider("mock-cloud")
        alt = MockCloudProvider("mock-alt-cloud")
        cloud.append((primary, models["mock"]["large"], models["mock"]["small"]))
        cloud.append((alt, models["mock"]["alt"], models["mock"]["alt"]))

    reg.roles["cloud-large"] = Role(cloud[0][0], cloud[0][1])
    reg.roles["cloud-small"] = Role(cloud[0][0], cloud[0][2])
    if len(cloud) > 1:
        reg.roles["alternate"] = Role(cloud[1][0], cloud[1][1])

    local = LocalChainProvider(
        llamacpp_url=os.getenv("OKADA_LLAMACPP_URL",
                               models["local"].get("llamacpp_url", "http://127.0.0.1:8081")),
        ollama_model=models["local"]["model"],
    )
    reg.roles["local"] = Role(local, models["local"]["model"])
    return reg
