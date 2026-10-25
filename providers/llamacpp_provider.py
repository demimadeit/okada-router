"""Local inference via llama.cpp's llama-server (OpenAI-compatible API).

This is the canonical local backend: GGUF weights served by llama.cpp,
fully offline. Calls do not pass through the network simulator — local
inference is the point.

Port discovery: llama-server's default port moved from 8080 to 9931 in
llama.cpp v0.7.0 (Oct 2026). The gateway itself listens on 8080, so a
from-source user who launches `llama-server` with upstream defaults ends up
on 9931. We try the configured URL first, then 9931, then 8080, and log
which one answered. `/health` must return llama-server's own JSON
({"status": "ok"}) so a stray non-llama service on the port is not mistaken
for a model.
"""
import json
import logging
import time
from typing import AsyncIterator

import httpx

from gateway.providers import Provider, ProviderError, StreamChunk, classify_http_error

log = logging.getLogger("okada.llamacpp")

_AVAILABILITY_TTL_S = 15
FALLBACK_PORTS = (9931, 8080)


def _normalize_content(content) -> str:
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


def _is_llama_health(r: httpx.Response) -> bool:
    if r.status_code != 200:
        return False
    try:
        return r.json().get("status") == "ok"
    except Exception:
        return False


class LlamaCppProvider(Provider):
    name = "llamacpp"
    kind = "local"

    def __init__(self, base_url: str = "http://127.0.0.1:8081"):
        super().__init__()
        self.configured_url = base_url.rstrip("/")
        self.base_url = self.configured_url
        self._available = None
        self._checked_at = 0.0

    def _candidates(self) -> list[str]:
        urls = [self.configured_url]
        host = self.configured_url.rsplit(":", 1)[0] if self.configured_url.count(":") >= 2 \
            else self.configured_url
        for port in FALLBACK_PORTS:
            u = f"{host}:{port}"
            if u not in urls:
                urls.append(u)
        return urls

    def available(self) -> bool:
        now = time.time()
        if self._available is None or (now - self._checked_at) > _AVAILABILITY_TTL_S:
            found = None
            for url in self._candidates():
                try:
                    if _is_llama_health(httpx.get(f"{url}/health", timeout=0.8)):
                        found = url
                        break
                except Exception:
                    continue
            if found and found != self.base_url:
                log.warning("llama-server answered at %s (configured %s); using it",
                            found, self.configured_url)
            if found:
                self.base_url = found
            self._available = found is not None
            self._checked_at = now
        return self._available

    async def chat(self, messages, model, max_tokens, temperature) -> dict:
        payload = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
        except httpx.HTTPError as e:
            raise ProviderError(f"llamacpp transport error: {e}") from e
        if r.status_code != 200:
            raise classify_http_error("llamacpp", r.status_code, r.text)
        data = r.json()
        for ch in data.get("choices", []):
            msg = ch.get("message") or {}
            msg["content"] = _normalize_content(msg.get("content"))
        data["model"] = f"local/{data.get('model', 'gguf')}"
        return data

    async def chat_stream(self, messages, model, max_tokens,
                          temperature) -> AsyncIterator[StreamChunk]:
        payload = {"messages": messages, "max_tokens": max_tokens,
                   "temperature": temperature, "stream": True}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=180.0)) as client:
                async with client.stream("POST", f"{self.base_url}/v1/chat/completions",
                                         json=payload) as r:
                    if r.status_code != 200:
                        body = (await r.aread()).decode("utf-8", "replace")
                        raise classify_http_error("llamacpp", r.status_code, body)
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
                        choices = evt.get("choices") or []
                        usage = evt.get("usage")
                        mdl = f"local/{evt.get('model', 'gguf')}"
                        if not choices:
                            if usage:
                                yield StreamChunk(usage=usage, model=mdl)
                            continue
                        ch = choices[0]
                        yield StreamChunk(
                            text=_normalize_content((ch.get("delta") or {}).get("content")),
                            finish_reason=ch.get("finish_reason"), usage=usage, model=mdl)
        except httpx.HTTPError as e:
            raise ProviderError(f"llamacpp transport error: {e}") from e
