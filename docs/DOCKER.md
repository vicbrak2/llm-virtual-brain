# 🐳 Brain en Docker — orquestación multi-LLM

Levanta el Brain Server (chat UI + API) en un contenedor, con **todos los
providers LLM orquestados en cadena calidad-primero**: Gemini → Groq (Kimi K2)
→ Cerebras → Mistral Large → OpenRouter → HuggingFace. Si un provider falla o
no tiene API key, Brain rota automáticamente al siguiente sin perder el
contexto de la conversación.

> Solo necesitas **una** API key para empezar (Groq es gratis y rápida).
> Las que no configures se omiten de la cadena automáticamente.

## 1. Configura las variables de entorno

Copia la plantilla y edita con tus keys:

```powershell
Copy-Item .env.example .env
notepad .env
```

Pega tus keys (deja vacías las que no tengas):

```env
GROQ_API_KEY=gsk_...
CEREBRAS_API_KEY=csk-...
GEMINI_API_KEY=AIza...
MISTRAL_API_KEY=...
OPENROUTER_API_KEY=sk-or-...
HF_TOKEN=hf_...
BRAIN_GAS_URL=
```

Dónde obtener cada key (guía paso a paso: [API_KEYS.md](API_KEYS.md)):

| Provider | URL | Free tier |
|---|---|---|
| Gemini | https://aistudio.google.com/apikey | ✅ |
| Groq | https://console.groq.com/keys | ✅ |
| Cerebras | https://cloud.cerebras.ai | ✅ |
| Mistral | https://console.mistral.ai/api-keys | ✅ (plan "Experiment") |
| OpenRouter | https://openrouter.ai/keys | ✅ (modelos :free) |
| HuggingFace | https://huggingface.co/settings/tokens | ✅ |

## 2. Levanta el contenedor

```powershell
docker compose up -d --build
```

## 3. Verifica que esté corriendo

```powershell
docker compose ps
docker compose logs -f brain
```

Chequeo de salud y de la cadena de providers:

```powershell
Invoke-RestMethod http://localhost:8901/api/health
Invoke-RestMethod http://localhost:8901/api/status
```

`/api/status` muestra la orquestación en vivo:

```json
{
  "active_profile": "creador",
  "active": "gemini",
  "count": 2,
  "providers": [
    {"order": 0, "name": "gemini", "model": "gemini-3.5-flash", "configured": true},
    {"order": 1, "name": "groq", "model": "moonshotai/kimi-k2-instruct-0905", "configured": true}
  ],
  "skipped": [
    {"name": "cerebras", "model": "gpt-oss-120b", "reason": "sin API key"},
    {"name": "mistral", "model": "mistral-large-latest", "reason": "sin API key"}
  ]
}
```

- `providers` = cadena orquestada activa (en orden de fallback).
- `skipped` = providers sin API key, fuera de la cadena.
- `active` = el último provider que respondió (sticky).

## 4. Accede a Brain

Abre **http://localhost:8901** → UI de chat con perfiles, subida de TXT y
creación de sub-agentes.

## Operación diaria

```powershell
docker compose logs -f brain      # ver logs (rotaciones de provider incluidas)
docker compose restart brain      # reiniciar (recarga .env y perfiles)
docker compose down               # detener
docker compose up -d --build      # reconstruir tras actualizar el código
```

Los datos persisten fuera del contenedor:

- `./profiles/` → perfiles YAML (incluye sub-agentes creados desde la UI)
- `./data/` → documentos subidos, registros y estado

## ¿Cómo funciona la orquestación?

1. Cada petición de chat entra a la **cadena de providers** del perfil activo.
2. Brain llama al provider *sticky* (el último que funcionó).
3. Si falla (timeout, rate limit, error), **rota al siguiente con los mismos
   mensajes** — el usuario no nota nada.
4. Los providers sin API key nunca entran a la cadena (no desperdician llamadas).
5. Si todos fallan, la API responde 502 con el detalle de cada error.

Para cambiar la cadena de un perfil, edita su YAML en `profiles/` (orden,
modelos, providers) y reinicia el contenedor.
