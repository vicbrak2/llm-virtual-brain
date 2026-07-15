# 🧠 Brain: Orquestador LLM Modular

Librería reutilizable para construir apps utilitarias con LLM conversacional, contexto dinámico y rotación resiliente de providers.

## 🎯 Casos de Uso

- 📋 **Task Manager** (Jarvis FOCUS OS)
- 💰 **Price Assistant** (consultar servicios desde Sheets)
- 🔐 **Password Manager** (acceso seguro a bóveda via chat)
- 📚 **Knowledge Bot** (RAG sobre documentos)
- 🏥 **Health Companion** (recordatorios + medicinas)

## 📦 Instalación

### Opción 1: Como módulo local

```bash
cd jarvis-backend
python -c "from brain import Brain; print(Brain.__doc__)"
```

### Opción 2: Como paquete pip (futuro)

```bash
pip install brain-llm
```

## 🚀 Uso Rápido

```python
from brain import Brain, load_config_from_yaml

# Cargar configuración
brain = Brain(load_config_from_yaml("config.yaml"))

# Pensar (consultar LLM)
response = await brain.think(
    user_msg="agregar compra de leche para mañana",
    context_data={"tasks": [...]},
    stage_name="formatter"
)

# Con JSON
result = await brain.think_json(
    user_msg="analizar tareas",
    context_data={...},
    stage_name="analyzer"
)
```

## 📋 Configuración (YAML)

```yaml
app_name: "mi_app"
profile: "smart"  # fast, smart, cheap, resilient

providers:
  - name: "groq"
    api_key: "${GROQ_API_KEY}"
    url: "https://api.groq.com/openai/v1/chat/completions"
    model: "llama-3.3-70b-versatile"
  
  - name: "hf"
    api_key: "${HF_TOKEN}"
    url: "https://router.huggingface.co/v1/chat/completions"
    model: "Qwen/Qwen2.5-72B-Instruct"

context:
  type: "gsheets"
  config:
    sheet_id: "${PRICES_SHEET_ID}"
    service_account_json: "/secrets/google-service.json"

prompts:
  type: "yaml"
  config:
    path: "prompts.yaml"

timeout_seconds: 30
log_level: "INFO"
```

### Variables de Entorno

Brain substituye automáticamente `${VAR_NAME}` con valores de entorno:

```bash
export GROQ_API_KEY="gsk_..."
export HF_TOKEN="hf_..."
# Brain loaderá estos valores en la config YAML
```

## 🧩 Componentes

### Brain Core

Orquestador principal: maneja providers, contexto, prompts.

```python
brain = Brain(
    providers=[...],
    context_provider=context,
    prompt_loader=prompts,
    app_name="mi_app"
)

# Pensar
response = await brain.think(user_msg, context_data, stage_name="default")

# Pensar JSON
data = await brain.think_json(user_msg, context_data, stage_name="analyzer")

# Multi-etapa (formatter → analyzer)
result = await brain.think_multi_stage(
    user_msg,
    stages=["formatter", "analyzer"]
)

# Estado
status = brain.status()  # {active, providers, ...}
```

### Providers

Proveedores LLM (OpenAI-compatible).

```python
from brain.providers import (
    CerebrasProvider, GroqProvider, HuggingFaceProvider,
    OpenRouterProvider, provider_from_dict
)

# Directo
groq = GroqProvider(api_key="gsk_...")

# Desde config dict
providers = [
    provider_from_dict({
        "name": "groq",
        "api_key": "gsk_...",
        "url": "...",
        "model": "..."
    })
]
```

### Context Providers

Enriquecedores de datos (Sheets, SQL, vault, JSON).

```python
from brain.context import (
    GoogleSheetsContext, SQLiteContext, PasswordVaultContext,
    JSONFileContext, NoContext, context_from_dict
)

# Google Sheets
ctx = GoogleSheetsContext(
    sheet_id="1ABC...",
    service_account_json="/secrets/google-service.json"
)

# SQLite
ctx = SQLiteContext(
    db_path="data.db",
    queries={"users": "SELECT id, name FROM users LIMIT 10"}
)

# Password Vault (sin exponer contraseñas)
ctx = PasswordVaultContext(vault_path="/secure/vault.json")

# Desde config
ctx = context_from_dict({
    "type": "gsheets",
    "sheet_id": "...",
    "service_account_json": "..."
})
```

### Prompt Loaders

Cargadores de prompts (YAML, JSON, en-memoria).

```python
from brain.prompts import (
    YAMLPromptLoader, JSONPromptLoader, DictPromptLoader,
    loader_from_dict
)

# YAML
prompts = YAMLPromptLoader("prompts.yaml")

# En-memoria
prompts = DictPromptLoader({
    "formatter": "Limpia input...",
    "analyzer": "Analiza profundamente..."
})

# Desde config
prompts = loader_from_dict({
    "type": "yaml",
    "path": "prompts.yaml"
})
```

## 📝 Ejemplos

### Ejemplo 1: Task Manager (Jarvis)

**config.yaml:**
```yaml
app_name: "jarvis_focus_os"
profile: "smart"

providers:
  - name: "cerebras"
    api_key: "${CEREBRAS_API_KEY}"
    model: "gpt-oss-120b"
  - name: "groq"
    api_key: "${GROQ_API_KEY}"
    model: "llama-3.3-70b-versatile"

context:
  type: "none"  # Custom context en app.py

prompts:
  type: "yaml"
  config:
    path: "prompts_jarvis.yaml"
```

**main.py:**
```python
from brain import Brain, load_config_from_yaml

brain = Brain(load_config_from_yaml("config.yaml"))

@app.post("/chat")
async def chat(msg: str, tasks: list):
    # Etapa 1: Formatter
    pre = await brain.think(msg, {"tasks": tasks}, stage_name="formatter")
    
    # Etapa 2: Analyzer
    result = await brain.think_json(
        pre,
        {"tasks": tasks},
        stage_name="analyzer"
    )
    return result
```

### Ejemplo 2: Price Assistant

**config.yaml:**
```yaml
app_name: "price_assistant"
profile: "cheap"

providers:
  - name: "openrouter"
    api_key: "${OPENROUTER_API_KEY}"
    model: "nvidia/nemotron-3-ultra-550b-a55b:free"

context:
  type: "gsheets"
  config:
    sheet_id: "${PRICES_SHEET_ID}"
    service_account_json: "/secrets/google-service.json"

prompts:
  type: "yaml"
  config:
    path: "prompts_prices.yaml"
```

**main.py:**
```python
from brain import Brain, load_config_from_yaml

brain = Brain(load_config_from_yaml("config.yaml"))

@app.post("/ask")
async def ask(query: str):
    # Brain enriquece automáticamente con datos de Sheets
    response = await brain.think(query, stage_name="query")
    return {"answer": response}
```

### Ejemplo 3: Password Manager

**config.yaml:**
```yaml
app_name: "password_manager"
profile: "smart"

providers:
  - name: "groq"
    api_key: "${GROQ_API_KEY}"

context:
  type: "password_vault"
  config:
    vault_path: "/secure/vault.json"

prompts:
  type: "yaml"
  config:
    path: "prompts_passwords.yaml"
```

**main.py:**
```python
from brain import Brain, load_config_from_yaml

brain = Brain(load_config_from_yaml("config.yaml"))

@app.post("/search")
async def search(query: str):
    # Brain NO expone contraseñas, solo sugerencias
    response = await brain.think(query, stage_name="search")
    return {"suggestion": response}
```

## 🔄 Flujo de Pensamiento

```
User Input
    ↓
[1] Cargar Prompt (por stage_name)
    ↓
[2] Enriquecer Contexto (si ContextProvider)
    ↓
[3] Construir Messages (system + context + user)
    ↓
[4] Llamar Providers en Cadena
    ├─ Intenta provider #1
    ├─ Si falla → intenta provider #2
    ├─ Si falla → intenta provider #3
    └─ Si todas fallan → BrainError
    ↓
[5] Parsear Respuesta (content o reasoning)
    ↓
[6] Retornar Response
    ↓
Opcional: [7] Parsecar JSON si think_json()
```

## 🎯 Multi-Etapa

Chain multiple etapas secuencialmente:

```python
result = await brain.think_multi_stage(
    user_msg="agregar compra de leche",
    stages=["formatter", "analyzer", "custom_stage"]
)
```

**Flujo:**
1. `formatter`: limpia input, detecta intent
2. `analyzer`: análisis profundo (toma output del formatter)
3. `custom_stage`: otra etapa personalizada

## 🔗 Rotación Dinámica

Brain recuerda qué provider respondió bien (sticky):

```
Llamada #1 → Intenta Groq (OK) → Sticky a Groq
Llamada #2 → Intenta Groq primero (OK) → Sigue con Groq
Llamada #3 → Groq falla → Rota a OpenRouter (OK) → Sticky a OpenRouter
Llamada #4 → Intenta OpenRouter primero (OK) → Sigue con OpenRouter
```

Evita reintentar providers caídos en cada llamada.

## 📊 Status

```python
status = brain.status()
# {
#   "app": "mi_app",
#   "active": "groq",  # Último que respondió OK
#   "providers_count": 4,
#   "providers": [
#     {"order": 0, "name": "cerebras", "model": "gpt-oss-120b"},
#     {"order": 1, "name": "groq", "model": "llama-3.3-70b-versatile"},
#     ...
#   ]
# }
```

## 🔐 Seguridad

### PasswordVaultContext

- **Expone:** categorías, nombres, hints
- **NO expone:** contraseñas
- Ejemplo: "Tienes 2 emails guardados. ¿Cuál buscas?"

### API Keys

- Almacenar en `.env` o variables de entorno
- Brain las substituye en YAML (`${VAR_NAME}`)
- **Nunca** commitear `.env` al repo

## 🐛 Troubleshooting

### "Todos los providers fallaron"

1. Verificar API keys (`brain.status()`)
2. Verificar conectividad
3. Revisar límites de tokens/rate limiting
4. Ver logs: `log_level: "DEBUG"` en config

### "No valid JSON found in response"

1. El LLM no retornó JSON válido
2. Aumentar `max_tokens` o cambiar `temperature`
3. Probar con otro provider

### "Context enrichment failed"

1. Verificar credenciales (Sheets, SQLite, etc.)
2. Verificar que el recurso existe
3. Brain continúa sin contexto (no falla)

## 📚 API Reference

### `Brain.think()`

```python
async def think(
    user_msg: str,
    context_data: Optional[Dict] = None,
    max_tokens: int = 600,
    temperature: float = 0.2,
    stage_name: str = "default"
) -> str
```

Pensar (consultar LLM) sobre un mensaje.

### `Brain.think_json()`

```python
async def think_json(
    user_msg: str,
    context_data: Optional[Dict] = None,
    max_tokens: int = 900,
    temperature: float = 0.0,
    stage_name: str = "default"
) -> Dict
```

Pensar y parsear JSON automáticamente.

### `Brain.think_multi_stage()`

```python
async def think_multi_stage(
    user_msg: str,
    stages: List[str],
    context_data: Optional[Dict] = None
) -> str
```

Ejecutar múltiples etapas secuencialmente.

### `Brain.status()`

```python
def status() -> Dict
```

Obtener estado de providers + último activo.

## 🚀 Próximos Pasos

1. Crear `config.yaml` para tu app
2. Crear `prompts.yaml` con tus stages
3. Instanciar `Brain` en tu `main.py`
4. Llamar `await brain.think()` desde tus endpoints

## 📖 Documentación Completa

Ver: `../BRAIN_MODULAR_ARQUITECTURA.md`

---

**Versión:** 1.0.0
**Licencia:** MIT
