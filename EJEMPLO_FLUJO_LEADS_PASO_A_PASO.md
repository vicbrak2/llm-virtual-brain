# Ejemplo Práctico: Flujo de Leads en Vivo 📱 → 📊

## El Escenario Real

**Andrea** ve un anuncio de Qamiluna en Instagram y quiere reservar maquillaje para su boda.

---

## 🎬 **PASO 1: Andrea Ve el Anuncio**

**Hora:** 2026-07-17 14:32 UTC

**Dónde:** Instagram Stories / Feed

**Anuncio:**
```
💄 Maquillaje de Novia Profesional
✨ Equipo Certificado | Prueba Incluida
💰 Desde $180.000

[Ver más] ← Andrea toca aquí
```

---

## 📝 **PASO 2: Andrea Completa el Formulario de Lead**

**Formulario que ve en Instagram:**

```
┌─────────────────────────────────────┐
│  Qamiluna Studio                    │
│  Cuéntanos sobre tu evento          │
├─────────────────────────────────────┤
│                                     │
│ Nombre completo *                   │
│ [Andrea Martínez              ]     │
│                                     │
│ Email *                             │
│ [andrea.martinez@mail.com     ]     │
│                                     │
│ Teléfono *                          │
│ [+56912345678                 ]     │
│                                     │
│ Ciudad *                            │
│ [Santiago                     ▼]    │
│                                     │
│ ¿En qué estás interesada? *         │
│ [Novia Civil                  ▼]    │
│                                     │
│        [Enviar Formulario]          │
│                                     │
└─────────────────────────────────────┘
```

**Andrea llena:**
- Nombre: Andrea Martínez
- Email: andrea.martinez@mail.com
- Teléfono: +56912345678
- Ciudad: Santiago
- Interés: Novia Civil

Andrea toca **[Enviar Formulario]**

---

## 🔄 **PASO 3: Meta Captura el Lead**

**Qué pasa DETRÁS DE CÁMARAS (en Meta Ads):**

Meta recibe el lead y lo registra:

```json
{
  "entry": [{
    "leadgen": [{
      "id": "lead_abc123456",
      "created_time": 1689600723,
      "field_data": [
        {
          "name": "full_name",
          "values": ["Andrea Martínez"]
        },
        {
          "name": "email",
          "values": ["andrea.martinez@mail.com"]
        },
        {
          "name": "phone_number",
          "values": ["+56912345678"]
        },
        {
          "name": "city",
          "values": ["Santiago"]
        },
        {
          "name": "interested_in",
          "values": ["Novia Civil"]
        }
      ]
    }]
  }]
}
```

Meta tiene el lead registrado en sus servidores. Pero Qamiluna **no lo sabe aún**.

---

## 🎯 **PASO 4: Meta Envía Webhook a Brain**

**Hora:** 14:32:01 (1 segundo después)

Meta realiza una **solicitud HTTPS POST** a Brain:

```http
POST http://localhost:8000/webhooks/instagram/leads HTTP/1.1
Content-Type: application/json
Authorization: Bearer [token]

{
  "entry": [{
    "leadgen": [{
      "id": "lead_abc123456",
      "created_time": 1689600723,
      "field_data": [
        {"name": "full_name", "values": ["Andrea Martínez"]},
        {"name": "email", "values": ["andrea.martinez@mail.com"]},
        {"name": "phone_number", "values": ["+56912345678"]},
        {"name": "city", "values": ["Santiago"]},
        {"name": "interested_in", "values": ["Novia Civil"]}
      ]
    }]
  }]
}
```

**Brain recibe este JSON en el webhook y ejecuta:**

```python
# brain/connectors.py - handle_instagram_leads_webhook()

1. Extrae datos del JSON:
   - name = "Andrea Martínez"
   - phone = "+56912345678"
   - email = "andrea.martinez@mail.com"
   - interest = "Novia Civil"
   - city = "Santiago"

2. Calcula SCORE:
   - ¿Tiene teléfono? ✅ +1 punto
   - ¿Tiene email? ✅ +1 punto
   - SCORE FINAL = 2 (máximo)

3. Crea un timestamp:
   - timestamp = "2026-07-17 14:32:01"

4. Genera una fila para Sheets:
   [
     "2026-07-17 14:32:01",     # Timestamp
     "Andrea Martínez",          # Nombre
     "+56912345678",             # Teléfono
     "andrea.martinez@mail.com", # Email
     "Novia Civil",              # Interés
     "Santiago",                 # Ciudad
     2,                          # Score
     "🆕",                       # Status (Nuevo)
     "",                         # Asignada a (vacío - manual)
     ""                          # Fecha Contacto (vacío - manual)
   ]
```

---

## 📊 **PASO 5: Brain Inserta en Google Sheets**

**Hora:** 14:32:02 (2 segundos después)

Brain usa la **Google Sheets API** para agregar la fila:

```python
# Llamada a Google Sheets API
sheets.values().append(
    spreadsheetId="1nfApWlPXdDJVCLDLnEI9HA1ttclQZCR4obSTNm2H5hw",
    range="LEADS_INSTAGRAM!A:J",
    values=[[
        "2026-07-17 14:32:01",
        "Andrea Martínez",
        "+56912345678",
        "andrea.martinez@mail.com",
        "Novia Civil",
        "Santiago",
        2,
        "🆕",
        "",
        ""
    ]]
)
```

**Google Sheets se actualiza AUTOMÁTICAMENTE:**

```
┌───────────────────┬──────────────────┬────────────────┬──────────────────────┬──────────────┬─────────┬───────┬────────┬────────────┬─────────────────┐
│ Timestamp         │ Nombre           │ Teléfono       │ Email                │ Interés      │ Ciudad  │ Score │ Status │ Asignada a │ Fecha Contacto  │
├───────────────────┼──────────────────┼────────────────┼──────────────────────┼──────────────┼─────────┼───────┼────────┼────────────┼─────────────────┤
│ 2026-07-17 14:32  │ Andrea Martínez  │ +56912345678   │ andrea.martinez@...  │ Novia Civil  │ Santiago│   2   │  🆕   │     —      │        —        │
└───────────────────┴──────────────────┴────────────────┴──────────────────────┴──────────────┴─────────┴───────┴────────┴────────────┴─────────────────┘
```

---

## 📧 **PASO 6: Brain Notifica al Equipo**

**Hora:** 14:32:03 (3 segundos después)

Brain envía **email a:**
- cami@qamiluna.com
- paz@qamiluna.com
- mou@qamiluna.com

**Asunto:** 📩 Nuevo lead de Instagram: Andrea Martínez (Novia Civil)

**Contenido:**
```
Hola equipo,

Nuevo lead llegó en vivo:

📱 Nombre: Andrea Martínez
📞 Teléfono: +56912345678
📧 Email: andrea.martinez@mail.com
💄 Interés: Novia Civil
📍 Ciudad: Santiago
⭐ Score: 2/2 (teléfono + email)

👉 Ver en Sheets: [link a Sheets]

---
Brain | Qamiluna Studio
```

---

## ✅ **PASO 7: Equipo de Qamiluna Actúa**

### **Opción A: Cami Responde por WhatsApp (Manual)**

**14:32:15** — Cami ve el email y el lead en Sheets

Cami abre WhatsApp y envía:

```
Hola Andrea 👋

Gracias por tu interés en Qamiluna Studio ✨

Vi que te interesa maquillaje de novia civil. Nos encantaría ayudarte.

¿Cuál es tu fecha de boda? Podríamos agendar una prueba de maquillaje sin costo.

Quedamos atentas 💄
```

### **Opción B: Paz Actualiza el Sheets**

Paz cambia el Status del lead:

```
Status: 🆕  →  📞 (Contactada)
Asignada a: —  →  Paz
Fecha Contacto: —  →  2026-07-17 14:32
```

---

## 📈 **TIMELINE COMPLETO (Desde que Andrea Toca el Anuncio)**

```
14:32:00 ← Andrea ve anuncio y toca [Ver más]
14:32:01 ← Andrea completa y envía formulario
14:32:02 ← Meta recibe lead en sus servidores
14:32:03 ← Meta envía webhook a Brain
14:32:04 ← Brain recibe y procesa JSON
14:32:05 ← Brain inserta en Google Sheets
14:32:06 ← Sheets se actualiza (visible para Cami, Paz, Mou)
14:32:07 ← Email llega a cami@qamiluna.com
14:32:15 ← Cami ve el email y el Sheets actualizado
14:32:20 ← Cami responde por WhatsApp

Total: 20 SEGUNDOS desde que Andrea toca hasta que recibe respuesta 🚀
```

---

## 🔍 **Qué Ve Cada Persona**

### **Andrea (Cliente)**
```
✅ Anuncio → Completa formulario → Vuelve a Instagram
(Quizás no ve nada más, pero su lead ya está capturado)
```

### **Cami, Paz, Mou (Equipo Qamiluna)**
```
📧 Email automático: "Nuevo lead de Instagram"
📊 Google Sheets: LEADS_INSTAGRAM actualizado en vivo
💬 WhatsApp: Pueden responder inmediatamente
```

### **Brain (Servidor)**
```
🔄 Recibe webhook de Meta
⚙️ Procesa datos
📤 Inserta en Google Sheets
📬 Envía email al equipo
📊 Sincroniza datos
```

---

## 💡 **Lo Más Importante**

| Aspecto | Tiempo | Beneficio |
|---|---|---|
| **Lead capturado** | 1 segundo después de enviar | Sin demora |
| **En Google Sheets** | 2-3 segundos después | Visible para todo el equipo |
| **Email de notificación** | 3-5 segundos después | Cami/Paz saben inmediatamente |
| **Respuesta del equipo** | ~20 segundos después | Antes de que Andrea se vaya a otro anuncio |

---

## 🎯 **Flujo Visual Completo**

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ANDREA EN INSTAGRAM                                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 💄 Maquillaje de Novia Profesional                       │  │
│  │ ✨ Equipo Certificado | Prueba Incluida                 │  │
│  │ 💰 Desde $180.000                                        │  │
│  │ [Completa Formulario]                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                          ↓                                       │
│                   Meta Ads Manager                               │
│                   (Captura el lead)                              │
│                          ↓                                       │
│              📤 WEBHOOK a Brain                                  │
│         POST /webhooks/instagram/leads                          │
│              JSON con datos de Andrea                           │
│                          ↓                                       │
│                    BRAIN SERVER                                  │
│              (Procesa y envía a Sheets)                         │
│                          ↓                                       │
│         ┌─────────────────────────────────┐                    │
│         │   GOOGLE SHEETS (En Vivo)       │                    │
│         ├─────────────────────────────────┤                    │
│         │ Andrea Martínez | +56912345678  │                    │
│         │ Novia Civil | Santiago | 🆕     │                    │
│         └─────────────────────────────────┘                    │
│                   ↙        ↓        ↖                           │
│             Cami        Paz       Mou                           │
│         (Ven el lead y responden por WhatsApp)                 │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🧪 **Test Real: Ahora Mismo**

Si ahora creas un lead de prueba en tu anuncio:

1. **Meta recibe** → 1 segundo
2. **Brain procesa** → 2 segundos
3. **Sheets actualiza** → 3 segundos (puedes refrescar y verlo)
4. **Email llega** → 5 segundos (revisa tu bandeja de entrada)

**TODO en 5 segundos. Automático. Sin que nadie haga nada. 🤖**

---

## ✨ **El Poder de Esto**

Antes de Brain:
- ❌ Andrea completa el formulario en Instagram
- ❌ Qamiluna NO sabe que existe
- ❌ 24 horas después descubren el lead (si lo revisan)
- ❌ Andrea ya contrató a otra empresa

Después de Brain:
- ✅ Andrea completa el formulario
- ✅ **Cami sabe en 5 segundos**
- ✅ **Cami responde en 20 segundos**
- ✅ **Andrea ve que hay gente real detrás** → Mayor confianza

---

## 🎬 **Próximo Paso**

Ahora que entiendes el flujo:

1. Configura el webhook en Meta Business Manager
2. Crea un lead de prueba
3. Mira cómo aparece en Google Sheets en VIVO
4. Recibe el email de notificación

**¿Listo para probar? 🚀**

---

**Versión:** 1.0  
**Fecha:** 2026-07-17  
**Ejemplo:** Andrea - Novia Civil en Santiago
