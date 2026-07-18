/**
 * GAS Web App para leads de Qamiluna: recibe filas desde Brain y las
 * escribe en el Google Sheet de leads (LEADS_INSTAGRAM, CONTACTOS_DIRECTOS,
 * CAMPAÑAS_ADS).
 *
 * CÓMO DESPLEGAR (5 minutos):
 * 1. Abre https://script.google.com → "Nuevo proyecto"
 * 2. Borra el contenido y pega este archivo completo
 * 3. Guarda (Ctrl+S), nómbralo "Qamiluna Leads"
 * 4. Implementar → Nueva implementación → tipo "Aplicación web"
 *    - Ejecutar como: Tú (tu cuenta)
 *    - Acceso: Cualquier usuario
 * 5. Autoriza los permisos cuando lo pida
 * 6. Copia la URL /exec y pégala en brain/.env:
 *       LEADS_GAS_URL=https://script.google.com/macros/s/.../exec
 * 7. Reinicia Brain
 */

// ID del Sheet de Qamiluna (fallback si Brain no envía spreadsheetId)
var DEFAULT_SPREADSHEET_ID = "1nfApWlPXdDJVCLDLnEI9HA1ttclQZCR4obSTNm2H5hw";

function doGet(e) {
  return _json({ ok: true, service: "Qamiluna Leads GAS", version: "1.0" });
}

function doPost(e) {
  var body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    // Compatibilidad con form-encoded (action=...&rows=[...])
    body = e.parameter || {};
    if (typeof body.headers === "string") body.headers = JSON.parse(body.headers || "[]");
    if (typeof body.rows === "string") body.rows = JSON.parse(body.rows || "[]");
  }

  var action = body.action || "";
  if (action === "appendRows") return appendRows(body);
  return _json({ ok: false, error: "acción desconocida: " + action });
}

function appendRows(body) {
  try {
    var ssId = body.spreadsheetId || DEFAULT_SPREADSHEET_ID;
    var ss = SpreadsheetApp.openById(ssId);
    var sheetName = body.sheet || "LEADS_INSTAGRAM";
    var headers = body.headers || [];
    var rows = body.rows || [];

    var sh = ss.getSheetByName(sheetName);
    if (!sh) {
      sh = ss.insertSheet(sheetName);
      if (headers.length) {
        sh.appendRow(headers);
        sh.setFrozenRows(1);
      }
    }

    if (rows.length) {
      var width = headers.length || rows[0].length;
      sh.getRange(sh.getLastRow() + 1, 1, rows.length, width)
        .setValues(rows.map(function (r) {
          r = r.slice();
          while (r.length < width) r.push("");
          return r.slice(0, width);
        }));
    }

    return _json({ ok: true, sheet: sheetName, appended: rows.length, lastRow: sh.getLastRow() });
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
