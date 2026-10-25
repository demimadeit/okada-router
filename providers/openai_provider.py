"""Any OpenAI-compatible cloud API (OpenAI, Groq, Gemini's compat endpoint,
OpenRouter, ...) — parameterized by base_url + key env var.

Two things matter beyond the happy path:
- error classification: a 404/410 means the MODEL is gone, not the network
  (Groq retired models in Aug and Sep 2026 while health checks stayed green);
  a 429 means "stop hammering this free tier", not "retry".
- native SSE streaming, so the gateway can relay tokens as they arrive and
  fail over mid-stream instead of waiting for a whole response.
"""
import json
from typing import AsyncIterator

import httpx

from gateway.providers import (Provider, ProviderError, StreamChunk, classify_http_error,
                               resolve_upstream_key)
from network.simulator import simulator


def _normalize_content(content) -> str:
    """Some servers return content as an array of parts; the gateway speaks
    plain strings."""
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


class OpenAIProvider(Provider):
    kind = "cloud"

    def __init__(self, name: str = "openai",
                 base_url: str = "https://api.openai.com/v1",
                 key_env: str = "OPENAI_API_KEY"):
        super().__init__()
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.key_env = key_env

    def available(self) -> bool:
        return bool(resolve_upstream_key(self.name, self.key_env))

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {resolve_upstream_key(self.name, self.key_env) or ''}"}

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
                r = await client.post(f"{self.base_url}/chat/completions",
                                      headers=self._headers(), json=payload)
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name} transport error: {e}") from e
        if r.status_code != 200:
            raise classify_http_error(self.name, r.status_code, r.text)
        data = r.json()
        for ch in data.get("choices", []):
            msg = ch.get("message") or {}
            msg["content"] = _normalize_content(msg.get("content"))
        return data

    async def chat_stream(self, messages, model, max_tokens,
                          temperature) -> AsyncIterator[StreamChunk]:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        await simulator.impose(payload_bytes=len(str(payload)))
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=60.0)) as client:
                async with client.stream("POST", f"{self.base_url}/chat/completions",
                                         headers=self._headers(), json=payload) as r:
                    if r.status_code != 200:
                        body = (await r.aread()).decode("utf-8", "replace")
                        raise classify_http_error(self.name, r.status_code, body)
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            return
                        try:
                            evt = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        usage = evt.get("usage")
                        choices = evt.get("choices") or []
                        if not choices:
                            if usage:
                                yield StreamChunk(usage=usage, model=evt.get("model", model))
                            continue
                        ch = choices[0]
                        delta = _normalize_content((ch.get("delta") or {}).get("content"))
                        yield StreamChunk(text=delta, finish_reason=ch.get("finish_reason"),
                                          usage=usage, model=evt.get("model", model))
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name} transport error: {e}") from e
