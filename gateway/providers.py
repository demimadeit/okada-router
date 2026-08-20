"""Provider abstraction, per-provider health tracking and the role registry.

Roles map routing decisions to concrete (provider, model) pairs:
  cloud-large  -> best cloud model available
  cloud-small  -> cheaper/faster cloud model
  alternate    -> a different cloud provider (failover)
  local        -> on-device model via Ollama

With no API keys in the environment the cloud roles bind to a mock provider
so routing behaviour can be exercised end-to-end; responses are clearly
labelled [mock]. Adding OPENAI_API_KEY / ANTHROPIC_API_KEY switches the
same roles to real providers with no code changes.
"""
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ProviderError(Exception):
    pass


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


class Provider(ABC):
    name: str = "base"
    kind: str = "cloud"  # "cloud" | "local"

    def __init__(self):
        self.health = ProviderHealth()

    @abstractmethod
    async def chat(self, messages: list, model: str, max_tokens: int, temperature: float) -> dict:
        """Return an OpenAI chat-completions-shaped response dict."""

    def available(self) -> bool:
        return True


@dataclass
class Role:
    provider: Provider
    model: str


@dataclass
class Registry:
    roles: dict = field(default_factory=dict)  # route -> Role
    mock_mode: bool = False

    def get(self, route: str):
        return self.roles.get(route)


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
    compat_sources = [
        ("OPENAI_API_KEY", "openai", "https://api.openai.com/v1"),
        ("ANTHROPIC_API_KEY", "anthropic", None),
        ("GROQ_API_KEY", "groq", "https://api.groq.com/openai/v1"),
        ("GEMINI_API_KEY", "gemini", "https://generativelanguage.googleapis.com/v1beta/openai"),
        ("OPENROUTER_API_KEY", "openrouter", "https://openrouter.ai/api/v1"),
    ]
    for key_env, name, base_url in compat_sources:
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
