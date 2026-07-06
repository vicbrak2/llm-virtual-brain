"""Excepciones custom de Brain."""

class BrainError(Exception):
    """Error general de Brain (todos los providers fallaron, config inválida, etc.)."""
    pass

class ProviderError(BrainError):
    """Error específico de un provider (timeout, 401, 402, etc.)."""
    pass

class ContextError(BrainError):
    """Error cargando/enriqueciendo contexto."""
    pass

class PromptError(BrainError):
    """Error cargando o parseando prompts."""
    pass

class ConfigError(BrainError):
    """Error en configuración (archivo no encontrado, formato inválido, etc.)."""
    pass
