# Setup Qamiluna × Meta + Instagram + Google Sheets

## 📋 Checklist: Antes de activar

- [x] `.env` creado en `brain/.env`
- [x] Funciones de webhook en `brain/connectors.py`
- [x] Rutas HTTP en `brain/server.py`
- [ ] **Google Sheets creada** con 3 pestañas (tú)
- [ ] **Webhook configurado en Meta** (tú)
- [ ] **App Review iniciada** en Meta (tú)
- [ ] **Servidor corriendo en puerto 8000+** (tú)

---

## 1️⃣ Verificar que el `.env` está bien

```bash
cd C:\AGENTE TDA\llm-virtual-brain
cat brain/.env
```

**Debe tener estos campos completos (SIN "your/xxx"):**
```
META_APP_ID=982984821462535
META_APP_SECRET=<ver brain/.env>
META_ACCESS_TOKEN=<ver brain/.env>  (token largo)
META_AD_ACCOUNT_ID=act_925869830396990
INSTAGRAM_BUSINESS_ACCOUNT_ID=17841468292856605
WEBHOOK_VERIFY_TOKEN=<ver brain/.env>
GOOGLE_SHEETS_ID=1nfApWlPXdDJVCLDLnEI9HA1ttclQZCR4obSTNm2H5hw
GOOGLE_API_KEY=<ver brain/.env>
```

✅ Si está todo → Continúa

---

## 2️⃣ Verificar Google Sheets

### Estructura esperada

Abre: https://docs.google.com/spreadsheets/d/1nfApWlPXdDJVCLDLnEI9HA1ttclQZCR4obSTNm2H5hw/edit

**Debe tener 3 pestañas:**

#### Pestaña 1: `LEADS_INSTAGRAM`
| Timestamp | Nombre | Teléfono | Email | Interés | Ciudad | Score | Status | Asignada a | Fecha Contacto |
|---|---|---|---|---|---|---|---|---|---|
| *vacía* | *vacía* | *vacía* | ... | | | | | | |

#### Pestaña 2: `CONTACTOS_DIRECTOS`
| Timestamp | Nombre | Mensaje | Plataforma | Leído | Respondido | Asignada a |
|---|---|---|---|---|---|---|
| *vacía* | *vacía* | *vacía* | | | | |

#### Pestaña 3: `CAMPAÑAS_ADS`
| Fecha | Campaña | Objetivo | Spend ($) | Impressiones | Clicks | CTR (%) | Conversiones | ROAS | Status |
|---|---|---|---|---|---|---|---|---|---|
| *vacía* | *vacía* | *vacía* | | | | | | | |

✅ Si las 3 pestañas existen → Continúa

---

## 3️⃣ Configurar Meta Business Manager → Webhook

**EN: https://business.facebook.com/**

1. Menú izquierdo → **Configuración** → **Integraciones de aplicaciones**
2. Busca tu app **"Qamiluna Brain"** → Haz clic
3. Ir a **Producto: Instagram Lead Ads**
4. En **"URL de Webhook"**, pega:
   ```
   https://brain.qamiluna.com/webhooks/instagram/leads
   ```
   (En desarrollo local: `http://localhost:8000/webhooks/instagram/leads`)

5. En **"Token de Verificación"**, pega:
   ```
   <WEBHOOK_VERIFY_TOKEN de brain/.env>
   ```
6. Haz clic en **"Verificar y guardar"**
   - Meta hará un GET a tu URL con `?hub_mode=subscribe&hub_challenge=XXX&hub_verify_token=8c7d86...`
   - Brain debe retornar el challenge → webhook verificado ✅

7. En **"Suscribirse a eventos"**, abilita:
   - [ ] `leadgen` (CRÍTICO — sin esto no llegan los leads)
   - [ ] `messaging_postbacks` (opcional, para mensajes)

✅ Si Meta dice "Verificado" → Continúa

---

## 4️⃣ Crear una campaña de prueba con Lead Ads

**EN: https://business.facebook.com/ads/manager/**

1. Crea una campaña nueva (o usa una existente)
2. Objetivo: **Leads** o **Conversiones**
3. En el Ad Set, busca **"Lead Form"**
4. Crea un formulario con estos campos:
   - ✅ Full Name
   - ✅ Email
   - ✅ Phone Number
   - ✅ City
   - ✅ Interested In (dropdown: Novia Civil, Novia Fiesta, Social, Taller)

5. Activa la campaña

✅ Si la campaña está activa con Lead Form → Continúa

---

## 5️⃣ Test: Enviar un lead de prueba

1. Abre tu anuncio en vista previa
2. Completa el formulario de prueba:
   - Nombre: "Test Lead"
   - Email: "test@example.com"
   - Teléfono: "+56912345678"
   - Interés: "Novia Civil"
3. Envía el formulario

**Espera 30 segundos...**

Luego abre Google Sheets → Pestaña **LEADS_INSTAGRAM**:
- ¿Aparece una fila nueva con "Test Lead"?
- ¿El Score es 2 (por teléfono + email)?
- ¿El Status es "🆕"?

✅ **SI SÍ** → Flujo de leads funcionando 🎉

❌ **SI NO** → Revisa troubleshooting abajo

---

## 6️⃣ Activar Periodic Tasks (Ads & DMs)

Brain sincroniza automáticamente:
- **Meta Ads:** cada 6 horas
- **Instagram DMs:** cada 15 minutos

Cuando Brain arranca:
```bash
python -m brain.server --profiles profiles --port 8000
```

Verás en logs:
```
[periodic] Meta Ads synced at 2026-07-17T12:30:45.123456
[periodic] Instagram DMs synced at 2026-07-17T12:15:45.654321
```

✅ Si ves esos logs → Tasks corriendo

---

## 🔧 Troubleshooting

### ❌ "Webhook no verifica"

**Síntomas:** Meta dice "Token inválido" en webhook config

**Solución:**
1. Verifica que `WEBHOOK_VERIFY_TOKEN` en `.env` matches exactamente
2. Si cambiaste el token, recarga `.env`:
   ```bash
   # Detén el servidor, actualiza .env, reinicia
   ```
3. Verifica que Brain está corriendo en `http://localhost:8000` (desarrollo)

---

### ❌ "Leads llegan pero no aparecen en Sheets"

**Síntomas:** Logs muestran `[webhook] Lead capturado: ...` pero Sheets vacía

**Solución:**
1. Verifica que `GOOGLE_SHEETS_ID` es correcto:
   ```
   https://docs.google.com/spreadsheets/d/{GOOGLE_SHEETS_ID}/edit
                                           ^^^^^^^^ este parte
   ```
2. Verifica que `GOOGLE_API_KEY` funciona:
   ```bash
   curl "https://sheets.googleapis.com/v4/spreadsheets/GOOGLE_SHEETS_ID?key=GOOGLE_API_KEY"
   # Debe retornar JSON con los datos de la hoja
   ```
3. Si ambos son correctos pero sigue sin funcionar:
   - ¿Está la pestaña `LEADS_INSTAGRAM` con headers correctos?
   - ¿La API Key tiene permiso a Sheets API? (debe estar habilitada en Google Cloud)

---

### ❌ "DMs no se sincronizan"

**Síntomas:** Logs muestran `[dm_sync] Error:` o no hay logs

**Solución:**
1. Verifica que `META_ACCESS_TOKEN` tiene scope `instagram_manage_messages`
2. Verifica que `INSTAGRAM_BUSINESS_ACCOUNT_ID` es correcto (17841468292856605)
3. Envía un DM a @qamiluna_studio desde otra cuenta Instagram
4. Espera 15+ minutos (intervalo de sync)
5. Abre Sheets → `CONTACTOS_DIRECTOS` → ¿Aparece el DM?

---

### ❌ "Ads sync reporta ROAS but no values"

**Síntomas:** Logs muestran `[ads_sync] Error: ...`

**Solución:**
1. Verifica que `META_AD_ACCOUNT_ID` es `act_925869830396990`
2. Verifica que la campaña tiene gasto (>$0)
3. Meta requiere ~24h para procesar métricas; si creaste ad recién, espera

---

## 📊 Monitoreo en vivo

### Logs en tiempo real

```bash
# Terminal 1: Corre Brain
python -m brain.server --profiles profiles --port 8000

# Terminal 2: Monitorea Sheets (opcional)
watch -n 5 'curl -s "https://docs.google.com/spreadsheets/d/1nfApWlPXdDJVCLDLnEI9HA1ttclQZCR4obSTNm2H5hw/export?format=csv&gid=0" | head -5'
```

### Verificar que webhooks llegan

```bash
# Meta enviará este GET para verificación inicial:
curl "http://localhost:8000/webhooks/instagram/leads?\
hub_mode=subscribe&\
hub_challenge=12345&\
hub_verify_token=<WEBHOOK_VERIFY_TOKEN de brain/.env>"

# Debe retornar: 12345 (el challenge)
```

---

## 🚀 Siguientes pasos

Cuando todo esté funcionando:

1. **Entrenar al equipo (Cami, Paz, Mou, Andrea):**
   - Mostrarles cómo ver leads en Sheets
   - Cómo cambiar Status de 🆕 → 📞 → ✅
   - Cómo responder DMs (manualmente, desde Instagram)

2. **Activar notificaciones:**
   - Si tienen Slack, configura `SLACK_WEBHOOK` en `.env`
   - Recibirán alertas cuando llegen leads nuevos

3. **Configurar alertas de ROAS bajo:**
   - Cuando ROAS < 2, Sheets marca ⚠️ Revisar
   - El equipo puede revisar campañas baja performance

4. **Escalar para producción:**
   - Usar Long-Lived Access Token (vs. 60-day)
   - Usar Google Service Account (vs. API Key simple)
   - Migrar a HTTPS + dominio real (https://brain.qamiluna.com)

---

## 📞 Soporte

- **Error en webhook:** Revisa logs de Brain + verifica token en Meta
- **Sheets no recibe:** Revisa GOOGLE_SHEETS_ID + API Key permissions
- **DMs no llegan:** Verifica scope `instagram_manage_messages` en token
- **Ads metrics vacías:** Espera 24h después de crear campaña; Meta procesa lento

---

**Última actualización:** 2026-07-17  
**Estado:** ✅ Pronto para testing  
**Equipo:** Cami, Paz, Mou, Andrea
