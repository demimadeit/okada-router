"""Local backend chain: prefer llama.cpp (canonical GGUF serving), fall back
to Ollama. The registry sees one 'local' provider; whichever backend is
actually running answers."""
from typing import AsyncIterator

from gateway.providers import Provider, ProviderError, StreamChunk
from providers.llamacpp_provider import LlamaCppProvider
from providers.local_provider import OllamaProvider


class LocalChainProvider(Provider):
    name = "local-chain"
    kind = "local"

    def __init__(self, llamacpp_url: str, ollama_model: str):
        super().__init__()
        self.backends = [
            (LlamaCppProvider(llamacpp_url), "gguf"),
            (OllamaProvider(), ollama_model),
        ]

    def available(self) -> bool:
        return any(p.available() for p, _ in self.backends)

    def active_backend(self):
        for provider, backend_model in self.backends:
            if provider.available():
                return provider, backend_model
        return None, None

    async def chat(self, messages, model, max_tokens, temperature) -> dict:
        last_err = None
        for provider, backend_model in self.backends:
            if not provider.available():
                continue
            try:
                return await provider.chat(messages, backend_model, max_tokens, temperature)
            except Exception as e:
                last_err = e
        raise ProviderError(f"no local backend available: {last_err}")

    async def chat_stream(self, messages, model, max_tokens,
                          temperature) -> AsyncIterator[StreamChunk]:
        provider, backend_model = self.active_backend()
        if provider is None:
            raise ProviderError("no local backend available")
        async for chunk in provider.chat_stream(messages, backend_model, max_tokens, temperature):
            yield chunk
