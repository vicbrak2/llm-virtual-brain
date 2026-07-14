# 🔑 Guía: obtener las API keys de cada provider

Todas son **gratis** (free tier, sin tarjeta de crédito salvo que se indique).
Pega cada key en tu `.env` (copiado de `.env.example`) y reinicia el contenedor:

```powershell
docker compose restart brain
Invoke-RestMethod http://localhost:8901/api/status   # verifica la cadena
```

La cadena está ordenada **calidad-primero** (la latencia no importa, Brain rota
si un provider falla o se queda sin cuota):

| # | Provider | Modelo configurado | Rol en la cadena |
|---|---|---|---|
| 1 | Gemini | `gemini-3.5-flash` | Principal — generación 2026, gran calidad |
| 2 | Groq | `moonshotai/kimi-k2-instruct-0905` | Open-weight top (Kimi K2, ~1T params MoE) |
| 3 | Cerebras | `gpt-oss-120b` (reasoning high) | Razonamiento profundo |
| 4 | Mistral | `mistral-large-latest` | Modelo grande, free tier generoso |
| 5 | OpenRouter | `meta-llama/llama-3.3-70b-instruct:free` | Fallback gratuito |
| 6 | HuggingFace | `Qwen/Qwen2.5-72B-Instruct` | Último recurso |

---

## 1. Gemini (Google) — `GEMINI_API_KEY`

1. Entra a **https://aistudio.google.com/apikey**
2. Inicia sesión con tu cuenta de Google (la de Gmail sirve).
3. Clic en **"Create API key"** → elige un proyecto (o deja que cree uno).
4. Copia la key (empieza con `AIza...`).

- Free tier: modelos **Flash y Flash-Lite** con límites por minuto/día.
- No requiere tarjeta. Ojo: si activas billing en el proyecto, pierdes el free tier.

## 2. Groq — `GROQ_API_KEY`

1. Entra a **https://console.groq.com**
2. Regístrate con Google o GitHub (gratis, sin tarjeta).
3. Menú lateral → **API Keys** → **"Create API Key"**.
4. Ponle un nombre (p. ej. `brain`) y copia la key (empieza con `gsk_...`).
   Se muestra **una sola vez** — guárdala ya.

- Free tier: miles de requests/día según el modelo.
- Aquí corre **Kimi K2** (uno de los mejores modelos abiertos) a gran velocidad.

## 3. Cerebras — `CEREBRAS_API_KEY`

1. Entra a **https://cloud.cerebras.ai**
2. Regístrate (email o Google, sin tarjeta).
3. Menú → **API Keys** → **"Generate API Key"**.
4. Copia la key (empieza con `csk-...`).

- Free tier: ~1M tokens/día, ~5 req/min, contexto limitado a 8K tokens.
- El catálogo gratuito cambia seguido; si `gpt-oss-120b` desaparece,
  lista los vigentes con tu key: `curl https://api.cerebras.ai/v1/models -H "Authorization: Bearer csk-..."`

## 4. Mistral — `MISTRAL_API_KEY`

1. Entra a **https://console.mistral.ai**
2. Regístrate (puede pedir verificación por teléfono).
3. En el workspace, acepta el plan gratuito **"Experiment"**
   (Billing → *Experiment for free*). Sin esto la API devuelve 401/403.
4. Menú → **API Keys** → **"Create new key"** → copia la key.

- Free tier: acceso a **todos** los modelos (incluido `mistral-large-latest`),
  ~2 req/min y ~1B tokens/mes. Para evaluación, no producción — perfecto como
  eslabón de la cadena.

## 5. OpenRouter — `OPENROUTER_API_KEY`

1. Entra a **https://openrouter.ai**
2. Regístrate con Google/GitHub/email.
3. Menú de tu cuenta → **Keys** → **"Create Key"**.
4. Copia la key (empieza con `sk-or-v1-...`).

- Los modelos `:free` no cuestan nada: ~20 req/min y ~200 req/día.
- Tip: si algún día cargas $10 de crédito (opcional), el límite diario de los
  modelos `:free` sube ~5x.
- Catálogo `:free` vigente: https://openrouter.ai/models/?q=free (rota seguido).

## 6. HuggingFace — `HF_TOKEN`

1. Entra a **https://huggingface.co** y crea cuenta.
2. Ve a **Settings → Access Tokens** (https://huggingface.co/settings/tokens).
3. **"Create new token"** → tipo **Read** (o fine-grained con permiso
   *Inference Providers*).
4. Copia el token (empieza con `hf_...`).

- El free tier de Inference Providers da un crédito mensual pequeño; es el
  último eslabón de la cadena.

---

## Verificar la orquestación

Con las keys en `.env`:

```powershell
docker compose restart brain
Invoke-RestMethod http://localhost:8901/api/status
```

- `providers` → los que entraron a la cadena (con `configured: true`).
- `skipped` → los que quedaron fuera por no tener key.
- `active` → el que respondió el último mensaje.

En los logs (`docker compose logs -f brain`) verás las rotaciones en vivo:
`[brain] rotación dinámica → mistral (mistral-large-latest)`.

## Cambiar modelos o el orden

Edita el YAML del perfil en `profiles/` (campo `model` y orden de la lista) y
reinicia. Los nombres conocidos (`gemini`, `groq`, `cerebras`, `mistral`,
`openrouter`, `hf`) ya traen URL y defaults — solo la key es obligatoria.
