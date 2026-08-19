"""Mock cloud provider: goes through the network simulator like a real cloud
call (so it fails offline, suffers packet loss and pays simulated latency),
then returns a deterministic canned response. Used when no API keys are set,
and by the test suite and benchmark."""
import time
import uuid

import httpx

from gateway.providers import Provider, ProviderError
from network.simulator import simulator


class MockCloudProvider(Provider):
    kind = "cloud"

    def __init__(self, name: str = "mock-cloud"):
        super().__init__()
        self.name = name

    async def chat(self, messages, model, max_tokens, temperature) -> dict:
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
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        text = f"[mock:{model}] Simulated cloud answer to: {last[:120]}"
        await simulator.impose(payload_bytes=len(text) + 400)  # response leg
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
                "prompt_tokens": payload // 4,
                "completion_tokens": len(text) // 4,
                "total_tokens": (payload + len(text)) // 4,
            },
        }


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
