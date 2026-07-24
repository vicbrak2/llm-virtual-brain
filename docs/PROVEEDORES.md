# Configuración Centralizada de Proveedores LLM

**Todos los agentes usan la misma cadena de providers** a menos que sobrescriban explícitamente en su YAML.

## Cadena por defecto

Definida en `brain/config.py`:

```python
DEFAULT_PROVIDERS = [
    {
        "name": "groq",
        "model": "openai/gpt-oss-120b",      # Rápido, gratis (100 requests/min)
    },
    {
        "name": "openrouter",
        "model": "mistralai/mistral-small-3.2-24b-instruct",  # Barato ($0.08/$0.45 por M)
    },
    {
        "name": "cerebras",
        "model": "gemma-4-31b",              # Razonamiento (fallback a reasoning_effort: high)
        "extra_body": {"reasoning_effort": "high"},
    },
    {
        "name": "hf",                        # Fallback universal (HuggingFace)
    },
]
```

## Cambiar globalmente

**Opción 1: Editar `brain/config.py`**

Modifica `DEFAULT_PROVIDERS` directamente. Afecta a TODOS los agentes que no especifiquen providers.

```python
DEFAULT_PROVIDERS = [
    {"name": "cerebras", "model": "gemma-4-31b", ...},  # Prioritario
    {"name": "groq", "model": "...", ...},
    ...
]
```

Reinicia Brain Server → todos los perfiles usan la nueva cadena.

**Opción 2: Sobreescribir en un YAML específico**

Un agente puede definir sus propios providers, ignorando los default:

```yaml
# profiles/custom_agent.yaml
description: Mi agente personalizado
app_name: custom_app

providers:
  - name: "grok"
    api_key: "${GROK_API_KEY}"
    model: "grok-2"
```

Este agente usa solo Grok. Otros usan DEFAULT_PROVIDERS.

## Agregar un nuevo modelo

1. Actualiza `DEFAULT_PROVIDERS` en `brain/config.py`:

```python
DEFAULT_PROVIDERS = [
    {
        "name": "groq",
        "api_key": "${GROQ_API_KEY}",
        "model": "openai/gpt-oss-120b",
    },
    {
        "name": "claude",  # NUEVO
        "api_key": "${ANTHROPIC_API_KEY}",
        "url": "https://api.anthropic.com/v1/messages",
        "model": "claude-3.5-sonnet",
    },
    ...
]
```

2. Agrega la variable de entorno en Railway o `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

3. Reinicia Brain Server.

Todos los agentes sin providers explícitos usan la nueva cadena.

## Registrar el cambio

Cada cambio a DEFAULT_PROVIDERS debe commitear con una descripción clara:

```bash
git commit -m "feat: agregar Claude 3.5 como segundo provider

DEFAULT_PROVIDERS ahora: groq (rápido) → claude (reasoning) → openrouter (barato)
Todos los agentes heredan este cambio automáticamente.
"
```

## Verificar qué providers está usando un agente

**En Brain Server:**

```bash
curl http://localhost:8888/api/profiles | jq '.[] | {name, providers}'
```

Cada perfil lista sus providers en orden de rotación.

**En logs:**

```
[brain] rotación dinámica → cerebras (gemma-4-31b)
```

Si es DEFAULT_PROVIDERS: va primero groq, si falla → openrouter, etc.

## Notas

- **Orden importa**: la cadena intenta providers en orden. Si groq falla (402/timeout), rota a openrouter.
- **Caché de respuestas**: Brain cachea por provider + prompt. Cambiar providers NO invalida cache; la próxima respuesta es "fresca".
- **Granularidad**: cada agente puede sobrescribir; no hay "herencia parcial" (es todo o nada).
- **Env vars**: si falta una API key para un provider en la cadena, ese provider se salta (no bloquea).

## Historial de cambios (v1.5.2+)

| Versión | Cambio | Razón |
|---------|--------|-------|
| v1.5.2  | Centralizar providers en config.py | Consistencia global, fácil cambio |
| v1.5.1  | groq + openrouter + cerebras + hf | Orden por costo/velocidad/resiliencia |
