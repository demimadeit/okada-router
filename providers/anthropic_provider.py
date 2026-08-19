import os
import time
import uuid

import httpx

from gateway.providers import Provider, ProviderError
from network.simulator import simulator


class AnthropicProvider(Provider):
    """Calls the Anthropic Messages API and adapts the result to the
    OpenAI chat-completions shape the gateway speaks."""
    name = "anthropic"
    kind = "cloud"

    def __init__(self, base_url: str = "https://api.anthropic.com"):
        super().__init__()
        self.base_url = base_url

    def available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))

    async def chat(self, messages, model, max_tokens, temperature) -> dict:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        chat_messages = [m for m in messages if m["role"] in ("user", "assistant")]
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system:
            payload["system"] = system
        await simulator.impose(payload_bytes=len(str(payload)))
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers={
                        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                        "anthropic-version": "2023-06-01",
                    },
                    json=payload,
                )
        except httpx.HTTPError as e:
            raise ProviderError(f"anthropic transport error: {e}") from e
        if r.status_code != 200:
            raise ProviderError(f"anthropic {r.status_code}: {r.text[:200]}")
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []))
        usage = data.get("usage", {})
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
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
        }
