"""
Brain: Orquestador LLM modular y reutilizable para apps utilitarias.

Ejemplos de uso:
  - Jarvis FOCUS OS (task management + Eisenhower)
  - Password Manager (búsqueda segura vía LLM)
  - Price Assistant (consultas sobre servicios)
  - Knowledge Bot (RAG conversacional)
"""

from .core import Brain, Message, extract_json, provider_configured
from .errors import BrainError, ProviderError, ContextError, PromptError, ConfigError
from .config import (
    BrainConfig,
    BrainProfile,
    ProviderConfig,
    ContextConfig,
    PromptConfig,
    load_config_from_yaml,
    load_config_from_json,
    load_config_from_env,
    get_profile_providers,
)
from .providers import (
    Provider,
    OpenAIProvider,
    KNOWN_PROVIDERS,
    provider_from_dict,
    CerebrasProvider,
    GroqProvider,
    HuggingFaceProvider,
    OpenRouterProvider,
)
from .context import (
    ContextProvider,
    NoContext,
    GoogleSheetsContext,
    SQLiteContext,
    PasswordVaultContext,
    JSONFileContext,
    context_from_dict,
)
from .prompts import (
    PromptLoader,
    YAMLPromptLoader,
    JSONPromptLoader,
    DictPromptLoader,
    loader_from_dict,
)

__version__ = "1.5.3"
__all__ = [
    "Brain",
    "Message",
    "extract_json",
    "provider_configured",
    "BrainError",
    "ProviderError",
    "ContextError",
    "PromptError",
    "ConfigError",
    "BrainConfig",
    "BrainProfile",
    "ProviderConfig",
    "ContextConfig",
    "PromptConfig",
    "load_config_from_yaml",
    "load_config_from_json",
    "load_config_from_env",
    "get_profile_providers",
    "Provider",
    "OpenAIProvider",
    "KNOWN_PROVIDERS",
    "provider_from_dict",
    "CerebrasProvider",
    "GroqProvider",
    "HuggingFaceProvider",
    "OpenRouterProvider",
    "ContextProvider",
    "NoContext",
    "GoogleSheetsContext",
    "SQLiteContext",
    "PasswordVaultContext",
    "JSONFileContext",
    "context_from_dict",
    "PromptLoader",
    "YAMLPromptLoader",
    "JSONPromptLoader",
    "DictPromptLoader",
    "loader_from_dict",
]
