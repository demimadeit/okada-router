import os

import httpx

from gateway.providers import Provider, ProviderError
from network.simulator import simulator


class OpenAIProvider(Provider):
    """Any OpenAI-compatible cloud API (OpenAI, Groq, Gemini's compat
    endpoint, OpenRouter, ...) — parameterized by base_url + key env var."""
    kind = "cloud"

    def __init__(self, name: str = "openai",
                 base_url: str = "https://api.openai.com/v1",
                 key_env: str = "OPENAI_API_KEY"):
        super().__init__()
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.key_env = key_env

    def available(self) -> bool:
        return bool(os.getenv(self.key_env))

    async def chat(self, messages, model, max_tokens, temperature) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        await simulator.impose(payload_bytes=len(str(payload)))
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {os.environ[self.key_env]}"},
                    json=payload,
                )
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name} transport error: {e}") from e
        if r.status_code != 200:
            raise ProviderError(f"{self.name} {r.status_code}: {r.text[:200]}")
        return r.json()
