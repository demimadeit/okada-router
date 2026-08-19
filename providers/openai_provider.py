import os

import httpx

from gateway.providers import Provider, ProviderError
from network.simulator import simulator


class OpenAIProvider(Provider):
    name = "openai"
    kind = "cloud"

    def __init__(self, base_url: str = "https://api.openai.com/v1"):
        super().__init__()
        self.base_url = base_url

    def available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

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
                    headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                    json=payload,
                )
        except httpx.HTTPError as e:
            raise ProviderError(f"openai transport error: {e}") from e
        if r.status_code != 200:
            raise ProviderError(f"openai {r.status_code}: {r.text[:200]}")
        return r.json()
