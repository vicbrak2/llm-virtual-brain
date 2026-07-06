# 🧠 LLM Virtual Brain

**Modular, parameterizable LLM orchestrator for building intelligent utility apps with multi-provider resilience, dynamic context, and composable stages.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/downloads/)
[![GitHub](https://img.shields.io/badge/GitHub-vicbrak2%2Fllm--virtual--brain-black)](https://github.com/vicbrak2/llm-virtual-brain)

## 🎯 What is Virtual Brain?

A Python library that abstracts multi-LLM orchestration, context enrichment, and conversational logic into a **single, reusable `Brain` class**. Build AI-powered apps without rewriting the LLM plumbing.

### 📋 Use Cases

- 📝 **Task Manager** — Jarvis FOCUS OS (TDA/ADHD assistant)
- 💰 **Price Assistant** — Query services from Google Sheets via chat
- 🔐 **Password Manager** — Secure vault access without exposing secrets
- 📚 **Knowledge Bot** — RAG conversational interface
- 🏥 **Health Companion** — Medication reminders + natural conversation

## ✨ Key Features

| Feature | Benefit |
|---|---|
| **Multi-Provider** | Cerebras → Groq → OpenRouter → HF (fallback chain) |
| **Dynamic Rotation** | If provider fails, auto-switch (no re-prompting) |
| **Sticky State** | Remembers which provider responded last → avoids dead providers |
| **Modular** | Same Brain code, different apps (change config only) |
| **Context Pluggable** | Google Sheets, SQLite, Password Vault, JSON, custom |
| **Multi-Stage** | Chain formatter → analyzer → custom (composable) |
| **Parameterizable** | YAML/JSON config (no code changes for new apps) |
| **Zero Lock-In** | Each provider is OpenAI-compatible REST (swap freely) |

## 🚀 Quick Start

### 1. Install

```bash
pip install llm-virtual-brain
```

Or with Google Sheets support:

```bash
pip install llm-virtual-brain[gsheets]
```

### 2. Create Config

**config.yaml:**
```yaml
app_name: "my_app"
profile: "smart"  # fast, smart, cheap, resilient

providers:
  - name: "groq"
    api_key: "${GROQ_API_KEY}"
    model: "llama-3.3-70b-versatile"
  
  - name: "openrouter"
    api_key: "${OPENROUTER_API_KEY}"
    model: "meta-llama/llama-3.3-70b-instruct:free"

context:
  type: "gsheets"
  config:
    sheet_id: "${PRICES_SHEET_ID}"
    service_account_json: "/secrets/google-service.json"

prompts:
  type: "yaml"
  config:
    path: "prompts.yaml"
```

### 3. Create Prompts

**prompts.yaml:**
```yaml
prompts:
  formatter: |
    Clean input and detect intent.
    Respond JSON: {"intent": "...", "text": "..."}
  
  analyzer: |
    Analyze deeply and plan actions.
    Respond JSON with steps and reasoning.
```

### 4. Use in Code

```python
from brain import Brain, load_config_from_yaml

# Initialize
brain = Brain(load_config_from_yaml("config.yaml"))

# Think (query LLM)
response = await brain.think(
    user_msg="What services do you offer?",
    context_data={"datetime": "2026-07-05 15:30"},
    stage_name="analyzer"
)

# Think & parse JSON
data = await brain.think_json(
    user_msg="...",
    context_data={...},
    stage_name="analyzer"
)

# Check status
status = brain.status()
# {active: "groq", providers_count: 2, ...}
```

## 📚 Documentation

- **[Architecture](docs/ARCHITECTURE.md)** — Design + components
- **[API Reference](docs/API.md)** — Full function signatures
- **[Examples](examples/)** — Price Assistant, Password Manager, Knowledge Bot
- **[Configuration Guide](docs/CONFIG.md)** — YAML format + context + providers

## 💡 Architecture

```
User Input
    ↓
[1] Load Prompt (by stage_name)
    ↓
[2] Enrich Context (Sheets, SQL, etc.)
    ↓
[3] Build Messages (system + context + user)
    ↓
[4] Call Providers in Chain
    ├─ Try provider #1 → OK? Return
    ├─ Fail → Try provider #2
    ├─ Fail → Try provider #3
    └─ All fail → BrainError
    ↓
[5] Parse Response (content or reasoning)
    ↓
[6] Return Response
    ↓
[7] Optional: Parse JSON (if think_json())
```

## 🔧 Components

### Brain

Main orchestrator:
```python
from brain import Brain

brain = Brain(
    providers=[...],
    context_provider=context,
    prompt_loader=prompts,
    app_name="my_app"
)
```

### Providers

OpenAI-compatible (Groq, OpenRouter, Cerebras, HuggingFace):
```python
from brain.providers import GroqProvider, OpenRouterProvider

providers = [
    GroqProvider(api_key="gsk_..."),
    OpenRouterProvider(api_key="sk-or-..."),
]
```

### Context

Enrich LLM with external data:
```python
from brain.context import GoogleSheetsContext, SQLiteContext, NoContext

context = GoogleSheetsContext(
    sheet_id="1ABC...",
    service_account_json="/secrets/google-service.json"
)
```

### Prompts

Load prompts from YAML, JSON, or dict:
```python
from brain.prompts import YAMLPromptLoader

prompts = YAMLPromptLoader("prompts.yaml")
prompt_text = prompts.get("formatter")
```

## 🎯 Multi-Stage Example

**Formatter → Analyzer pattern:**

```python
# Stage 1: Quick formatter (cleanup + intent)
pre = await brain.think(
    user_msg,
    context_data=context,
    max_tokens=200,
    temperature=0.1,
    stage_name="formatter"
)

# Stage 2: Deep analyzer (full reasoning)
result = await brain.think_json(
    pre,  # Feed formatter output
    context_data=context,
    max_tokens=700,
    temperature=0.3,
    stage_name="analyzer"
)

# Or one-liner:
result = await brain.think_multi_stage(
    user_msg,
    stages=["formatter", "analyzer"]
)
```

## 🔐 Context Providers

### Google Sheets
```python
GoogleSheetsContext(
    sheet_id="1ABC...",
    service_account_json="/path/to/google-service.json",
    worksheet_name="Prices"
)
```

### SQLite
```python
SQLiteContext(
    db_path="data.db",
    queries={"users": "SELECT * FROM users LIMIT 10"}
)
```

### Password Vault (Secure)
```python
# Vault structure: {category: [{name, username, hint}, ...]}
# NEVER exposes passwords, only structure
PasswordVaultContext(vault_path="/secure/vault.json")
```

### Custom
```python
from brain.context import ContextProvider

class MyContext(ContextProvider):
    async def enrich(self, user_msg: str, current_data: dict) -> dict:
        # Fetch data, add to current_data
        current_data["my_field"] = await fetch_external_api()
        return current_data
```

## 🌍 Environment Variables

Brain auto-substitutes `${VAR_NAME}` in YAML:

```yaml
providers:
  - name: "groq"
    api_key: "${GROQ_API_KEY}"  # Loaded from env at init
    model: "${GROQ_MODEL:llama-3.3-70b-versatile}"  # Default if not set
```

```bash
export GROQ_API_KEY="gsk_..."
export GROQ_MODEL="llama-3.3-70b-versatile"
# Brain loads these automatically
```

## 📊 Status & Monitoring

```python
status = brain.status()
# {
#   "app": "my_app",
#   "active": "groq",  # Last successful provider
#   "providers_count": 3,
#   "providers": [
#     {"order": 0, "name": "groq", "model": "llama-3.3-70b-versatile"},
#     {"order": 1, "name": "openrouter", "model": "meta-llama/..."},
#     ...
#   ]
# }
```

## 🔄 Dynamic Rotation Example

```
Call #1 → groq OK (sticky=groq)
Call #2 → groq OK (sticky=groq)
Call #3 → groq fails (timeout) → openrouter OK (sticky=openrouter)
Call #4 → openrouter OK (sticky=openrouter)
Call #5 → openrouter fails → hf OK (sticky=hf)
```

No re-prompting on rotation; full context preserved.

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest
mypy brain/
black --check brain/
```

## 📦 Profiles

Pre-configured provider chains:

| Profile | Providers | Use Case |
|---|---|---|
| `fast` | Groq → OpenRouter → HF | Speed + free tier |
| `smart` | Cerebras → Groq | Reasoning + fallback |
| `cheap` | OpenRouter:free → HF | Budget ($0) |
| `resilient` | All 4 | Maximum uptime |

## 🎓 Examples

- [Price Assistant](examples/price_assistant/) — Query Sheets via LLM
- [Password Manager](examples/password_manager/) — Secure vault + chat
- [Jarvis FOCUS OS](examples/jarvis_focus_os/) — TDA task manager
- [Knowledge Bot](examples/knowledge_bot/) — RAG interface

Run:
```bash
cd examples/price_assistant
python main.py
```

## 🐛 Troubleshooting

### "All providers failed"
1. Check API keys: `brain.status()`
2. Verify connectivity
3. Check token limits/rate-limiting
4. Review logs (set `log_level: DEBUG`)

### "No valid JSON found"
1. LLM didn't return JSON
2. Increase `max_tokens` or lower `temperature`
3. Try different provider

### "Context enrichment failed"
1. Check credentials (Sheets, SQLite, etc.)
2. Verify resource exists
3. Brain continues without context (graceful degrade)

## 🤝 Contributing

1. Fork [llm-virtual-brain](https://github.com/vicbrak2/llm-virtual-brain)
2. Create feature branch: `git checkout -b feature/my-feature`
3. Commit: `git commit -m "Add feature"`
4. Push: `git push origin feature/my-feature`
5. Open PR

## 📄 License

MIT — See [LICENSE](LICENSE)

## 🙏 Credits

Built by [Victor Martinez](https://github.com/vicbrak2) as an evolution of [Jarvis FOCUS OS](https://github.com/vicbrak2/jarvis-focus-os).

---

**Questions?** Open an [issue](https://github.com/vicbrak2/llm-virtual-brain/issues).

**Want to contribute?** See [CONTRIBUTING.md](CONTRIBUTING.md).
