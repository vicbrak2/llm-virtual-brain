"""Proveedores LLM (OpenAI-compatible y custom)."""

from typing import Dict, List, Optional


class Provider:
    """Proveedor LLM OpenAI-compatible (Groq, Cerebras, OpenRouter, HF, etc.)."""

    def __init__(
        self,
        name: str,
        api_key: str,
        url: str,
        model: str,
        token_param: str = "max_tokens",
        extra_headers: Optional[Dict] = None,
        extra_body: Optional[Dict] = None,
    ):
        """
        Args:
            name: Nombre único (cerebras, groq, hf, openrouter, etc.).
            api_key: API key del proveedor.
            url: URL del endpoint de chat completions.
            model: Nombre del modelo.
            token_param: Nombre del parámetro de tokens (max_tokens, max_completion_tokens).
            extra_headers: Headers adicionales (HTTP-Referer, X-Title, etc.).
            extra_body: Parámetros extra en el payload (reasoning_effort, etc.).
        """
        self.name = name
        self.api_key = api_key
        self.url = url
        self.model = model
        self.token_param = token_param
        self.extra_headers = extra_headers or {}
        self.extra_body = extra_body or {}

    def get_headers(self) -> Dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)
        return headers

    def get_payload(self, messages: List, max_tokens: int, temperature: float) -> Dict:
        payload = {
            "model": self.model,
            "messages": [
                m if isinstance(m, dict) else {"role": m.role, "content": m.content}
                for m in messages
            ],
            self.token_param: max_tokens,
            "temperature": temperature,
        }
        payload.update(self.extra_body)
        return payload

    def parse_response(self, response_json: Dict) -> str:
        """Extraer contenido. Modelos de razonamiento (Cerebras) pueden dejar
        content vacío y todo en reasoning — se acepta cualquiera de los dos."""
        try:
            msg = response_json["choices"][0]["message"]
            return msg.get("content") or msg.get("reasoning") or ""
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Formato de respuesta inválido: {e}")

    def __repr__(self):
        return f"Provider(name={self.name!r}, model={self.model!r})"


# Alias retro-compatible: todo provider por defecto es OpenAI-compatible.
OpenAIProvider = Provider


# Defaults de providers conocidos. Cualquier campo puede overridearse desde config.
KNOWN_PROVIDERS: Dict[str, Dict] = {
    "cerebras": {
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "model": "gpt-oss-120b",
        "token_param": "max_completion_tokens",
        "extra_body": {"reasoning_effort": "low"},
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        # llama-3.3-70b-versatile fue deprecado por Groq; gpt-oss-120b es el reemplazo recomendado
        "model": "openai/gpt-oss-120b",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        # gemini-2.0-flash fue apagado (jun 2026); 3.5-flash es el estable del free tier
        "model": "gemini-3.5-flash",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "mistral": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "model": "mistral-small-latest",
    },
    "hf": {
        "url": "https://router.huggingface.co/v1/chat/completions",
        "model": "Qwen/Qwen2.5-72B-Instruct",
    },
}


def provider_from_dict(config: Dict) -> Provider:
    """
    Construir un Provider desde un dict de config.

    Acepta alias comunes: `key` → `api_key`, `headers` → `extra_headers`.
    Para nombres conocidos (cerebras, groq, hf, openrouter, gemini, mistral)
    aplica defaults de url/model/token_param que el dict puede overridear.
    """
    cfg = dict(config)

    # Normalizar alias
    if "key" in cfg and "api_key" not in cfg:
        cfg["api_key"] = cfg.pop("key")
    if "headers" in cfg and "extra_headers" not in cfg:
        cfg["extra_headers"] = cfg.pop("headers")

    name = (cfg.get("name") or "custom").lower()
    defaults = KNOWN_PROVIDERS.get(name, {})

    def pick(field, fallback=None):
        val = cfg.get(field)
        if val in (None, "", {}):
            val = defaults.get(field, fallback)
        return val

    return Provider(
        name=name,
        api_key=cfg.get("api_key", ""),
        url=pick("url", ""),
        model=pick("model", ""),
        token_param=pick("token_param", "max_tokens"),
        extra_headers=pick("extra_headers", {}) or {},
        extra_body=pick("extra_body", {}) or {},
    )


# Atajos convenientes (retro-compat con la API anterior de clases)
def CerebrasProvider(api_key: str, model: str = "gpt-oss-120b", **kwargs) -> Provider:
    return provider_from_dict({"name": "cerebras", "api_key": api_key, "model": model, **kwargs})


def GroqProvider(api_key: str, model: str = "llama-3.3-70b-versatile", **kwargs) -> Provider:
    return provider_from_dict({"name": "groq", "api_key": api_key, "model": model, **kwargs})


def HuggingFaceProvider(api_key: str, model: str = "Qwen/Qwen2.5-72B-Instruct", **kwargs) -> Provider:
    return provider_from_dict({"name": "hf", "api_key": api_key, "model": model, **kwargs})


def OpenRouterProvider(
    api_key: str, model: str = "meta-llama/llama-3.3-70b-instruct:free", **kwargs
) -> Provider:
    return provider_from_dict({"name": "openrouter", "api_key": api_key, "model": model, **kwargs})
