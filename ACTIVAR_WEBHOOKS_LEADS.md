# Activar Webhooks de Brain para Capturar Leads en Vivo

## Objetivo
Configurar Instagram Lead Ads → Meta Webhooks → Brain → Google Sheets de forma automática

---

## ✅ Estado Actual

- ✅ @qamiluna_studio **conectada a Meta Business Manager**
- ✅ `.env` configurado en `brain/` con credenciales
- ✅ Funciones de webhook en `brain/connectors.py`
- ✅ Rutas HTTP en `brain/server.py`
- ✅ Google Sheets lista con 3 pestañas

---

## 🔧 Paso 1: Iniciar Brain

### En tu terminal (PowerShell o CMD):

```bash
cd C:\AGENTE TDA\llm-virtual-brain

# Opción 1: Iniciar Brain (si Python está instalado)
python -m brain.server --profiles profiles --port 8000

# O si tienes poetry/venv:
poetry run python -m brain.server --profiles profiles --port 8000
```

**Deberías ver en la terminal:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

✅ Si ves esto → **Brain está corriendo correctamente**

---

## 🎯 Paso 2: Configurar Webhook en Meta Business Manager

### En https://business.facebook.com/

1. Ve a **Configuración > Integraciones de aplicaciones**
2. Busca y abre tu app **"Qamiluna Brain"**
3. Selecciona **Producto: Instagram**
4. Busca la sección **"Webhooks"** o **"Configuración de webhook"**
5. En **URL de Webhook**, ingresa:
   ```
   http://localhost:8000/webhooks/instagram/leads
   ```
   (Si estás en producción: https://brain.qamiluna.com/webhooks/instagram/leads)

6. En **Token de Verificación**, ingresa:
   ```
   <WEBHOOK_VERIFY_TOKEN de brain/.env>
   ```

7. Haz clic en **Verificar y guardar**
   - Meta enviará un GET request a tu webhook
   - Brain responderá automáticamente con el token
   - ✅ Deberá decir "Verificado"

8. En **Suscribirse a eventos**, abilita:
   - ☑️ **leadgen** (CRÍTICO — sin esto no llegan los leads)
   - ☑️ **messaging_postbacks** (opcional)

9. Haz clic en **Guardar cambios**

---

## 📊 Paso 3: Verificar Google Sheets

Abre tu Google Sheet: https://docs.google.com/spreadsheets/d/1nfApWlPXdDJVCLDLnEI9HA1ttclQZCR4obSTNm2H5hw/edit

Verifica que tengas **3 pestañas:**
- ✅ `LEADS_INSTAGRAM`
- ✅ `CONTACTOS_DIRECTOS`
- ✅ `CAMPAÑAS_ADS`

Cada pestaña debe tener sus headers en la fila 1.

---

## 🧪 Paso 4: Test de Lead (Verificación)

### Opción A: Desde tu anuncio de Instagram (Lo mejor)

1. Abre tu campaña de Meta Ads que tiene **Lead Form**
2. Abre la vista previa del anuncio
3. Completa el formulario de prueba:
   - **Nombre:** "Test Lead Qamiluna"
   - **Email:** "test@qamiluna.com"
   - **Teléfono:** "+56994831974"
   - **Interés:** "Novia Civil"

4. Envía el formulario

### Opción B: Desde Meta Ads Manager (Alternativa)

1. Ve a **Ads Manager > Tu Campaña**
2. En el Ad Set, busca **"Lead Form Preview"**
3. Completa el formulario de prueba
4. Envía

---

## ✅ Verificar que Funcionó

### En la Terminal (donde corre Brain):

Deberías ver logs similares a:
```
[webhook] Lead capturado: Test Lead Qamiluna (Novia Civil)
[notify] Email sería enviado a: ['cami@qamiluna.com', 'paz@qamiluna.com', 'mou@qamiluna.com']
[gsheet] Lead insertado en LEADS_INSTAGRAM
```

### En Google Sheets:

Abre la pestaña **`LEADS_INSTAGRAM`**:

Deberías ver una **fila nueva**:
| Timestamp | Nombre | Teléfono | Email | Interés | Ciudad | Score | Status | Asignada a | Fecha Contacto |
|---|---|---|---|---|---|---|---|---|---|
| 2026-07-17 14:32 | Test Lead Qamiluna | +56994831974 | test@qamiluna.com | Novia Civil | — | 2 | 🆕 | — | — |

✅ **¡¡SI VES ESTO, TODO FUNCIONA!!** 🎉

---

## 🔄 Paso 5: Sincronizaciones Automáticas

Una vez verificado que funciona, Brain sincroniza automáticamente:

### Meta Ads Insights (cada 6 horas)
- Escribe en pestaña: `CAMPAÑAS_ADS`
- Métricas: Spend, ROAS, Impressiones, Conversiones
- Si ROAS < 2 → marca como ⚠️ Revisar

### Instagram DMs (cada 15 minutos)
- Escribe en pestaña: `CONTACTOS_DIRECTOS`
- Captura: últimos mensajes sin responder
- Estado: Leído ✅ pero NO respondido (manual)

---

## 🆘 Troubleshooting

### ❌ "Webhook no verifica"

**Problema:** Meta dice "Token inválido"

**Solución:**
1. Verifica que `WEBHOOK_VERIFY_TOKEN` en `.env` sea:
   ```
   <WEBHOOK_VERIFY_TOKEN de brain/.env>
   ```
2. Verifica que Brain está corriendo (`python -m brain.server`)
3. Intenta nuevamente

### ❌ "Lead capturado pero no aparece en Sheets"

**Problema:** Terminal muestra "[webhook] Lead capturado..." pero Sheets vacía

**Solución:**
1. Verifica que `GOOGLE_SHEETS_ID` en `.env` sea:
   ```
   1nfApWlPXdDJVCLDLnEI9HA1ttclQZCR4obSTNm2H5hw
   ```
2. Verifica que `GOOGLE_API_KEY` esté correcto
3. Verifica que la pestaña `LEADS_INSTAGRAM` existe en Sheets
4. Intenta nuevamente desde Meta

### ❌ "Brain no inicia"

**Problema:** Error al ejecutar `python -m brain.server`

**Solución:**
```bash
# Verifica que Python está instalado
python --version  # debe ser 3.8+

# Verifica que .env existe
ls brain/.env     # debe existir

# Reinstala dependencias
pip install -r requirements.txt

# Intenta de nuevo
python -m brain.server --profiles profiles --port 8000
```

### ❌ "Leads desde Brave, pero no desde Chrome"

**Problema:** El webhook funciona en Brave pero no en Chrome

**Solución:**
- Esto es raro, pero significa que el navegador del usuario afecta. No es un problema de Brain.
- Webhook está corriendo en tu servidor, no en el navegador.
- Intenta crear un lead desde Instagram app (celular) — no desde navegador.

---

## 📋 Checklist Final

Antes de considerar que está listo:

- [ ] Brain corre sin errores (`python -m brain.server`)
- [ ] Webhook verificado en Meta Business Manager ✅
- [ ] Google Sheets tiene 3 pestañas con headers
- [ ] Test de lead se insertó en `LEADS_INSTAGRAM`
- [ ] DMs de Instagram aparecen en `CONTACTOS_DIRECTOS` (después de 15 min)
- [ ] Campañas de Meta aparecen en `CAMPAÑAS_ADS` (después de 6 horas)

---

## 🚀 ¡Listo!

Una vez que completes estos pasos:

✅ **Leads en vivo** desde Instagram → Sheets automáticamente
✅ **DMs** sincronizados cada 15 minutos
✅ **Métricas de Ads** actualizadas cada 6 horas
✅ **Equipo de Qamiluna** puede ver todo en una sola Sheets

---

## 📞 Siguiente Paso

Una vez que todo esté funcionando, avísame:

1. ¿Viste el test de lead en Google Sheets?
2. ¿Brain está corriendo sin errores?
3. ¿Meta Business Manager verificó el webhook?

Si es sí a los 3 → **¡¡Estamos LISTOS para producción!!** 🎉

---

**Fecha:** 2026-07-17  
**Versión:** 1.0  
**Para:** Qamiluna Studio

¡Adelante! 🚀
