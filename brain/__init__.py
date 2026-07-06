"""
Brain: Orquestador LLM modular y reutilizable para apps utilitarias.

Ejemplos de uso:
  - Jarvis FOCUS OS (task management + Eisenhower)
  - Password Manager (búsqueda segura vía LLM)
  - Price Assistant (consultas sobre servicios)
  - Knowledge Bot (RAG conversacional)
"""

from .core import Brain, BrainError
from .config import BrainConfig, BrainProfile, ProviderConfig, load_config_from_yaml, load_config_from_env
from .providers import Provider, OpenAIProvider
from .context import ContextProvider, NoContext, GoogleSheetsContext, SQLiteContext, PasswordVaultContext
from .prompts import PromptLoader, YAMLPromptLoader, JSONPromptLoader, DictPromptLoader

__version__ = "1.0.0"
__all__ = [
    "Brain",
    "BrainError",
    "BrainConfig",
    "BrainProfile",
    "ProviderConfig",
    "Provider",
    "OpenAIProvider",
    "ContextProvider",
    "NoContext",
    "GoogleSheetsContext",
    "SQLiteContext",
    "PasswordVaultContext",
    "PromptLoader",
    "YAMLPromptLoader",
    "JSONPromptLoader",
    "DictPromptLoader",
    "load_config_from_yaml",
    "load_config_from_env",
]
