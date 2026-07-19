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

    def parse_response(self, response_json: Dict) -> tuple:
        """Extraer (contenido, truncado). `truncado=True` cuando
        finish_reason=="length": el llamador decide si continuar la
        generación o rotar de provider.

        Modelos de razonamiento (Cerebras con reasoning_effort alto, etc.)
        a veces dejan "content" vacío y ponen todo en "reasoning" — pero ese
        campo es el borrador interno del modelo (a menudo en inglés, sin
        pulir, con frases tipo "the user is asking..."), NO una respuesta
        para el usuario. Antes se aceptaba como fallback y se mostraba tal
        cual en el chat; ahora se trata igual que un truncamiento: se falla
        y se rota al siguiente provider en vez de mostrar razonamiento crudo."""
        try:
            choice = response_json["choices"][0]
            msg = choice["message"]
            content = msg.get("content") or ""
            truncated = choice.get("finish_reason") == "length"
            if content.strip():
                return content, truncated
            detail = ("truncado por max_tokens en pleno razonamiento" if truncated
                      else "sin content (el modelo dejó todo en 'reasoning' interno, no es una respuesta)")
            raise ValueError(f"{detail} (sin content)")
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
        # llama-3.3-70b-versatile se apaga el 16-ago-2026 (deprecado por Groq).
        # gpt-oss-120b: mismo precio de tier gratis (30 RPM/1K RPD/8K TPM/200K TPD)
        # pero de pago sale mas barato que el resto de la cadena ($0.15/$0.60 por
        # M de tokens) y no tiene fecha de apagado — migrado 2026-07.
        "model": "openai/gpt-oss-120b",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        # gemini-2.0-flash fue apagado (jun 2026); 3.5-flash es el estable del free tier
        "model": "gemini-3.5-flash",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        # De pago (sin :free): $0.08/$0.45 por M tokens, mas barato que el resto
        # de la cadena y sin los 429 del tier gratis compartido. Si la cuenta no
        # tiene saldo, la llamada falla y la cadena rota a cerebras/hf (gratis).
        "model": "nvidia/nemotron-3-super-120b-a12b",
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
    api_key: str, model: str = "nvidia/nemotron-3-ultra-550b-a55b:free", **kwargs
) -> Provider:
    return provider_from_dict({"name": "openrouter", "api_key": api_key, "model": model, **kwargs})
