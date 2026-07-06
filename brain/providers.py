"""Proveedores LLM (OpenAI-compatible y custom)."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class Provider(ABC):
    """Base abstracta para proveedores LLM."""

    def __init__(
        self,
        name: str,
        api_key: str,
        url: str,
        model: str,
        token_param: str = "max_tokens",
        extra_headers: Optional[Dict] = None,
        extra_body: Optional[Dict] = None
    ):
        """
        Args:
            name: Nombre único (cerebras, groq, hf, openrouter, etc.).
            api_key: API key del proveedor.
            url: URL del endpoint (e.g., https://api.groq.com/openai/v1/chat/completions).
            model: Nombre del modelo (e.g., llama-3.3-70b-versatile).
            token_param: Nombre del parámetro de tokens (max_tokens, max_completion_tokens, etc.).
            extra_headers: Headers adicionales (HTTP-Referer, X-Title, etc.).
            extra_body: Parámetros adicionales en el payload (reasoning_effort, etc.).
        """
        self.name = name
        self.api_key = api_key
        self.url = url
        self.model = model
        self.token_param = token_param
        self.extra_headers = extra_headers or {}
        self.extra_body = extra_body or {}

    def get_headers(self) -> Dict:
        """Headers HTTP para el request."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        headers.update(self.extra_headers)
        return headers

    def get_payload(
        self,
        messages: List,  # List[Message] (pero sin importar para evitar circular)
        max_tokens: int,
        temperature: float
    ) -> Dict:
        """Construir payload JSON para POST."""
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            self.token_param: max_tokens,
            "temperature": temperature,
        }
        payload.update(self.extra_body)
        return payload

    def parse_response(self, response_json: Dict) -> str:
        """
        Extraer contenido de la respuesta del LLM.
        Default: OpenAI-compatible (choices[0].message.content).
        Override en subclases para formatos especiales.
        """
        try:
            msg = response_json["choices"][0]["message"]
            # Modelos con razonamiento (Cerebras): content puede estar vacío, verificar reasoning
            content = msg.get("content") or msg.get("reasoning") or ""
            return content
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Invalid response format: {str(e)}")


class OpenAIProvider(Provider):
    """Proveedor OpenAI-compatible (Groq, OpenRouter, HuggingFace, etc.)."""
    pass  # Hereda toda la lógica de Provider


class CerebrasProvider(Provider):
    """Cerebras: usa max_completion_tokens en lugar de max_tokens."""

    def __init__(self, api_key: str, model: str = "gpt-oss-120b", **kwargs):
        super().__init__(
            name="cerebras",
            api_key=api_key,
            url="https://api.cerebras.ai/v1/chat/completions",
            model=model,
            token_param="max_completion_tokens",
            extra_body={"reasoning_effort": "low"},
            **kwargs
        )


class GroqProvider(Provider):
    """Groq: rápido, gratis en ciertos límites."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile", **kwargs):
        super().__init__(
            name="groq",
            api_key=api_key,
            url="https://api.groq.com/openai/v1/chat/completions",
            model=model,
            **kwargs
        )


class HuggingFaceProvider(Provider):
    """HuggingFace: router gratis, pero tokens limitados/mes."""

    def __init__(self, api_key: str, model: str = "Qwen/Qwen2.5-72B-Instruct", **kwargs):
        super().__init__(
            name="hf",
            api_key=api_key,
            url="https://router.huggingface.co/v1/chat/completions",
            model=model,
            **kwargs
        )


class OpenRouterProvider(Provider):
    """OpenRouter: agregador de modelos, free tier disponible."""

    def __init__(
        self,
        api_key: str,
        model: str = "meta-llama/llama-3.3-70b-instruct:free",
        **kwargs
    ):
        super().__init__(
            name="openrouter",
            api_key=api_key,
            url="https://openrouter.ai/api/v1/chat/completions",
            model=model,
            extra_headers={
                "HTTP-Referer": "https://jarvis.local",
                "X-Title": "Jarvis FOCUS OS"
            },
            **kwargs
        )


def provider_from_dict(config: Dict) -> Provider:
    """Construir un Provider desde dict de config."""
    name = config.get("name", "").lower()
    api_key = config.get("api_key", "")
    url = config.get("url", "")
    model = config.get("model", "")
    token_param = config.get("token_param", "max_tokens")
    extra_headers = config.get("extra_headers", {})
    extra_body = config.get("extra_body", {})

    # Atajos para providers conocidos
    if name == "cerebras":
        return CerebrasProvider(api_key, model, extra_headers=extra_headers, extra_body=extra_body)
    elif name == "groq":
        return GroqProvider(api_key, model, extra_headers=extra_headers, extra_body=extra_body)
    elif name == "hf":
        return HuggingFaceProvider(api_key, model, extra_headers=extra_headers, extra_body=extra_body)
    elif name == "openrouter":
        return OpenRouterProvider(api_key, model, extra_headers=extra_headers, extra_body=extra_body)
    else:
        # Generic OpenAI-compatible
        return OpenAIProvider(
            name=name,
            api_key=api_key,
            url=url,
            model=model,
            token_param=token_param,
            extra_headers=extra_headers,
            extra_body=extra_body
        )
