"""Local inference via llama.cpp's llama-server (OpenAI-compatible API).

This is the ADTC-compliant local backend: GGUF weights served by llama.cpp,
fully offline. Like the Ollama provider, calls do not pass through the
network simulator — local inference is the point.
"""
import httpx

from gateway.providers import Provider, ProviderError

_AVAILABILITY_TTL_S = 15


class LlamaCppProvider(Provider):
    name = "llamacpp"
    kind = "local"

    def __init__(self, base_url: str = "http://127.0.0.1:8081"):
        super().__init__()
        self.base_url = base_url
        self._available = None
        self._checked_at = 0.0

    def available(self) -> bool:
        import time
        now = time.time()
        if self._available is None or (now - self._checked_at) > _AVAILABILITY_TTL_S:
            try:
                r = httpx.get(f"{self.base_url}/health", timeout=0.8)
                self._available = r.status_code == 200
            except Exception:
                self._available = False
            self._checked_at = now
        return self._available

    async def chat(self, messages, model, max_tokens, temperature) -> dict:
        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
        except httpx.HTTPError as e:
            raise ProviderError(f"llamacpp transport error: {e}") from e
        if r.status_code != 200:
            raise ProviderError(f"llamacpp {r.status_code}: {r.text[:200]}")
        data = r.json()
        data["model"] = f"local/{data.get('model', 'gguf')}"
        return data
