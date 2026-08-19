"""Local inference via Ollama (http://127.0.0.1:11434).

Local calls do NOT pass through the network simulator — that is the point:
the device can answer even when the network cannot.
"""
import time
import uuid

import httpx

from gateway.providers import Provider, ProviderError

OLLAMA = "http://127.0.0.1:11434"
_AVAILABILITY_TTL_S = 15


class OllamaProvider(Provider):
    name = "ollama"
    kind = "local"

    def __init__(self):
        super().__init__()
        self._available = None
        self._checked_at = 0.0

    def available(self) -> bool:
        now = time.time()
        if self._available is None or (now - self._checked_at) > _AVAILABILITY_TTL_S:
            try:
                r = httpx.get(f"{OLLAMA}/api/tags", timeout=0.8)
                self._available = r.status_code == 200 and bool(r.json().get("models"))
            except Exception:
                self._available = False
            self._checked_at = now
        return self._available

    async def chat(self, messages, model, max_tokens, temperature) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(f"{OLLAMA}/api/chat", json=payload)
        except httpx.HTTPError as e:
            raise ProviderError(f"ollama transport error: {e}") from e
        if r.status_code != 200:
            raise ProviderError(f"ollama {r.status_code}: {r.text[:200]}")
        data = r.json()
        text = data.get("message", {}).get("content", "")
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": f"local/{model}",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
        }
