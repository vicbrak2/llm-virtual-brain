# Arquitectura: Qamiluna Brain × Meta + Instagram + Google Sheets

## Flujo de Datos en Vivo

```
┌─────────────────────────────────────────────────────────────────┐
│                    INSTAGRAM LEAD ADS (Cliente)                │
│                         @qamiluna_studio                        │
│                      ✍️ Completa formulario                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ (en tiempo real, <5 seg)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     META GRAPH API                              │
│          Lead Form → Webhook POST /webhooks/instagram/leads     │
│          JSON: {full_name, email, phone, interested_in, city}   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BRAIN SERVER                                 │
│             (localhost:8000 o brain.qamiluna.com)              │
│                                                                 │
│  POST /webhooks/instagram/leads                                 │
│    ↓                                                             │
│  Procesa en background:                                         │
│    • Extract: nombre, teléfono, email, interés                 │
│    • Calcula score (0-2)                                        │
│    • Genera timestamp                                           │
│    ↓                                                             │
│  Inserta en Google Sheets (via Sheets API)                      │
│    ↓                                                             │
│  Notifica equipo (email/Slack)                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   GOOGLE SHEETS                                 │
│         📊 Qamiluna Leads & Campaigns (Sheet compartida)       │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ LEADS_INSTAGRAM (pestaña 1)                             │  │
│  ├──────────┬──────────┬──────────┬─────────┬───────────────┤  │
│  │ Timestamp│ Nombre   │ Teléfono │ Email   │ Interés...    │  │
│  ├──────────┼──────────┼──────────┼─────────┼───────────────┤  │
│  │14:32:00  │ Andrea P │+56941... │ a@m.com │ Novia Civil   │  │
│  │13:15:00  │ Catalina │—         │ c@m.com │ Social        │  │
│  └──────────┴──────────┴──────────┴─────────┴───────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ CONTACTOS_DIRECTOS (pestaña 2)                          │  │
│  ├──────────┬──────────┬──────────┬──────────┬────────────┤  │
│  │ Timestamp│ Nombre   │ Mensaje  │ Plataform│ Respondido │  │
│  ├──────────┼──────────┼──────────┼──────────┼────────────┤  │
│  │15:20:00  │ Marcela  │ ¿Cuánto...│ Insta DM │ ❌ (Manual)│  │
│  └──────────┴──────────┴──────────┴──────────┴────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ CAMPAÑAS_ADS (pestaña 3 - sync cada 6h)               │  │
│  ├──────────┬───────────────┬────────┬─────┬──────────────┤  │
│  │ Fecha    │ Campaña       │ Spend $│ ROAS│ Status       │  │
│  ├──────────┼───────────────┼────────┼─────┼──────────────┤  │
│  │2026-07-17│ Summer Sale   │ 1250.50│ 3.2 │ ✅           │  │
│  │2026-07-17│ Novias Julio  │  450.00│ 1.8 │ ⚠️ Revisar   │  │
│  └──────────┴───────────────┴────────┴─────┴──────────────┘  │
│                                                                 │
│  📝 Equipo usa estas pestañas para:                            │
│     • Ver leads nuevos                                         │
│     • Cambiar Status (🆕 → 📞 → ✅)                           │
│     • Monitorear performance de ads                            │
│     • Responder DMs manualmente                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
        ┌───────────────────────────────────────┐
        │  EQUIPO: Cami, Paz, Mou, Andrea       │
        │  💻 Acceso a Sheets compartida        │
        │  ☎️  Responden desde Instagram        │
        │  ✉️  Responden desde WhatsApp         │
        └───────────────────────────────────────┘
```

---

## Sync Periódicas (Background Tasks)

```
CADA 15 MINUTOS:
┌─────────────────────────────────────────┐
│ Sync Instagram DMs (lectura sin resp)   │
│                                         │
│ 1. GET /me/conversations (Instagram API)│
│ 2. Extrae: nombre, último mensaje       │
│ 3. Append a Sheets tab CONTACTOS_DIRECTOS
│                                         │
│ ✅ Sin respuesta automática — manual    │
└─────────────────────────────────────────┘

CADA 6 HORAS:
┌─────────────────────────────────────────┐
│ Sync Meta Ads Insights                  │
│                                         │
│ 1. GET /act_{id}/insights (Meta API)    │
│ 2. Extrae: spend, impressions, ROAS     │
│ 3. Calcula: ROAS, status de alerta      │
│ 4. Append a Sheets tab CAMPAÑAS_ADS     │
│                                         │
│ ⚠️  Si ROAS < 2 → marca para revisar   │
└─────────────────────────────────────────┘
```

---

## Archivos Modificados / Creados

| Archivo | Cambio | Propósito |
|---------|--------|----------|
| `brain/.env` | ✅ CREADO | Config: Meta tokens, Google Sheets ID, webhook token |
| `brain/connectors.py` | ✅ ACTUALIZADO | 5 nuevas funciones de webhook + Google Sheets |
| `brain/server.py` | ✅ ACTUALIZADO | 2 nuevas rutas HTTP + scheduler periódico |
| `SETUP_QAMILUNA_META_GOOGLE.md` | ✅ CREADO | Guía de configuración + testing paso a paso |
| `ARQUITECTURA_INTEGRACION.md` | ✅ CREADO | Este documento |

---

## Variables de Entorno Cargadas

```bash
# Meta APIs
META_APP_ID=982984821462535
META_APP_SECRET=<ver brain/.env>
META_ACCESS_TOKEN=<ver brain/.env> (Long-Lived)
META_AD_ACCOUNT_ID=act_925869830396990
INSTAGRAM_BUSINESS_ACCOUNT_ID=17841468292856605

# Webhook de Meta
WEBHOOK_VERIFY_TOKEN=<ver brain/.env>
WEBHOOK_URL=https://brain.qamiluna.com/webhooks/instagram/leads

# Google Sheets
GOOGLE_SHEETS_ID=1nfApWlPXdDJVCLDLnEI9HA1ttclQZCR4obSTNm2H5hw
GOOGLE_API_KEY=<ver brain/.env>
GOOGLE_CLOUD_PROJECT_ID=qamiluna-brain

# Notificaciones
NOTIFICATION_EMAIL=cami@qamiluna.com,paz@qamiluna.com,mou@qamiluna.com
SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK (opcional)

# Entorno
ENVIRONMENT=development
```

---

## Endpoints HTTP Nuevos

### GET /webhooks/instagram/leads
**Propósito:** Verificación de webhook (handshake con Meta)  
**Meta hace:** GET con `hub_mode=subscribe&hub_challenge=XXX&hub_verify_token=YYY`  
**Brain responde:** El challenge (número) si token es válido  
**Error:** 403 si token incorrecto

### POST /webhooks/instagram/leads
**Propósito:** Recibe leads de Instagram en tiempo real  
**Meta envía:** JSON con `{entry: [{leadgen: [{field_data: [...]}]}]}`  
**Brain hace:**
1. Extrae datos en background (no bloquea)
2. Calcula score (0-2)
3. Inserta en Sheets
4. Notifica equipo por email/Slack
**Respuesta:** `{status: "received"}` inmediato

---

## Funciones Nuevas en connectors.py

### `async handle_instagram_leads_webhook(payload: Dict) -> bool`
- Procesa webhook de Instagram Leads Ads
- Extrae: nombre, email, teléfono, interés, ciudad
- Score: +1 por teléfono, +1 por email
- Inserta fila en Sheets `LEADS_INSTAGRAM`
- Notifica equipo

### `async _append_to_gsheet(sheet_id: str, tab: str, values: List[List]) -> bool`
- Wrapper de Sheets API
- Append de valores al final de una pestaña
- Maneja errores de API Key / permisos

### `async _notify_team_lead(lead_data: Dict) -> None`
- Envía email a: cami@, paz@, mou@
- Envía Slack (si está configurado)
- Mensaje: "📩 Nuevo lead: {name} ({interest})"

### `async sync_meta_ads_insights() -> bool`
- Consulta Meta Ads API: insights últimos 7 días
- Por cada campaña:
  - Calcula ROAS (revenue / spend)
  - Status: ✅ (ROAS≥2), ⚠️ (1.5≤ROAS<2), ❌ (ROAS<1.5)
  - Append a Sheets `CAMPAÑAS_ADS`

### `async sync_instagram_dms() -> bool`
- Consulta Instagram Business API: conversaciones vivas
- Por cada DM:
  - Extrae: nombre, último mensaje, timestamp
  - Append a Sheets `CONTACTOS_DIRECTOS`
  - **NO responde automático**

---

## Flujo de Testing

```
1. Brain arranca
   ↓
2. Se suscribe a: GET /webhooks/instagram/leads
   Meta verifica token → ✅ Verificado
   ↓
3. Creas anuncio con Lead Form
   ↓
4. Alguien completa formulario
   ↓
5. Meta envía: POST /webhooks/instagram/leads
   Brain procesa en background (~1 seg)
   ↓
6. Abre Sheets → LEADS_INSTAGRAM
   → ¿Aparece lead nuevo?
   ✅ SÍ → Flujo correcto
   ❌ NO → Revisar troubleshooting en SETUP_QAMILUNA_META_GOOGLE.md
   ↓
7. Luego de 6h:
   Meta Ads sync ejecuta
   → Abre Sheets → CAMPAÑAS_ADS
   → ¿Aparecen métricas?
   ↓
8. Luego de 15 min:
   Instagram DMs sync ejecuta
   → Abre Sheets → CONTACTOS_DIRECTOS
   → ¿Aparecen DMs?
```

---

## Escala de Seguridad

| Nivel | Implementación | Status |
|-------|----------------|--------|
| **Desarrollo** | localhost:8000, API Key simple, token 60 días | ✅ IMPLEMENTADO |
| **Staging** | HTTP (no HTTPS), monitoring local | ⏳ Próximo |
| **Producción** | HTTPS, Service Account JSON, Long-Lived tokens | ⏳ Próximo |

---

## Próximos Pasos Recomendados

1. **Ejecutar SETUP_QAMILUNA_META_GOOGLE.md** (todas las secciones)
2. **Entrenar equipo** en Sheets + respuestas manuales
3. **Monitorear logs** de Brain durante pruebas
4. **Escalar a HTTPS** cuando entre en producción
5. **Configurar Slack** si tienen workspace

---

**Versión:** 1.0  
**Fecha:** 2026-07-17  
**Status:** ✅ Listo para testing  
**Mantenedor:** Brain (Qamiluna)
