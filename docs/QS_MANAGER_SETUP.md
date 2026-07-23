# Configuración de QS Manager en Brain

Guía para conectar el agente `qamiluna_team` con el Web App de QS Manager V2 (Google Apps Script).

## 1. Desplegar QS Manager V2 Web App

### A. Abrir el proyecto Apps Script

1. Ve a [script.google.com](https://script.google.com)
2. Abre el proyecto existente de QS Manager, o crea uno nuevo:
   - **Crear nuevo**: `+ Nuevo proyecto` → Pegar el código de `tools/qs-manager-v2-webapp.gs`
   - **Usar existente**: Si ya tienes un Apps Script que publica QS Manager, salta a paso B

### B. Configurar variables de entorno (Script Properties)

1. En el proyecto Apps Script:
   - `Project Settings` (engranaje izquierda, abajo)
   - `Script properties`
   - Agregar dos nuevas propiedades:

```text
Propiedad: QS_MANAGER_READ_API_KEY
Valor: <genera una clave larga aleatoria, ej: "qs-read-key-7a9f2c1e4d8b5f">

Propiedad: QS_MANAGER_CATALOG_API_KEY
Valor: <usa la clave existente si la tienes, o genera una nueva>
```

**Nota**: Si ya tienes `QS_MANAGER_CATALOG_API_KEY` pero no `QS_MANAGER_READ_API_KEY`, el script aceptará la `CATALOG_API_KEY` para lectura temporalmente, pero es recomendable crear una clave de lectura separada.

### C. Desplegar como Web App

1. En el editor del Apps Script:
   - `Deploy` (botón azul arriba)
   - `New deployment` (+)
   - Tipo: `Web app`
   - Execute as: `[Tu usuario de Google]`
   - Who has access: `Anyone` (si es solo para Brain en la nube)
   - `Deploy`

2. Copiar la URL publicada (algo como):
```
https://script.google.com/macros/s/SCRIPT_ID/exec
```

## 2. Configurar Brain

### A. Variables de entorno (`.env` en la carpeta `brain/`)

```text
QS_MANAGER_GAS_URL=https://script.google.com/macros/s/SCRIPT_ID/exec
QS_MANAGER_READ_API_KEY=qs-read-key-7a9f2c1e4d8b5f
```

O si usas Railway/docker, agregar a las variables de entorno del proyecto:

```
QS_MANAGER_GAS_URL=https://script.google.com/macros/s/SCRIPT_ID/exec
QS_MANAGER_READ_API_KEY=qs-read-key-7a9f2c1e4d8b5f
```

### B. Reiniciar Brain Server

```bash
# Local
python -m brain.server --profiles profiles --data data --port 8888

# O si está corriendo, reinicia (Ctrl+C y vuelve a ejecutar)
```

## 3. Verificar la integración

### Test manual via curl

```bash
# Listar servicios activos
curl -X POST http://localhost:8888/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "qamiluna_team",
    "message": "Que servicios activos tenemos en la planilla?"
  }' | jq '.reply'
```

Respuesta esperada (incluye datos en vivo de QS):
```
DATOS EN VIVO - QS MANAGER
Generado: 2026-07-23T14:32:00...

SERVICIOS ACTIVOS
- SVC-0001 | Social: Maquillaje | Precio: 45000
- SVC-0002 | Social: M+P | Precio: 65000
...

TRASLADOS REGISTRADOS
- Providencia: $5000 (6), $7000 (2) | Ultimo: 2026-07-20
- Las Condes: $8000 (4) | Ultimo: 2026-07-18
...

El agente responde:
"Tenemos 3 servicios activos registrados. El precio de Social: Maquillaje es 45000..."
```

### Test con Jarvis

Si Jarvis está corriendo (puerto 3000), puedes pedir a qamiluna_team vía Jarvis:

```bash
curl -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "qamiluna_team",
    "message": "Hay tarifa unica de traslado para Las Condes?"
  }' | jq '.reply'
```

## 4. Preguntas de validación

Prueba estas preguntas al agente para verificar que los datos están disponibles:

```text
1. "Que servicios activos tenemos en la planilla?"
   Respuesta esperada: lista servicios con precios desde QS MANAGER

2. "Cuanto hemos cobrado de traslado en Providencia?"
   Respuesta esperada: valores registrados (5000, 7000) con fechas

3. "Hay tarifa unica de traslado para Las Condes?"
   Respuesta esperada: valores registrados (8000) o aclaración de múltiples valores

4. "Existe el servicio Social: M+P como activo?"
   Respuesta esperada: "Sí, aparece como SVC-0002" o "No aparece como activo"
```

## 5. Troubleshooting

### Error: "QS_MANAGER_GAS_URL is not configured"
- Falta la variable `QS_MANAGER_GAS_URL` en `.env` o railway
- Verifica que está configurada y reinicia el servidor

### Error: "Invalid read API key"
- La clave en `QS_MANAGER_READ_API_KEY` no coincide con la de Script Properties
- Regenera la clave en Script Properties y actualiza `.env`

### El agente responde sin datos en vivo (dice "según la planilla")
- El conector `qs_manager_qamiluna` está configurado pero no obtiene datos
- Verifica: URL del Web App correcta, clave de API válida, conexión de red
- En el server, busca logs: `[qs_manager] fetch falló: ...`

### El Web App responde 404
- El deployment no está publicado o se expiró
- En Apps Script: `Deploy` → `Manage deployments` → revisa que esté activo
- Si no, crea un nuevo deployment

### Sheets retorna "sheet not found"
- El código del Web App espera `Bitácora QS — Servicios` y `Servicios_Master`
- Verifica que existan con esos nombres exactos (mayúsculas, acentos)
- Revisa el ID de Spreadsheet: `const QS_MANAGER_V2_BITACORA_ID = '...'`

## 6. Referencia: acciones del Web App

El Web App soporta 3 acciones via POST:

### `list_active_services`
```bash
curl -X POST "$QS_MANAGER_GAS_URL" \
  -H "Content-Type: application/json" \
  -d '{"action":"list_active_services","api_key":"CLAVE"}'
```

Respuesta:
```json
{
  "ok": true,
  "result": {
    "count": 3,
    "services": [
      {
        "service_id": "SVC-0001",
        "nombre_canonico": "Social: Maquillaje",
        "precio_venta": 45000,
        "margen": 0.66,
        ...
      }
    ]
  }
}
```

### `get_transport_values`
```bash
curl -X POST "$QS_MANAGER_GAS_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "get_transport_values",
    "api_key": "CLAVE",
    "comuna": "Providencia",
    "limit": 50
  }'
```

Respuesta:
```json
{
  "ok": true,
  "result": {
    "groups": [
      {
        "comuna": "Providencia",
        "transport_values": [
          {"value": 5000, "count": 6},
          {"value": 7000, "count": 2}
        ],
        "latest_date": "2026-07-20"
      }
    ]
  }
}
```

Para todas las comunas, omite `"comuna"`.

## 7. Siguientes pasos (opcional)

- **Caching mejorado**: Agregar `CACHE_TTL_SECONDS` en `brain/connectors.py` si los datos cambian frecuentemente
- **Validación de datos**: Agregar reglas de negocio (ej: traslado > 0)
- **Auditoria**: Registrar cada consulta al conector en un log local
- **Multi-tenant**: Si hay varios estudios, parametrizar el Spreadsheet ID por profile
