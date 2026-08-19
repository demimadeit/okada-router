"""Local backend chain: prefer llama.cpp (ADTC-compliant GGUF serving),
fall back to Ollama. The registry sees one 'local' provider; whichever
backend is actually running answers."""
from gateway.providers import Provider, ProviderError
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
