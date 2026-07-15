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
| 1 | Groq | `llama-3.3-70b-versatile` | Principal — Llama 3.3 70B a gran velocidad (LPU) |
| 2 | Cerebras | `gpt-oss-120b` (reasoning high) | Razonamiento profundo |
| 3 | OpenRouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | Fallback gratuito |
| 4 | HuggingFace | `Qwen/Qwen2.5-72B-Instruct` | Último recurso |

> Gemini y Mistral se retiraron de la cadena (sin API key en uso). Para
> re-agregarlos basta añadir su bloque en los YAML de `profiles/`.

---

## 1. Groq — `GROQ_API_KEY`

1. Entra a **https://console.groq.com**
2. Regístrate con Google o GitHub (gratis, sin tarjeta).
3. Menú lateral → **API Keys** → **"Create API Key"**.
4. Ponle un nombre (p. ej. `brain`) y copia la key (empieza con `gsk_...`).
   Se muestra **una sola vez** — guárdala ya.

- Free tier: miles de requests/día según el modelo.
- Aquí corre **Llama 3.3 70B** a gran velocidad (hardware LPU).

## 2. Cerebras — `CEREBRAS_API_KEY`

1. Entra a **https://cloud.cerebras.ai**
2. Regístrate (email o Google, sin tarjeta).
3. Menú → **API Keys** → **"Generate API Key"**.
4. Copia la key (empieza con `csk-...`).

- Free tier: ~1M tokens/día, ~5 req/min, contexto limitado a 8K tokens.
- El catálogo gratuito cambia seguido; si `gpt-oss-120b` desaparece,
  lista los vigentes con tu key: `curl https://api.cerebras.ai/v1/models -H "Authorization: Bearer csk-..."`

## 3. OpenRouter — `OPENROUTER_API_KEY`

1. Entra a **https://openrouter.ai**
2. Regístrate con Google/GitHub/email.
3. Menú de tu cuenta → **Keys** → **"Create Key"**.
4. Copia la key (empieza con `sk-or-v1-...`).

- Los modelos `:free` no cuestan nada: ~20 req/min y ~200 req/día.
- Tip: si algún día cargas $10 de crédito (opcional), el límite diario de los
  modelos `:free` sube ~5x.
- Catálogo `:free` vigente: https://openrouter.ai/models/?q=free (rota seguido).

## 4. HuggingFace — `HF_TOKEN`

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
`[brain] rotación dinámica → cerebras (gpt-oss-120b)`.

## Cambiar modelos o el orden

Edita el YAML del perfil en `profiles/` (campo `model` y orden de la lista) y
reinicia. Los nombres conocidos (`gemini`, `groq`, `cerebras`, `mistral`,
`openrouter`, `hf`) ya traen URL y defaults — solo la key es obligatoria.
