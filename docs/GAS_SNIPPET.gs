/**
 * Snippet para Google Apps Script: registrar documentos TXT del Brain Server
 * en una hoja de cálculo (base de datos).
 *
 * 1. Pega esta función en tu proyecto GAS (junto a tu doPost/doGet existente,
 *    o crea un proyecto nuevo standalone).
 * 2. En doPost, enruta action=registerDocument hacia registerDocument(e).
 * 3. Implementa/despliega como Web App (ejecutar como tú, acceso: cualquiera).
 * 4. Pon la URL /exec en el perfil YAML:  storage: { gas_url: "...", sheet: "Documentos" }
 */

function doPost(e) {
  var action = (e.parameter.action || "");
  if (action === "registerDocument") return registerDocument(e);
  return ContentService.createTextOutput(
    JSON.stringify({ ok: false, error: "acción desconocida: " + action })
  ).setMimeType(ContentService.MimeType.JSON);
}

function registerDocument(e) {
  var p = e.parameter;
  var ss = getOrCreateSpreadsheet_("Brain DB");
  var sheetName = p.sheet || "Documentos";
  var sh = ss.getSheetByName(sheetName);
  if (!sh) {
    sh = ss.insertSheet(sheetName);
    sh.appendRow(["Fecha", "Perfil", "Archivo", "Caracteres", "Contenido"]);
    sh.setFrozenRows(1);
  }
  sh.appendRow([
    p.ts || new Date().toISOString(),
    p.profile || "",
    p.name || "",
    Number(p.chars || 0),
    (p.content || "").substring(0, 45000), // límite práctico por celda
  ]);
  return ContentService.createTextOutput(
    JSON.stringify({ ok: true, sheet: sheetName, row: sh.getLastRow() })
  ).setMimeType(ContentService.MimeType.JSON);
}

/** Standalone-safe: los proyectos no ligados a una hoja no tienen "active spreadsheet". */
function getOrCreateSpreadsheet_(name) {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty("BRAIN_DB_ID");
  if (id) {
    try { return SpreadsheetApp.openById(id); } catch (err) {}
  }
  var ss = SpreadsheetApp.create(name);
  props.setProperty("BRAIN_DB_ID", ss.getId());
  return ss;
}
