# Verificación del Negocio en Meta — Último Paso para Leads Reales

**Para:** Camila (admin de Qamiluna Studio)
**Estado del sistema:** Todo el pipeline técnico está funcionando y verificado. Solo falta este trámite administrativo para que Meta entregue leads reales.

---

## ¿Por qué es necesario?

La app está en **Modo Desarrollo** ("Sin publicar"). Meta NO entrega leads de producción
(ni siquiera los de prueba del equipo) a apps sin publicar. Para publicarla, Meta exige
la **Verificación del negocio**: comprobar que Qamiluna Studio es un negocio real.

Es el proceso estándar para cualquier empresa que captura leads. Se hace una sola vez.

---

## Paso 1: Subir el ícono de la app (2 minutos)

1. Ve a: https://developers.facebook.com/apps/956394080206503/settings/basic/
2. Busca el recuadro **"Ícono de la app"** (dice "Arrastra y suelta el archivo")
3. Arrastra el archivo `qamiluna_icon.png` que está en la carpeta del proyecto
   (`C:\AGENTE TDA\llm-virtual-brain\qamiluna_icon.png`) — o usa cualquier logo
   de Qamiluna en 1024×1024 px
4. Clic en **Guardar cambios** (abajo a la derecha)

## Paso 2: Iniciar la Verificación del Negocio (10-15 minutos)

1. Ve a: https://developers.facebook.com/apps/956394080206503/go_live/
2. En la sección **"Verificación del negocio"** (aparece "Qamiluna Studio — No verificado"),
   haz clic en **"Iniciar verificación"**
3. Meta te pedirá:
   - **Datos del negocio:** nombre legal, dirección, teléfono, sitio web (puede ser
     el Instagram: https://www.instagram.com/qamiluna_studio)
   - **Documentos** (uno o más de estos, según el país):
     - Inicio de actividades / RUT de empresa (SII en Chile)
     - Patente comercial o certificado de registro
     - Factura de servicios a nombre del negocio (luz, agua, teléfono)
     - Estados de cuenta bancarios del negocio
   - **Verificación de contacto:** un código que llega por teléfono, email o dominio
4. Envía la solicitud

**Tiempo de revisión de Meta:** normalmente 1 a 5 días hábiles.
Te llegará una notificación al email de la cuenta (c.villalobosba@gmail.com).

## Paso 3: Publicar la app (1 clic, después de la aprobación)

1. Cuando la verificación diga ✅ **Verificado**, vuelve a:
   https://developers.facebook.com/apps/956394080206503/go_live/
2. Haz clic en el botón **"Publicar"** (abajo a la derecha, se habilitará)
3. Listo — la app pasa a modo **Activo**

## Paso 4: Probar con un lead real (5 minutos)

1. Verifica que Brain y el túnel estén corriendo en la PC (ver sección siguiente)
2. Ve a: https://developers.facebook.com/tools/lead-ads-testing
3. Página: Qamiluna Studio · Formulario: "Maquillaje Novias Qamiluna"
4. Clic en **"Crear cliente potencial"**
5. En menos de 30 segundos deberías ver la fila nueva en la pestaña
   `LEADS_INSTAGRAM` del Google Sheet

---

## Qué debe estar corriendo en la PC para recibir leads

```powershell
# 1. Brain (servidor de leads)
cd "C:\AGENTE TDA\llm-virtual-brain"
python -m brain.server --profiles profiles --port 8000

# 2. Túnel público (en otra terminal)
cloudflared tunnel --url http://localhost:8000
```

⚠️ **Importante — URL del túnel:** cada vez que `cloudflared` se reinicia, la URL
pública cambia (es un túnel gratuito "quick"). Cuando eso pase, hay que actualizar
la nueva URL en Meta:

- Panel: https://developers.facebook.com/apps/956394080206503/webhooks
- Productos **Instagram** y **Page** → campo "URL de devolución de llamada"
- Formato: `https://<nueva-url>.trycloudflare.com/webhooks/instagram/leads`
- Token de verificación: el `WEBHOOK_VERIFY_TOKEN` de `brain/.env`

(Alternativa a futuro: túnel con dominio fijo de Cloudflare —requiere cuenta gratis
y un dominio— o desplegar Brain en un servidor. Así la URL nunca cambia.)

---

## Arquitectura ya verificada (no tocar, funciona)

```
Instagram Lead Ad (formulario "Maquillaje Novias Qamiluna")
      ↓ automático
Meta (webhook leadgen)                                  ✅ probado con muestra oficial
      ↓ HTTPS
Túnel Cloudflare → Brain (localhost:8000)               ✅ Meta entregó webhooks reales
      ↓
Brain busca los datos del lead vía Graph API            ✅ token con leads_retrieval
      ↓                                                    (token de página, nunca vence)
Google Sheet LEADS_INSTAGRAM vía GAS                    ✅ 2 leads de prueba insertados
      ↓ (si Sheets falla)
Cola local brain/pending_leads.jsonl                    ✅ reintento automático cada 15 min
```

**Ningún lead se pierde:** si el Sheet o el GAS fallan, el lead queda en la cola local
y se reinserta solo. Si Brain está apagado, Meta reintenta la entrega por horas y los
leads quedan guardados 90 días en Meta (recuperables con la herramienta de descarga
de formularios en Meta Business Suite).

---

**Fecha:** 2026-07-18
**App:** tt (956394080206503) · Página: Qamiluna Studio (943591052179865)
**Formulario:** Maquillaje Novias Qamiluna
