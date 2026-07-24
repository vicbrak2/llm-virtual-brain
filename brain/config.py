"""Configuración de Brain (modelos pydantic + loaders YAML/JSON/env)."""

import os
import re
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class BrainProfile(str, Enum):
    """Perfiles predefinidos de cadenas de providers."""
    FAST = "fast"            # Groq → OpenRouter → HF (rápido + gratis)
    SMART = "smart"          # Cerebras → Groq (reasoning + fallback)
    CHEAP = "cheap"          # OpenRouter:free → HF (solo free)
    RESILIENT = "resilient"  # Todos (máxima resiliencia)


# ── Cadena de providers POR DEFECTO (aplica a todos los agentes si no especifican) ──
# Cambiar aquí afecta a todos los perfiles globalmente.
# Orden: groq (rápido/barato) → openrouter (barato/versátil) → cerebras (razonamiento) → hf (fallback)
DEFAULT_PROVIDERS = [
    {
        "name": "groq",
        "api_key": "${GROQ_API_KEY}",
        "model": "openai/gpt-oss-120b",
    },
    {
        "name": "openrouter",
        "api_key": "${OPENROUTER_API_KEY}",
        "model": "qwen/qwen3-30b-a3b-instruct-2507",
    },
    {
        "name": "cerebras",
        "api_key": "${CEREBRAS_API_KEY}",
        "model": "gpt-oss-120b",
        "extra_body": {
            "reasoning_effort": "high",
        },
    },
    {
        "name": "hf",
        "api_key": "${HF_TOKEN}",
    },
]


class ProviderConfig(BaseModel):
    """Configuración de un proveedor LLM. url/model/token_param son opcionales
    para nombres conocidos (se completan con defaults de KNOWN_PROVIDERS)."""
    name: str
    api_key: str = ""
    url: str = ""
    model: str = ""
    token_param: str = ""
    extra_headers: Dict = Field(default_factory=dict)
    extra_body: Dict = Field(default_factory=dict)


class ContextConfig(BaseModel):
    """Configuración del proveedor de contexto."""
    type: str = "none"  # none, gsheets, sqlite, password_vault, json
    config: Dict = Field(default_factory=dict)


class PromptConfig(BaseModel):
    """Configuración del cargador de prompts."""
    type: str = "dict"  # dict, yaml, json
    config: Dict = Field(default_factory=dict)


class BrainConfig(BaseModel):
    """Configuración completa de Brain."""
    app_name: str = "brain_app"
    profile: Optional[BrainProfile] = None
    providers: List[ProviderConfig] = Field(default_factory=list)
    context: ContextConfig = Field(default_factory=ContextConfig)
    prompts: PromptConfig = Field(default_factory=PromptConfig)
    timeout_seconds: int = 30
    log_level: str = "INFO"


def load_config_from_yaml(yaml_path: str) -> BrainConfig:
    """Cargar configuración desde YAML (con substitución ${VAR} / ${VAR:default}).

    Si el YAML no especifica 'providers', usa DEFAULT_PROVIDERS (centralizado en config.py).
    Esto asegura que todos los agentes usan la misma cadena LLM por defecto.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("load_config_from_yaml requiere PyYAML: pip install pyyaml")

    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Config no encontrada: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Si no hay providers en el YAML, usar DEFAULT_PROVIDERS (cadena centralizada)
    if "providers" not in data or not data["providers"]:
        data["providers"] = DEFAULT_PROVIDERS

    return BrainConfig(**_substitute_env_vars(data))


def load_config_from_json(json_path: str) -> BrainConfig:
    """Cargar configuración desde JSON (con substitución de env vars)."""
    import json as _json

    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Config no encontrada: {path}")

    with open(path, encoding="utf-8") as f:
        data = _json.load(f)

    return BrainConfig(**_substitute_env_vars(data))


def load_config_from_env() -> BrainConfig:
    """Cargar configuración desde variables de entorno.

    BRAIN_APP_NAME, BRAIN_PROVIDERS (JSON list), BRAIN_CONTEXT_TYPE,
    BRAIN_CONTEXT_CONFIG (JSON dict).
    """
    import json as _json

    try:
        providers = [ProviderConfig(**p) for p in _json.loads(os.getenv("BRAIN_PROVIDERS", "[]"))]
    except Exception:
        providers = []

    try:
        context_config = _json.loads(os.getenv("BRAIN_CONTEXT_CONFIG", "{}"))
    except Exception:
        context_config = {}

    return BrainConfig(
        app_name=os.getenv("BRAIN_APP_NAME", "brain_app"),
        providers=providers,
        context=ContextConfig(
            type=os.getenv("BRAIN_CONTEXT_TYPE", "none"),
            config=context_config,
        ),
    )


_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")


def _substitute_env_vars(data):
    """Substituir recursivamente ${VAR} y ${VAR:default} con valores de entorno."""
    if isinstance(data, dict):
        return {k: _substitute_env_vars(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_substitute_env_vars(item) for item in data]
    if isinstance(data, str):
        def replacer(match):
            var, default = match.group(1), match.group(2)
            val = os.getenv(var)
            if val is not None:
                return val
            if default is not None:
                return default
            return match.group(0)  # sin valor ni default → dejar tal cual
        return _ENV_VAR_RE.sub(replacer, data)
    return data


def get_profile_providers(profile: BrainProfile) -> List[Dict]:
    """Cadena de providers sugerida por perfil (las keys van por env)."""
    profiles = {
        BrainProfile.FAST: [{"name": "groq"}, {"name": "openrouter"}, {"name": "hf"}],
        BrainProfile.SMART: [{"name": "cerebras"}, {"name": "groq"}],
        BrainProfile.CHEAP: [{"name": "openrouter"}, {"name": "hf"}],
        BrainProfile.RESILIENT: [
            {"name": "groq"}, {"name": "cerebras"},
            {"name": "openrouter"}, {"name": "hf"}
        ],
    }
    return profiles.get(profile, [])
