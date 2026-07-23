# Infraestructura y capacidades de Brain — documento explicativo

> Generado el 2026-07-22. Refleja el estado real verificado (producción + repo local),
> no solo lo documentado en README.md (que describe la librería genérica, no siempre
> el despliegue actual de Qamiluna).

---

## 1. Qué es Brain

**Brain** es un orquestador multi-LLM en Python (FastAPI) que centraliza la lógica de
hablar con distintos proveedores de modelos de lenguaje, con rotación automática si
uno falla, inyección de contexto en vivo (Instagram, Meta Ads, etc.) y una capa de
"perfiles" (agentes) configurables por YAML sin tocar código.

Nació como evolución de **Jarvis FOCUS OS** (ver sección 6) y hoy corre en producción
principalmente para **Qamiluna Studio** (estudio de maquillaje/peinado), con un agente
interno (`qamiluna_team`), un agente general y un "creador" de sub-agentes.

**Producción:** `https://brain-production-e825.up.railway.app` (Railway, servicio `brain`).

---

## 2. Orquestación multi-LLM (`brain/core.py`, `brain/providers.py`)

### 2.1 Cadena de providers y rotación

Cada perfil define una lista ordenada de providers. Ante cualquier fallo (HTTP error,
timeout, respuesta vacía, rate limit) se rota automáticamente al siguiente **sin perder
el contexto de la conversación** — no hay re-prompting.

Cadena actual (misma para los 3 perfiles activos en producción):

| Orden | Provider | Modelo | Costo | Notas |
|---|---|---|---|---|
| 1 | Groq | `openai/gpt-oss-120b` | Gratis (tier free, techo de TPM) | Primero: no cuesta nada mientras no rate-limitee |
| 2 | OpenRouter | `mistralai/mistral-small-3.2-24b-instruct` | $0.075 / $0.20 por M tokens | No razonador, "reduce infinite generations" |
| 3 | Cerebras | `gemma-4-31b` | $0.35 / $1.49 por M tokens | Razonador (thinking), pago (org "Qamiluna studio") |
| 4 | HuggingFace | `Qwen/Qwen2.5-72B-Instruct` | Pago (créditos prepago) | No razonador, último respaldo |

Todos los providers son **OpenAI-compatible** (mismo formato de request/response),
lo que permite intercambiarlos sin cambiar código — solo config YAML.

### 2.2 Mecanismos de resiliencia implementados esta sesión

- **Timeout duro por llamada** (`asyncio.wait_for`, 30s): antes un provider lento podía
  colgar 60-90s y el edge de Railway devolvía 502 genérico sin info útil. Ahora cada
  intento individual corta a los 30s exactos y rota.
- **Rechazo de "reasoning" crudo**: si un modelo razonador deja `content` vacío y todo
  el texto en el campo interno `reasoning` (borrador en inglés, sin pulir), `parse_response()`
  lo trata como fallo y rota — nunca se muestra ese texto crudo al usuario.
- **Continuación automática**: si una respuesta se corta por `max_tokens`
  (`finish_reason == "length"`), se reintenta con el MISMO provider pidiendo
  "continúa exactamente donde quedaste", hasta 3 veces, concatenando el resultado.
- **Modo `refine` (multi-etapa)**: opcional (`refine: true` en `/api/chat`), usa un
  provider para el borrador y otro distinto para refinarlo — más calidad, pero más
  lento y más caro. El chat principal lo usa por defecto; el reporte de Instagram y
  `/api/query/improve` usan un solo paso (`refine: false` / `Brain.complete()`).

### 2.3 Modelos descartados (y por qué) — evitar repetir el error

| Modelo | Problema encontrado |
|---|---|
| `nvidia/nemotron-3-super-120b-a12b` (antiguo default OpenRouter) | Razonador: en prompts largos gastaba todo el `max_tokens` "pensando", dejando `content` vacío, o tardaba 60-90s |
| `google/gemini-2.5-flash-lite` | Con tablas markdown largas, emitía páginas enteras de espacios en blanco hasta agotar el presupuesto de tokens; la continuación automática lo agravaba (llegó a 352 KB de basura) |
| `qwen/qwen3.5-35b-a3b` | Inconsistente: a veces perfecto, a veces cortaba a los ~200 tokens sin razón aparente |

---

## 3. Contexto en vivo — Conectores (`brain/connectors.py`)

Los conectores traen datos reales de APIs externas y se inyectan en el prompt del LLM
como bloque `DATOS EN VIVO` antes de cada respuesta. Cacheados 10 minutos
(`CACHE_TTL_SECONDS`) para no golpear las APIs en cada mensaje.

| Conector | Tipo | Fuente | Estado en producción |
|---|---|---|---|
| `instagram_qamiluna` | `instagram` | Instagram Graph API (`graph.instagram.com`) | ✅ OK — @qamiluna_studio, 3112 seguidores |
| `meta_ads_qamiluna` | `meta_ads` | Meta Marketing API | ❌ Error 400 (token/cuenta de ads mal configurados) |
| `facebook_qamiluna` | `facebook_page` | Graph API de Facebook | ❌ Error 400 (mismo token de Meta Ads) |
| `whatsapp_qamiluna` | `whatsapp` | WhatsApp Business API | ⏳ Pendiente (falta `WHATSAPP_BUSINESS_ACCOUNT_ID`) |
| `messenger_qamiluna` | `messenger` | Graph API de Facebook | ❌ Error 400 (mismo token) |
| `threads_qamiluna` | `threads` | API de Threads | ⏳ Pendiente (falta `THREADS_ACCESS_TOKEN`) |

**El único conector 100% funcional hoy es Instagram.** Meta Ads, Facebook Page y
Messenger comparten el mismo `META_ADS_ACCESS_TOKEN`, que está devolviendo 400 Bad
Request — pendiente de diagnóstico/renovación (no investigado a fondo aún).

### 3.1 Qué trae el conector de Instagram

Perfil (seguidores, tipo de cuenta) · alcance/vistas/interacciones de 28 días ·
demografía (edad, ciudad) · **serie diaria de nuevos seguidores y alcance (14 días)**
agregada esta sesión · últimas 15 publicaciones con métricas por post y link exacto ·
rendimiento por hashtag · resumen histórico mensual (hasta 100 posts) · historias
activas · comentarios sin responder · DMs esperando respuesta.

**Nota confirmada:** "impresiones" NO está disponible — Meta la deprecó para este tipo
de cuenta; el sistema usa "alcance" en su lugar y lo declara así en vez de inventar el dato.

---

## 4. Perfiles / agentes

### 4.1 En producción (los 3 realmente desplegados y activos)

| Perfil | Tipo | Descripción | Conectores | Linkea a |
|---|---|---|---|---|
| `qamiluna_team` | Interno | Operaciones, métricas de IG, estrategia de contenido, borradores de community management (con guardrails de tono/vocabulario y **alcance restringido al negocio** — rechaza en 1 línea preguntas fuera de tema para no gastar tokens) | 6 (ver arriba) | `general` |
| `general` | Público | Asistente de conocimiento general sobre documentos TXT subidos | Ninguno | — |
| `creador` | Meta | Diseña y despliega nuevos sub-agentes vía conversación (genera YAML + Brain lo carga en caliente) | Ninguno | — |

### 4.2 En el repo local, sin desplegar (creados ~2026-07-19/22, no commiteados)

Estos archivos existen en `profiles/` pero son **untracked en git** (`git status`
los marca `??`) y por lo tanto nunca llegaron a Railway — no aparecen en
`/api/profiles` de producción:

- `profiles/jarvis_internal.yaml` — agente espejo de Jarvis FOCUS OS dentro de Brain
  (task management, calendar, matriz de Eisenhower).
- `profiles/jarvis_meta.yaml` — meta-agente que crea sub-agentes especializados
  *para* Jarvis (análogo a `creador`, pero orientado a productividad en vez de negocio).
- `profiles/eisenhower.yaml` — perfil de contexto compartible (clasificador
  urgente/importante) que otros agentes pueden "linkear" para heredar su lógica.

Ver sección 6 para el detalle de esta integración pendiente.

---

## 5. Interfaces (UI)

### 5.1 `/` — Chat principal (`ui/brain-chat.html`)

Bundle React precompilado (~280 KB, sin JSX fuente en el repo) con panel lateral de
perfiles, subida de documentos TXT, editor de agentes, y generador de prompts para
agentes externos. Todas las mejoras de esta sesión se agregaron como **bloques
`<script>` aditivos al final del archivo** (nunca se tocó el bundle compilado):

- Monitor en vivo de la orquestación (`#brain-monitor`, polling a `/api/chat/status`).
- Botón "✨ mejorar consulta" (usa `/api/query/improve`).
- Botón "🗑 Limpiar chat" (borra el historial del perfil activo en `localStorage`).
- Botón "📊 Reporte IG" (usa el endpoint cacheado `/api/report/instagram`, inyecta el
  resultado al historial vía `localStorage` + reload).
- Auto-linkeo de URLs sueltas (antes solo los links markdown `[texto](url)` se
  convertían en hipervínculo; ahora también las URLs planas tipo `https://...`).

### 5.2 `/studio` — Fachada pública (`ui/studio.html`)

HTML/JS plano y editable (no compilado), hardcoded al perfil `qamiluna_team`, pensado
para que el equipo (maquilladoras, estilistas) lo use sin ver la complejidad del panel
principal. Mismos 4 botones que el chat principal (mejorar consulta, limpiar chat,
reporte IG, chips de acceso rápido a captions/Reels/historias), con el mismo renderer
de markdown (tablas, listas, links) portado desde `brain-chat.html`.

---

## 6. Jarvis FOCUS OS — qué es y cómo se relaciona con Brain

Esto tiene **dos capas separadas** que no hay que confundir:

### 6.1 Jarvis FOCUS OS como origen histórico de Brain

Según el propio `README.md`: *"Built by Victor Martinez as an evolution of
[Jarvis FOCUS OS](https://github.com/vicbrak2/jarvis-focus-os)"*. Es decir, **Brain
nació como una generalización** de la lógica LLM que originalmente vivía dentro de
Jarvis (un asistente de productividad enfocado en TDA/ADHD: gestión de tareas,
calendario, matriz de Eisenhower). Se extrajo esa lógica a una librería reusable
(`Brain`) para poder alimentar también a Qamiluna y a cualquier otro caso de uso.

### 6.2 Jarvis FOCUS OS como sistema vivo, separado, hoy

Jarvis **sigue existiendo como aplicación propia e independiente** — no es solo
historia. Corre como contenedor Docker local (`jarvis-focusos`, expuesto en
`localhost:8000` según el conector MCP) y expone su propia API de tareas/calendario/
Eisenhower. Verificado en esta sesión vía el MCP `jarvis` conectado a este chat
(`jarvis_get_board`, `jarvis_list_tasks`, `jarvis_add_task`, `jarvis_schedule_event`,
`jarvis_sync`, `jarvis_import_calendar`, etc.) — **el contenedor no estaba corriendo
en el momento de la prueba** (`Error: no se pudo conectar a Jarvis en
http://localhost:8000. Verifica que el contenedor jarvis-focusos esté corriendo`).

### 6.3 La integración pendiente (lo nuevo, sin desplegar)

Los 3 archivos de la sección 4.2 son el intento de **reconectar Jarvis con Brain**,
pero al revés de como era originalmente: en vez de que la lógica LLM viva dentro de
Jarvis, ahora Jarvis (FastAPI, puerto 3000 según el comentario del YAML — dato a
confirmar, discrepa con el puerto 8000 que usa el MCP) le pegaría a Brain por HTTP:

```
Jarvis FOCUS OS (puerto 3000/8000)
        │  POST http://<brain>/api/chat  {"profile": "jarvis_internal", "message": "..."}
        ▼
   Brain Server  →  cadena groq → openrouter → cerebras → hf
        │  (razona sobre tareas, calendario, prioridad Eisenhower)
        ▼
   Respuesta al agente Jarvis
```

Así Jarvis reutilizaría toda la infraestructura de resiliencia/costo que ya construimos
para Qamiluna (rotación, timeouts, modelos baratos) en vez de mantener su propia
integración LLM.

**Estado real: código escrito, nunca commiteado ni desplegado.** Para que esto quede
vivo faltaría:
1. Confirmar qué puerto expone realmente Jarvis (3000 vs 8000 — discrepancia sin resolver).
2. `git add profiles/jarvis_internal.yaml profiles/jarvis_meta.yaml profiles/eisenhower.yaml`
   + commit + `./deploy.sh`.
3. Configurar Jarvis (el otro repo/contenedor) para que apunte al Brain de producción
   en vez de (o además de) su propia lógica LLM local.
4. Levantar el contenedor `jarvis-focusos` para poder probarlo end-to-end.

---

## 7. Backend — referencia de endpoints (`brain/server.py`)

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/` | Sirve el chat principal (`brain-chat.html`) |
| GET | `/studio`, `/studio/manifest.json` | Fachada pública de `qamiluna_team` |
| GET | `/api/health` | Healthcheck |
| GET | `/api/profiles` | Lista perfiles cargados + estado de conectores |
| POST | `/api/profile/activate` \| `/toggle` \| `/delete` \| `/update` | Gestión de perfiles/agentes |
| GET | `/api/profile/info` | Detalle de un perfil |
| GET | `/api/document`, `/api/documents` | Documentos TXT subidos por perfil |
| GET | `/api/status` | Cadena de providers activa + conectores en vivo |
| GET | `/api/chat/status` | Estado en vivo de la orquestación en curso (para el monitor) |
| POST | `/api/chat` | Endpoint principal de conversación (multi-step opcional vía `refine`) |
| POST | `/api/query/improve` | Reescribe la consulta del usuario antes de enviarla (1 paso, barato) |
| POST | `/api/report/instagram` | Reporte completo de IG, **cacheado por hash del contexto real** — no gasta tokens si Meta no entregó datos nuevos |
| POST | `/api/prompt/generate`, `/api/import` | Flujo de "prompt para agente externo" (ChatGPT/Claude externos devuelven XML que se importa a Sheets) |
| POST | `/api/upload` | Subida de documentos TXT (base de conocimiento) |
| GET/POST | `/webhooks/instagram/leads` | Webhook de leads de Instagram (Meta) |

---

## 8. Despliegue e infraestructura

- **Hosting:** Railway (proyecto `qamiluna-brain`, servicio `brain`), dominio público
  `brain-production-e825.up.railway.app`.
- **⚠️ No hay autodeploy desde GitHub.** Un `git push` NO despliega nada por sí solo
  — hay que correr `./deploy.sh` (agregado esta sesión), que hace `railway up`,
  espera el build con timeout de 5 min y confirma `SUCCESS`/`FAILED` explícitamente.
- **Imagen:** Dockerfile propio (`python:3.12-slim`), copia `brain/`, `ui/` y
  `profiles/` al build — los perfiles quedan **horneados en la imagen**, no en el
  volumen persistente.
- **Volumen persistente:** `data/` (documentos subidos, `response_times.json`,
  `profiles_meta.json`, tablas registradas).
- **Variables de entorno (Railway):** `GROQ_API_KEY`, `OPENROUTER_API_KEY`,
  `CEREBRAS_API_KEY`, `HF_TOKEN`, `INSTAGRAM_ACCESS_TOKEN`, `META_ACCESS_TOKEN`,
  `META_ADS_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `META_APP_ID/SECRET`, `META_PAGE_ID`,
  `GOOGLE_API_KEY`, `GOOGLE_SHEETS_ID`, `BRAIN_GAS_URL`, `LEADS_GAS_URL`,
  `NOTIFICATION_EMAIL`.
- **Créditos pagos activos verificados:** OpenRouter ($9.79), Cerebras org
  "Qamiluna studio" ($10.00), HuggingFace ($10.00). Groq sigue en tier gratis.

---

## 9. Seguridad / guardrails implementados

1. **Nunca se muestra el `reasoning` crudo de un modelo** (interno, a veces en inglés,
   sin pulir) como si fuera la respuesta final — se trata como fallo y se rota.
2. **`qamiluna_team` tiene alcance restringido**: preguntas ajenas al negocio (trivia,
   pedidos de encarnar personajes externos) se rechazan en una línea sin elaborar,
   para no gastar tokens.
3. **Guardrail de vocabulario de marca**: en captions/Reels/historias/WhatsApp se
   prohíben frases genéricas ("princesa", "brillar", "look único" sin detalle, etc.)
   y se sanea automáticamente (`_sanitize_qamiluna_content_reply`) si igual aparecen.
4. **No se inventan datos**: precios, fechas, cupos, links o métricas ausentes se
   marcan con placeholders editables (`[PRECIO]`, `[FECHA]`, etc.) en vez de rellenarse.
5. **Nada se publica automáticamente**: todo borrador de contenido queda explícitamente
   marcado como "para revisión humana"; el agente nunca afirma haber publicado o
   respondido algo por su cuenta.

---

## 10. Pendientes conocidos (no resueltos aún)

- Meta Ads / Facebook Page / Messenger devuelven 400 Bad Request — token o
  `META_AD_ACCOUNT_ID` desalineados (había una discrepancia detectada entre
  `act_925869830396990` configurado y `act_2103138713891114` visto en un `.env`
  pegado por el usuario, nunca confirmada cuál es la correcta).
- WhatsApp y Threads: conectores implementados en código pero sin credenciales.
- Integración Jarvis ↔ Brain: escrita, no desplegada (sección 6.3).
- Discrepancia de puerto de Jarvis (3000 en el comentario del YAML vs 8000 en el MCP)
  sin resolver.
