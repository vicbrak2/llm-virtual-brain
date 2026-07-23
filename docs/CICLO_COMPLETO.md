# Ciclo Completo: Crear → Linkear → Usar un Sub-Agente

## Escenario
Jarvis necesita un agente especializado en **análisis de tendencias de tareas**. 
Este agente debe:
- Clasificar tareas usando la matriz Eisenhower
- Sugerir acciones basadas en urgencia/importancia
- Reportar tendencias

---

## Paso 1: Pedir al creador que diseñe el agente

```bash
# Terminal 1: Brain Server corriendo
python -m brain.server --profiles profiles --data data --port 8888

# Terminal 2: Charlar con jarvis_meta (creador)
curl -X POST http://localhost:8888/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "jarvis_meta",
    "message": "Necesito un agente que analice tendencias de tareas: cuáles son urgentes+importantes, cuáles puedo delegar, cuáles eliminar. El agente debe proponer estrategias para la semana.",
    "max_tokens": 600
  }'
```

**Respuesta esperada:**
```
jarvis_meta hace preguntas de refinamiento:
1. "¿Con qué frecuencia se ejecutaría? (diario, semanal, etc.)"
2. "¿Qué datos de entrada necesita? (lista de tareas, calendario, OKRs)"
3. "¿Formato de salida? (resumen ejecutivo, tabla, reporte detallado)"
4. Cuando tenga el contexto → Presenta resumen y pide "OK"
```

---

## Paso 2: Confirmar creación

```bash
# Responder "OK" al jarvis_meta
curl -X POST http://localhost:8888/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "jarvis_meta",
    "message": "OK",
    "history": [
      {"role": "user", "content": "Necesito un agente que analice..."},
      {"role": "assistant", "content": "... resumen ... ¿Confirmas?"},
      {"role": "user", "content": "OK"}
    ],
    "max_tokens": 600
  }'
```

**Respuesta esperada:**
```
✅ Agente creado y desplegado.

• Tag/ID: tendencias_tareas
• Nombre: Analizador de Tendencias
• Ficha en Sheets: pestaña AGENTE tendencias_tareas ✓
• Hoja de datos propia: DB tendencias_tareas
```

---

## Paso 3: Editar el agente → Linkear a Eisenhower

Ahora el nuevo agente `tendencias_tareas` existe y es invocable.
Para que **herede el contexto de Eisenhower**, editamos sus links:

```bash
# GET info del agente
curl -s http://localhost:8888/api/profile/info?name=tendencias_tareas | jq

# Ejemplo de salida:
{
  "name": "tendencias_tareas",
  "description": "...",
  "prompt": "...",
  "links": [],                           # Vacio ahora
  "available_links": ["eisenhower", "general", "qamiluna_team"],
  "connectors": []
}

# POST para linkear a eisenhower
curl -X POST http://localhost:8888/api/profile/update \
  -H "Content-Type: application/json" \
  -d '{
    "name": "tendencias_tareas",
    "links": ["eisenhower"]
  }'

# Respuesta esperada:
{
  "name": "tendencias_tareas",
  "links": ["eisenhower"],
  "connectors": [],
  "yaml_updated": false
}
```

**¿Qué paso? El agente `tendencias_tareas` ahora ve:**
- Sus propios documentos (data/tables/tendencias_tareas/)
- El contexto compartido de eisenhower (data/tables/eisenhower/)
- Ambos se inyectan juntos como BASE DE CONOCIMIENTO en cada chat

---

## Paso 4: Usar el agente (Jarvis invoca tendencias_tareas)

Desde Jarvis:

```python
# En main.py de Jarvis, despues de obtener tareas
import httpx

async def analyze_task_trends(tasks: list):
    """Jarvis pide al agente tendencias_tareas que analice las tareas."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "http://localhost:8888/api/chat",
            json={
                "profile": "tendencias_tareas",
                "message": f"Analiza estas tareas y classifícalas por urgencia/importancia:\n{json.dumps(tasks)}",
                "max_tokens": 1000
            }
        )
        return r.json()["reply"]

# Uso:
reply = await analyze_task_trends([
    {"title": "Bug crítico en API", "deadline": "hoy", "impact": "alta"},
    {"title": "Refactor de auth", "deadline": "3 semanas", "impact": "media"},
    ...
])
```

**¿Qué pasa internamente?**
```
1. POST /api/chat {profile: "tendencias_tareas", message: "..."}
2. Brain Server carga:
   - Prompt del agente tendencias_tareas
   - Docs de data/tables/tendencias_tareas/ (propios)
   - Docs de data/tables/eisenhower/ (linkado)
   - Connectors del agente (si existen)
3. Inyecta TODO eso como contexto al LLM
4. LLM responde clasificando tareas usando la matriz Eisenhower
5. Respuesta se devuelve a Jarvis
```

---

## Paso 5: Agregar datos / Configurar conectores (opcional)

### Subir un documento de políticas al agente:

```bash
# Upload TXT con ejemplos de clasificación
curl -X POST http://localhost:8888/api/upload \
  -F "file=@./policies.txt" \
  -F "profile=tendencias_tareas"
```

### Configurar conector Instagram (arquitectura):

```bash
curl -X POST http://localhost:8888/api/profile/update \
  -H "Content-Type: application/json" \
  -d '{
    "name": "tendencias_tareas",
    "connectors": [
      {
        "name": "instagram_insights",
        "type": "instagram",
        "config": {
          "account": "@qamiluna_studio",
          "metrics": ["impressions", "engagement", "reach"]
        }
      }
    ]
  }'

# El agente ahora "sabe" que puede acceder a Instagram:
# "Las métricas de Instagram están disponibles via conector instagram_insights,
#  pero actualmente ese conector aún no está activado."
```

---

## Aislamiento Garantizado

Aunque `tendencias_tareas` linkea a `eisenhower`:

| Aspecto | Garantía |
|---|---|
| Datos | tendencias_tareas ve su carpeta + eisenhower; los demás NO lo ven |
| Documentos | Si subes TXT a tendencias_tareas, NO va a eisenhower (unidireccional) |
| Filas en Sheets | Cada agente tiene su hoja "DB <perfil>" separada |
| Eliminación | Si eliminas tendencias_tareas, se limpia el link en eisenhower automáticamente |
| Contexto en chat | merged_docs_context() suma docs solo de perfiles linkeados, en tiempo de ejecución |

---

## Resumen: Flujo Multi-Agente

```
┌─ Jarvis (puerto 3000)
│  └─ /chat
│     └─ BrainServerClient.complete()
│        └─ HTTP POST http://localhost:8888/api/chat {profile: "tendencias_tareas"}
│           └─ Brain Server
│              ├─ carga: tendencias_tareas.yaml (prompt + providers)
│              ├─ carga: data/tables/tendencias_tareas/ (propios)
│              ├─ carga: data/tables/eisenhower/ (linkado)
│              ├─ inyecta: TODO como BASE DE CONOCIMIENTO
│              └─ LLM responde vía Groq/Cerebras/etc.
│
└─ Google Sheets (Brain DB)
   ├─ Pestaña "DB tendencias_tareas" (datos del agente)
   ├─ Pestaña "AGENTE tendencias_tareas" (ficha + auditoría)
   ├─ Pestaña "DB eisenhower" (datos compartidos)
   └─ Pestaña "Agentes Jarvis" (índice de altas/bajas)
```

---

## Próximos pasos

1. **Ejecutores reales de conectores** — cuando se llama a /api/chat con connectores, 
   ejecutar la lógica real (fetch de Instagram, Facebook, etc.) en lugar de solo anunciar que existen.

2. **Deploy a Railway** — llevar Brain Server a la nube para que Jarvis sea accesible desde cualquier lugar.

3. **Sub-agentes especializados** — crear más agentes dinámicos:
   - `sprint_planner` (planificador de sprints)
   - `calendar_optimizer` (optimización de calendario)
   - `content_suggester` (sugerencias de contenido para Qamiluna)
