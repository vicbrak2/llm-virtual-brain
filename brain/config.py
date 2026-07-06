"""Configuración de Brain (pydantic models + loaders)."""

import os
from enum import Enum
from typing import Dict, List, Optional
from pathlib import Path

try:
    from pydantic import BaseModel, Field, validator
except ImportError:
    # Fallback: usar dataclass si Pydantic no está disponible
    from dataclasses import dataclass as BaseModel
    Field = lambda **kwargs: None
    def validator(*args, **kwargs):
        return lambda f: f


class BrainProfile(str, Enum):
    """Perfiles predefinidos de cadenas de providers."""
    FAST = "fast"           # Groq → OpenRouter → HF (rápido + gratis)
    SMART = "smart"         # Cerebras → Groq (reasoning + fallback)
    CHEAP = "cheap"         # OpenRouter:free → HF (solo free)
    RESILIENT = "resilient" # Todos (máxima resiliencia)


class ProviderConfig(BaseModel):
    """Configuración de un proveedor LLM."""
    name: str
    api_key: str
    url: str
    model: str
    token_param: str = "max_tokens"
    extra_headers: Dict = {}
    extra_body: Dict = {}

    class Config:
        use_enum_values = True


class ContextConfig(BaseModel):
    """Configuración del proveedor de contexto."""
    type: str = "none"  # none, gsheets, sqlite, password_vault, json
    config: Dict = {}   # Parámetros específicos del tipo


class PromptConfig(BaseModel):
    """Configuración del cargador de prompts."""
    type: str = "dict"  # dict, yaml, json
    config: Dict = {}   # Parámetros específicos del tipo


class BrainConfig(BaseModel):
    """Configuración completa de Brain."""
    app_name: str = Field(default="brain_app", description="Nombre de la aplicación")
    profile: Optional[BrainProfile] = None
    providers: List[ProviderConfig] = Field(default_factory=list)
    context: ContextConfig = Field(default_factory=lambda: ContextConfig())
    prompts: PromptConfig = Field(default_factory=lambda: PromptConfig())
    timeout_seconds: int = 30
    log_level: str = "INFO"

    class Config:
        use_enum_values = True


def load_config_from_yaml(yaml_path: str) -> BrainConfig:
    """Cargar configuración desde archivo YAML."""
    try:
        import yaml
    except ImportError:
        raise ImportError("load_config_from_yaml requires PyYAML: pip install pyyaml")

    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Config file not found: {yaml_path}")

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    # Substituir variables de entorno (${VAR_NAME})
    data = _substitute_env_vars(data)

    return BrainConfig(**data)


def load_config_from_json(json_path: str) -> BrainConfig:
    """Cargar configuración desde archivo JSON."""
    import json

    json_path = Path(json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"Config file not found: {json_path}")

    with open(json_path) as f:
        data = json.load(f)

    # Substituir variables de entorno
    data = _substitute_env_vars(data)

    return BrainConfig(**data)


def load_config_from_env() -> BrainConfig:
    """Cargar configuración desde variables de entorno."""
    import json

    providers_json = os.getenv("BRAIN_PROVIDERS", "[]")
    try:
        providers = [ProviderConfig(**p) for p in json.loads(providers_json)]
    except:
        providers = []

    context_json = os.getenv("BRAIN_CONTEXT_CONFIG", "{}")
    context_config = json.loads(context_json)

    return BrainConfig(
        app_name=os.getenv("BRAIN_APP_NAME", "brain_app"),
        providers=providers,
        context=ContextConfig(
            type=os.getenv("BRAIN_CONTEXT_TYPE", "none"),
            config=context_config
        )
    )


def _substitute_env_vars(data):
    """Recursivamente substituir ${VAR_NAME} con valores de entorno."""
    if isinstance(data, dict):
        return {k: _substitute_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_substitute_env_vars(item) for item in data]
    elif isinstance(data, str):
        # Buscar ${VAR_NAME} y substituir
        import re
        def replacer(match):
            var_name = match.group(1)
            return os.getenv(var_name, match.group(0))  # Si no existe, dejar como está
        return re.sub(r'\$\{([^}]+)\}', replacer, data)
    else:
        return data


def get_profile_providers(profile: BrainProfile) -> List[Dict]:
    """Retornar configuración de providers por perfil."""
    profiles = {
        BrainProfile.FAST: [
            {"name": "groq"},
            {"name": "openrouter"},
            {"name": "hf"}
        ],
        BrainProfile.SMART: [
            {"name": "cerebras"},
            {"name": "groq"}
        ],
        BrainProfile.CHEAP: [
            {"name": "openrouter"},
            {"name": "hf"}
        ],
        BrainProfile.RESILIENT: [
            {"name": "cerebras"},
            {"name": "groq"},
            {"name": "openrouter"},
            {"name": "hf"}
        ]
    }
    return profiles.get(profile, [])
