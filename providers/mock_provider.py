"""Mock cloud provider: goes through the network simulator like a real cloud
call (so it fails offline, suffers packet loss and pays simulated latency),
then returns a deterministic canned response. Used when no API keys are set,
and by the test suite and benchmark.

Special model names let tests exercise failure classes without a network:
  "mock-retired"      -> ModelNotFoundError (provider fine, model gone)
  "mock-ratelimited"  -> RateLimitedError
"""
import time
import uuid
from typing import AsyncIterator

import httpx

from gateway.providers import (ModelNotFoundError, Provider, ProviderError, RateLimitedError,
                               StreamChunk)
from network.simulator import simulator


def _response(model: str, text: str, prompt_tokens: int) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": len(text) // 4,
            "total_tokens": prompt_tokens + len(text) // 4,
        },
    }


class MockCloudProvider(Provider):
    kind = "cloud"

    def __init__(self, name: str = "mock-cloud"):
        super().__init__()
        self.name = name

    async def _cross_network(self, messages, model) -> int:
        if not simulator.enabled:
            # real mode: a cloud call must actually cross the network —
            # prove it, so the mock genuinely fails when the link is dead
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    await client.head("https://www.gstatic.com/generate_204")
            except httpx.HTTPError as e:
                raise ProviderError(f"mock-cloud: network unreachable: {e}") from e
        payload = sum(len(m.get("content", "")) for m in messages) + 400
        await simulator.impose(payload_bytes=payload)
        if model == "mock-retired":
            raise ModelNotFoundError(f"{self.name} 404 model unavailable: "
                                     "the model `mock-retired` does not exist")
        if model == "mock-ratelimited":
            raise RateLimitedError(f"{self.name} 429 rate limited")
        return payload

    async def chat(self, messages, model, max_tokens, temperature) -> dict:
        payload = await self._cross_network(messages, model)
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        text = f"[mock:{model}] Simulated cloud answer to: {last[:120]}"
        await simulator.impose(payload_bytes=len(text) + 400)  # response leg
        return _response(model, text, payload // 4)

    async def chat_stream(self, messages, model, max_tokens,
                          temperature) -> AsyncIterator[StreamChunk]:
        payload = await self._cross_network(messages, model)
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        text = f"[mock:{model}] Simulated cloud answer to: {last[:120]}"
        words = text.split(" ")
        for i, w in enumerate(words):
            # each chunk crosses the simulated network, so a mid-stream
            # outage (intermittent profile) surfaces as an exception here
            await simulator.impose(payload_bytes=len(w) + 20)
            yield StreamChunk(text=(w if i == 0 else " " + w), model=model)
        yield StreamChunk(finish_reason="stop", model=model,
                          usage={"prompt_tokens": payload // 4, "completion_tokens": len(text) // 4,
                                 "total_tokens": payload // 4 + len(text) // 4})


class MockLocalProvider(Provider):
    """Test double for the local model: no network, always works."""
    kind = "local"
    name = "mock-local"

    async def chat(self, messages, model, max_tokens, temperature) -> dict:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        text = f"[mock-local:{model}] Offline answer to: {last[:120]}"
        return {
            "id": "chatcmpl-mocklocal",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }
