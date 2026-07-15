"""
Brain Server: API HTTP para la interfaz de chat unificada.

Expone Brain como servicio: chat multi-provider, perfiles conmutables,
subida de archivos TXT que se registran como "base de datos" (Google Sheets
vía GAS si el perfil lo configura, y siempre en un registro local JSON).

Uso:
    pip install "llm-virtual-brain[server]"
    python -m brain.server --profiles ./profiles --port 8080

Perfiles: archivos YAML en --profiles (formato BrainConfig) con extras opcionales:
    description: "Asistente de precios"
    storage:
      gas_url: "https://script.google.com/macros/s/.../exec"   # opcional → Sheets
      sheet: "Documentos"                                       # hoja destino
"""

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import load_config_from_yaml, _substitute_env_vars
from .core import Brain

MAX_DOC_CHARS = 60_000          # límite por documento subido
CONTEXT_BUDGET_CHARS = 12_000   # presupuesto de contexto de documentos por chat

# ── Formato de intercambio con agentes externos ─────────────────────────────
# El prompt generado le exige al agente externo responder SOLO con este XML;
# /api/import lo parsea, lo persiste (local + Sheets) y lo suma al contexto.
IMPORT_FORMAT_SPEC = """FORMATO DE RESPUESTA OBLIGATORIO — responde ÚNICAMENTE con este bloque XML, sin texto antes ni después:

<brain-import profile="{profile}" sheet="{sheet}">
  <schema>
{schema_fields}
  </schema>
  <row>
{example_row}
  </row>
  <!-- repite <row> por cada registro -->
</brain-import>

REGLAS DEL FORMATO:
1. Solo el XML. Sin markdown, sin ```, sin explicaciones.
2. Cada <row> debe tener exactamente los campos del <schema>, en el mismo orden.
3. Valores de texto plano (sin HTML). Usa "" si un dato no existe.
4. Números sin separador de miles; decimales con punto.
5. Escapa los caracteres especiales XML: & → &amp;  < → &lt;  > → &gt;"""


# ── Creación de sub-agentes desde el chat (perfil "creador") ────────────────
# Cuando el creador confirma un agente, su respuesta incluye un bloque
# <brain-agent>; el server lo materializa: YAML + perfil vivo + registro en Sheets.
def parse_brain_agent(content: str) -> Optional[Dict]:
    """Extraer el primer bloque <brain-agent> (spec de un sub-agente)."""
    match = re.search(r"<brain-agent\b.*?</brain-agent>", content, re.DOTALL)
    if not match:
        return None
    try:
        root = ET.fromstring(match.group(0))
    except ET.ParseError as e:
        raise ValueError(f"XML de brain-agent inválido: {e}")
    def txt(tag):
        el = root.find(tag)
        return (el.text or "").strip() if el is not None else ""
    spec = {
        "nombre": txt("nombre"),
        "descripcion": txt("descripcion"),
        "prompt": txt("prompt"),
    }
    if not spec["nombre"] or not spec["prompt"]:
        raise ValueError("brain-agent requiere <nombre> y <prompt>")
    return spec


def slugify(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s or "agente"


def parse_brain_import(content: str) -> Optional[Dict]:
    """Extraer y parsear el primer bloque <brain-import> de un texto.
    Devuelve {profile, sheet, headers, rows} o None si no hay bloque."""
    match = re.search(r"<brain-import\b.*?</brain-import>", content, re.DOTALL)
    if not match:
        return None
    xml_text = match.group(0)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"XML inválido: {e}")

    headers: List[str] = [
        f.get("name", "").strip()
        for f in root.findall("./schema/field")
        if f.get("name", "").strip()
    ]
    rows: List[List[str]] = []
    for row_el in root.findall("./row"):
        if not headers:  # sin schema explícito: inferir del primer row
            headers = [child.tag for child in row_el]
        row_map = {child.tag: (child.text or "").strip() for child in row_el}
        rows.append([row_map.get(h, "") for h in headers])

    if not headers or not rows:
        raise ValueError("El bloque brain-import no tiene schema/filas válidas")

    return {
        "profile": root.get("profile", ""),
        "sheet": root.get("sheet", "Datos"),
        "headers": headers,
        "rows": rows,
    }


class ChatRequest(BaseModel):
    message: str
    history: List[Dict] = []
    profile: Optional[str] = None
    max_tokens: int = 1400  # con margen para modelos razonadores (reasoning + respuesta)
    temperature: float = 0.3
    refine: bool = True  # pipeline multi-LLM (borrador → refina → final) con trace


class ActivateRequest(BaseModel):
    name: str


class UpdateProfileRequest(BaseModel):
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None       # etapa "chat" del agente
    links: Optional[List[str]] = None  # perfiles cuyo contexto se comparte con este
    connectors: Optional[List[Dict]] = None  # conexiones API futuras del agente


class GeneratePromptRequest(BaseModel):
    objective: str                 # qué datos debe producir el agente externo
    profile: Optional[str] = None
    sheet: Optional[str] = None    # hoja destino (default: storage.sheet o "Datos")


class ImportRequest(BaseModel):
    content: str                   # respuesta del agente externo (contiene <brain-import>)
    profile: Optional[str] = None


class ProfileRuntime:
    """Un perfil cargado: Brain + metadatos + storage."""

    def __init__(self, name: str, yaml_path: Path, data_dir: Path):
        self.name = name
        self.yaml_path = yaml_path
        import yaml as _yaml
        with open(yaml_path, encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}
        self.description = raw.pop("description", "")
        self.creator = bool(raw.pop("creator", False))  # perfil meta: crea sub-agentes
        self.active = True                              # toggle activo/inactivo
        self.storage = _substitute_env_vars(raw.pop("storage", {}) or {})
        # Si la env var no existe, queda el placeholder ${...} → tratar como no configurado
        if "${" in str(self.storage.get("gas_url", "")):
            self.storage["gas_url"] = ""
        # El resto del YAML es un BrainConfig estándar
        self.brain = Brain(load_config_from_yaml(str(yaml_path)))
        self.docs_dir = data_dir / "uploads" / name
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = data_dir / f"registry_{name}.json"

    # ── Registro local de documentos ─────────────────────────────
    def _load_registry(self) -> List[Dict]:
        if self.registry_path.exists():
            try:
                return json.loads(self.registry_path.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_registry(self, reg: List[Dict]):
        self.registry_path.write_text(
            json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def register_document(self, filename: str, content: str) -> Dict:
        content = content[:MAX_DOC_CHARS]
        safe_name = f"{int(time.time())}_{Path(filename).name}"
        (self.docs_dir / safe_name).write_text(content, encoding="utf-8")
        entry = {
            "name": Path(filename).name,
            "stored_as": safe_name,
            "chars": len(content),
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sheet": False,
        }
        reg = self._load_registry()
        reg.append(entry)
        self._save_registry(reg)
        return entry

    def mark_sheet_ok(self, stored_as: str):
        reg = self._load_registry()
        for e in reg:
            if e.get("stored_as") == stored_as:
                e["sheet"] = True
        self._save_registry(reg)

    def documents(self) -> List[Dict]:
        return self._load_registry()

    def docs_context(self) -> str:
        """Concatenar documentos recientes dentro del presupuesto de contexto."""
        parts, used = [], 0
        for entry in reversed(self._load_registry()):
            path = self.docs_dir / entry["stored_as"]
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            remaining = CONTEXT_BUDGET_CHARS - used
            if remaining <= 200:
                break
            chunk = text[:remaining]
            parts.append(f"── Documento: {entry['name']} ({entry['ts']}) ──\n{chunk}")
            used += len(chunk)
        return "\n\n".join(reversed(parts))


def create_app(profiles_dir: str = "profiles", data_dir: str = "data") -> FastAPI:
    profiles_path = Path(profiles_dir)
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    profiles: Dict[str, ProfileRuntime] = {}
    if profiles_path.exists():
        for f in sorted(profiles_path.glob("*.yaml")) + sorted(profiles_path.glob("*.yml")):
            try:
                profiles[f.stem] = ProfileRuntime(f.stem, f, data_path)
            except Exception as e:
                print(f"[server] perfil '{f.stem}' inválido, omitido: {e}")

    if not profiles:
        raise RuntimeError(
            f"No hay perfiles válidos en '{profiles_dir}'. "
            "Crea al menos un YAML (formato BrainConfig + description/storage)."
        )

    state = {"active": next(iter(profiles))}

    # Toggles activo/inactivo persistidos entre reinicios
    state_file = data_path / "agents_state.json"
    if state_file.exists():
        try:
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            for pname, on in saved.get("active", {}).items():
                if pname in profiles:
                    profiles[pname].active = bool(on)
        except Exception:
            pass

    def save_state():
        state_file.write_text(
            json.dumps({"active": {n: p.active for n, p in profiles.items()}},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )

    # Metadatos por perfil: links (contextos compartidos) y connectors (APIs futuras)
    meta_file = data_path / "profiles_meta.json"
    meta: Dict[str, Dict] = {}
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    def save_meta():
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    def profile_meta(name: str) -> Dict:
        return meta.setdefault(name, {"links": [], "connectors": []})

    def merged_docs_context(p: "ProfileRuntime") -> str:
        """Contexto del perfil + contextos compartidos (perfiles linkeados)."""
        parts = []
        own = p.docs_context()
        if own:
            parts.append(own)
        for linked_name in profile_meta(p.name).get("links", []):
            lp = profiles.get(linked_name)
            if lp is None:
                continue
            ctx = lp.docs_context()
            if ctx:
                parts.append(f"── CONTEXTO COMPARTIDO (desde '{linked_name}') ──\n{ctx}")
        return "\n\n".join(parts)

    app = FastAPI(title="Brain Server", version="1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_profile(name: Optional[str]) -> ProfileRuntime:
        pname = name or state["active"]
        if pname not in profiles:
            raise HTTPException(404, f"Perfil desconocido: {pname}")
        return profiles[pname]

    # UI embebida: si existe ui/brain-chat.html (o BRAIN_UI apunta a un HTML), se sirve en /
    from fastapi.responses import FileResponse, HTMLResponse

    ui_candidates = [
        Path(os.getenv("BRAIN_UI", "")),
        Path("ui/brain-chat.html"),
        Path(__file__).parent.parent / "ui" / "brain-chat.html",
    ]
    ui_file = next((p for p in ui_candidates if p and str(p) != "." and p.is_file()), None)

    @app.get("/", include_in_schema=False)
    async def ui_root():
        if ui_file:
            # no-store: el navegador siempre pide la UI fresca (evita ver versiones viejas)
            return FileResponse(ui_file, media_type="text/html",
                                headers={"Cache-Control": "no-store, must-revalidate"})
        return HTMLResponse(
            "<h1>Brain Server</h1><p>API en /api/*. UI no encontrada "
            "(coloca ui/brain-chat.html o define BRAIN_UI).</p>"
        )

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "service": "Brain Server", "profiles": len(profiles)}

    @app.get("/api/profiles")
    async def list_profiles():
        return {
            "active": state["active"],
            "profiles": [
                {
                    "name": p.name,
                    "tag": p.name,  # el tag de invocación externa ES el nombre del perfil
                    "app_name": p.brain.app_name,
                    "description": p.description,
                    "providers": [pr.name for pr in p.brain.providers],
                    "documents": len(p.documents()),
                    "sheets": bool(p.storage.get("gas_url")),
                    "active": p.active,
                    "creator": p.creator,
                    "links": profile_meta(p.name).get("links", []),
                    "connectors": len(profile_meta(p.name).get("connectors", [])),
                }
                for p in profiles.values()
            ],
        }

    @app.post("/api/profile/activate")
    async def activate(body: ActivateRequest):
        if body.name not in profiles:
            raise HTTPException(404, f"Perfil desconocido: {body.name}")
        state["active"] = body.name
        return {"active": state["active"]}

    @app.post("/api/profile/toggle")
    async def toggle(body: ActivateRequest):
        """Activar/desactivar un sub-agente (los inactivos rechazan peticiones)."""
        if body.name not in profiles:
            raise HTTPException(404, f"Perfil desconocido: {body.name}")
        p = profiles[body.name]
        if p.creator and p.active:
            raise HTTPException(400, "El perfil creador no se puede desactivar")
        p.active = not p.active
        save_state()
        return {"name": p.name, "active": p.active}

    @app.post("/api/profile/delete")
    async def delete_profile(body: ActivateRequest):
        """Eliminar un agente: se quita del sistema y su YAML se archiva en
        profiles/_archived/ (sus documentos y tablas NO se borran, por seguridad)."""
        if body.name not in profiles:
            raise HTTPException(404, f"Perfil desconocido: {body.name}")
        p = profiles[body.name]
        if p.creator:
            raise HTTPException(400, "El perfil creador no se puede eliminar")
        if len(profiles) <= 1:
            raise HTTPException(400, "No se puede eliminar el único perfil")
        # Archivar el YAML (recuperable manualmente moviéndolo de vuelta)
        archived_dir = profiles_path / "_archived"
        archived_dir.mkdir(parents=True, exist_ok=True)
        try:
            target = archived_dir / f"{int(time.time())}_{p.yaml_path.name}"
            p.yaml_path.replace(target)
            archived_as = str(target)
        except Exception as e:
            archived_as = f"no se pudo archivar el YAML: {e}"
        del profiles[body.name]
        meta.pop(body.name, None)
        # Quitar links rotos que apuntaban al eliminado
        for m in meta.values():
            if body.name in m.get("links", []):
                m["links"].remove(body.name)
        if state["active"] == body.name:
            state["active"] = next(iter(profiles))
        save_state()
        save_meta()
        # Marca de auditoría en el índice del Sheet
        any_gas = next((pp for pp in profiles.values() if pp.storage.get("gas_url")), None)
        if any_gas:
            await push_rows_to_sheets(any_gas, "Agentes",
                ["Fecha", "Tag", "Nombre", "Descripción", "Estado"],
                [[time.strftime("%Y-%m-%d %H:%M:%S"), body.name, "", "", "ELIMINADO"]])
        return {"deleted": body.name, "archived_yaml": archived_as,
                "data_kept": True, "active": state["active"]}

    @app.get("/api/profile/info")
    async def profile_info(name: str):
        """Detalle editable de un perfil: descripción, prompt, links y connectors."""
        if name not in profiles:
            raise HTTPException(404, f"Perfil desconocido: {name}")
        p = profiles[name]
        prompt = p.brain.prompt_loader.get("chat") if p.brain.prompt_loader else ""
        m = profile_meta(name)
        return {
            "name": p.name,
            "description": p.description,
            "prompt": prompt,
            "links": m.get("links", []),
            "connectors": m.get("connectors", []),
            "available_links": [n for n in profiles if n != name and not profiles[n].creator],
            "creator": p.creator,
        }

    @app.post("/api/profile/update")
    async def profile_update(body: UpdateProfileRequest):
        """Editar un agente: descripción y/o prompt (persisten en su YAML),
        links de contexto compartido y connectors (persisten en profiles_meta.json)."""
        if body.name not in profiles:
            raise HTTPException(404, f"Perfil desconocido: {body.name}")
        p = profiles[body.name]
        changed_yaml = False

        if body.description is not None or body.prompt is not None:
            import yaml as _yaml
            with open(p.yaml_path, encoding="utf-8") as f:
                raw = _yaml.safe_load(f) or {}
            if body.description is not None:
                raw["description"] = body.description
                changed_yaml = True
            if body.prompt is not None:
                raw.setdefault("prompts", {"type": "dict", "config": {"prompts": {}}})
                raw["prompts"].setdefault("config", {}).setdefault("prompts", {})["chat"] = body.prompt
                raw["prompts"]["type"] = "dict"
                changed_yaml = True
            if changed_yaml:
                p.yaml_path.write_text(
                    _yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
                was_active = p.active
                profiles[body.name] = ProfileRuntime(body.name, p.yaml_path, data_path)
                profiles[body.name].active = was_active
                p = profiles[body.name]

        m = profile_meta(body.name)
        if body.links is not None:
            valid = [l for l in body.links if l in profiles and l != body.name]
            m["links"] = valid
        if body.connectors is not None:
            m["connectors"] = body.connectors
        save_meta()

        # Auditoría en la ficha del Sheet
        if changed_yaml and p.storage.get("gas_url"):
            rows = [["Actualizado", time.strftime("%Y-%m-%d %H:%M:%S")]]
            if body.description is not None:
                rows.append(["Descripción (nueva)", body.description])
            if body.prompt is not None:
                rows.append(["Prompt / Directrices (nuevo)", body.prompt])
            await push_rows_to_sheets(p, f"AGENTE {p.name}", ["Campo", "Valor"], rows)

        return {
            "name": p.name, "description": p.description,
            "links": m["links"], "connectors": m["connectors"],
            "yaml_updated": changed_yaml,
        }

    @app.get("/api/document")
    async def document_content(profile: str, stored_as: str):
        """Contenido de un documento subido (para el visor de la UI)."""
        p = get_profile(profile)
        if "/" in stored_as or "\\" in stored_as or ".." in stored_as:
            raise HTTPException(400, "stored_as inválido")
        path = p.docs_dir / stored_as
        if not path.is_file():
            raise HTTPException(404, "Documento no encontrado")
        return {"stored_as": stored_as,
                "content": path.read_text(encoding="utf-8", errors="replace")[:MAX_DOC_CHARS]}

    @app.get("/api/status")
    async def status():
        p = profiles[state["active"]]
        return {"active_profile": state["active"], **p.brain.status()}

    @app.get("/api/documents")
    async def documents(profile: Optional[str] = None):
        p = get_profile(profile)
        return {"profile": p.name, "documents": p.documents()}

    @app.post("/api/chat")
    async def chat(body: ChatRequest):
        p = get_profile(body.profile)
        if not p.active:
            raise HTTPException(409, f"El agente '{p.name}' está desactivado (usa /api/profile/toggle)")

        # Prompt de sistema: etapa "chat" del perfil (o genérico)
        system = ""
        if p.brain.prompt_loader:
            system = p.brain.prompt_loader.get("chat")
        if not system:
            system = (
                f"Eres el asistente '{p.brain.app_name}'. Responde en el idioma del usuario, "
                "de forma clara y accionable, apoyándote en los documentos del contexto cuando existan."
            )

        docs = merged_docs_context(p)
        messages = [{"role": "system", "content": system}]
        if docs:
            messages.append({
                "role": "system",
                "content": f"BASE DE CONOCIMIENTO (documentos subidos por el usuario):\n\n{docs}",
            })
        connectors = profile_meta(p.name).get("connectors", [])
        if connectors:
            conn_desc = ", ".join(f"{c.get('name', '?')} ({c.get('type', 'api')})" for c in connectors)
            messages.append({
                "role": "system",
                "content": f"CONECTORES CONFIGURADOS (aún no ejecutables en tiempo real; si el "
                           f"usuario pide datos que dependen de ellos, indica que la conexión está "
                           f"configurada pero pendiente de activación): {conn_desc}",
            })
        for h in body.history[-8:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": body.message})

        trace = None
        try:
            if body.refine and len(p.brain.providers) > 1:
                reply, trace = await p.brain.complete_refined(
                    messages, max_tokens=body.max_tokens, temperature=body.temperature
                )
            else:
                reply = await p.brain.complete(
                    messages, max_tokens=body.max_tokens, temperature=body.temperature
                )
        except Exception as e:
            raise HTTPException(502, f"Todos los proveedores fallaron: {str(e)[:200]}")

        st = p.brain.status()
        result = {"reply": reply, "provider": st["active"], "profile": p.name}
        if trace:
            result["trace"] = trace

        # Perfil creador: si la respuesta confirma un agente (<brain-agent>), materializarlo
        if p.creator:
            try:
                spec = parse_brain_agent(reply)
            except ValueError as e:
                spec = None
                result["agent_error"] = str(e)
            if spec:
                created = await materialize_agent(p, spec)
                result["agent_created"] = created
                result["reply"] = (
                    f"✅ Agente creado y desplegado.\n\n"
                    f"• Tag/ID: {created['tag']}\n"
                    f"• Nombre: {created['name']}\n"
                    f"• Ficha en Sheets: {'pestaña AGENTE ' + created['tag'] + ' ✓' if created['sheets'] == 'ok' else created['sheets']}\n"
                    f"• Hoja de datos propia: DB {created['tag']}\n\n"
                    f"Ya aparece en la barra lateral: seleccionalo para probarlo, "
                    f"o invocalo desde cualquier UI externa con profile='{created['tag']}'."
                )
        return result

    async def push_rows_to_sheets(p: ProfileRuntime, sheet: str, headers: List[str], rows: List[List[str]]) -> str:
        """Registrar filas estructuradas en Google Sheets vía GAS (action=appendRows)."""
        gas_url = p.storage.get("gas_url", "")
        if not gas_url:
            return "no_configurado"
        try:
            async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
                r = await client.post(gas_url, data={
                    "action": "appendRows",
                    "sheet": sheet,
                    "profile": p.name,
                    "headers": json.dumps(headers, ensure_ascii=False),
                    "rows": json.dumps(rows, ensure_ascii=False),
                })
                r.raise_for_status()
            return "ok"
        except Exception as e:
            return f"error: {str(e)[:120]}"

    async def materialize_agent(creator: ProfileRuntime, spec: Dict) -> Dict:
        """Crear un sub-agente real: YAML + perfil vivo + pestaña legible en Sheets."""
        import yaml as _yaml
        tag = slugify(spec["nombre"])
        if tag in profiles:
            tag = f"{tag}_{int(time.time()) % 10000}"
        yaml_path = profiles_path / f"{tag}.yaml"
        cfg = {
            "description": spec["descripcion"] or spec["nombre"],
            "app_name": f"brain_{tag}",
            "providers": [
                {"name": "groq", "api_key": "${GROQ_API_KEY}",
                 "model": "llama-3.3-70b-versatile"},
                {"name": "cerebras", "api_key": "${CEREBRAS_API_KEY}",
                 "extra_body": {"reasoning_effort": "high"}},
                {"name": "openrouter", "api_key": "${OPENROUTER_API_KEY}",
                 "model": "nvidia/nemotron-3-ultra-550b-a55b:free"},
                {"name": "hf", "api_key": "${HF_TOKEN}"},
            ],
            "prompts": {"type": "dict", "config": {"prompts": {"chat": spec["prompt"]}}},
            "storage": {"gas_url": "${BRAIN_GAS_URL}", "sheet": f"DB {tag}"},
            "timeout_seconds": 30,
        }
        yaml_path.write_text(
            _yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        profiles[tag] = ProfileRuntime(tag, yaml_path, data_path)
        save_state()
        # Ficha humano-legible del agente en su propia pestaña del Sheet
        sheets_status = await push_rows_to_sheets(
            creator, f"AGENTE {tag}", ["Campo", "Valor"],
            [
                ["Tag/ID", tag],
                ["Nombre", spec["nombre"]],
                ["Descripción", spec["descripcion"]],
                ["Creado", time.strftime("%Y-%m-%d %H:%M:%S")],
                ["Hoja de datos", f"DB {tag}"],
                ["Invocación", f"POST /api/chat con profile='{tag}'"],
                ["Prompt / Directrices", spec["prompt"]],
            ],
        )
        # Índice de agentes (una fila por alta)
        await push_rows_to_sheets(
            creator, "Agentes", ["Fecha", "Tag", "Nombre", "Descripción", "Estado"],
            [[time.strftime("%Y-%m-%d %H:%M:%S"), tag, spec["nombre"],
              spec["descripcion"], "ACTIVO"]],
        )
        return {"tag": tag, "name": spec["nombre"], "sheets": sheets_status}

    async def do_import(p: ProfileRuntime, data: Dict) -> Dict:
        """Persistir un brain-import: tabla local + doc de contexto + Sheets."""
        sheet = data["sheet"] or p.storage.get("sheet", "Datos")
        headers, rows = data["headers"], data["rows"]

        # 1) Tabla estructurada local
        tables_dir = p.docs_dir.parent.parent / "tables" / p.name
        tables_dir.mkdir(parents=True, exist_ok=True)
        table_path = tables_dir / f"{sheet}.json"
        existing = {"headers": headers, "rows": []}
        if table_path.exists():
            try:
                existing = json.loads(table_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        if existing.get("headers") == headers:
            existing["rows"].extend(rows)
        else:
            existing = {"headers": headers, "rows": rows}
        table_path.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")

        # 2) Como documento CSV → entra al contexto del chat (brain lo interpreta)
        csv_lines = [";".join(headers)] + [";".join(str(c) for c in r) for r in rows]
        entry = p.register_document(f"[tabla] {sheet}.csv", "\n".join(csv_lines))

        # 3) Google Sheets (filas estructuradas)
        sheets_status = await push_rows_to_sheets(p, sheet, headers, rows)
        if sheets_status == "ok":
            p.mark_sheet_ok(entry["stored_as"])

        return {
            "sheet": sheet,
            "headers": headers,
            "rows_imported": len(rows),
            "rows_total": len(existing["rows"]),
            "sheets": sheets_status,
            "registered": entry,
        }

    @app.post("/api/prompt/generate")
    async def generate_prompt(body: GeneratePromptRequest):
        """Generar un prompt autocontenido para ejecutar en un agente externo.
        La respuesta del agente vendrá en formato <brain-import> lista para /api/import."""
        p = get_profile(body.profile)
        sheet = body.sheet or p.storage.get("sheet", "Datos")

        # El LLM propone el schema de campos según el objetivo
        fields: List[str] = []
        try:
            raw = await p.brain.complete([
                {"role": "system", "content":
                    "Diseñas schemas tabulares. Dado un objetivo de recolección de datos, responde SOLO "
                    "un JSON: {\"fields\": [\"campo1\", ...]} con 3 a 8 nombres de columna en snake_case, "
                    "en el idioma del objetivo, ordenados lógicamente."},
                {"role": "user", "content": body.objective},
            ], max_tokens=200, temperature=0.0)
            from .core import extract_json
            parsed = extract_json(raw) or {}
            fields = [str(f) for f in parsed.get("fields", []) if str(f).strip()][:8]
        except Exception as e:
            print(f"[prompt/generate] schema LLM falló, uso genérico: {e}")
        if not fields:
            fields = ["nombre", "descripcion", "valor"]

        schema_fields = "\n".join(f'    <field name="{f}"/>' for f in fields)
        example_row = "\n".join(f"    <{f}>…</{f}>" for f in fields)
        format_spec = IMPORT_FORMAT_SPEC.format(
            profile=p.name, sheet=sheet,
            schema_fields=schema_fields, example_row=example_row,
        )

        prompt = (
            f"# TAREA PARA AGENTE EXTERNO\n\n"
            f"## Objetivo\n{body.objective.strip()}\n\n"
            f"## Instrucciones\n"
            f"1. Investiga/recopila los datos necesarios para cumplir el objetivo.\n"
            f"2. Sé exhaustivo pero preciso: solo datos verificables, no inventes.\n"
            f"3. Devuelve TODOS los registros encontrados.\n\n"
            f"## {format_spec}\n"
        )
        return {"prompt": prompt, "profile": p.name, "sheet": sheet, "fields": fields}

    @app.post("/api/import")
    async def import_data(body: ImportRequest):
        """Importar la respuesta de un agente externo (bloque <brain-import>)."""
        p = get_profile(body.profile)
        try:
            data = parse_brain_import(body.content)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if data is None:
            raise HTTPException(400, "No se encontró un bloque <brain-import> en el contenido")
        result = await do_import(p, data)
        return {"profile": p.name, **result}

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...), profile: Optional[str] = Form(None)):
        p = get_profile(profile)
        fname = (file.filename or "").lower()
        if not (fname.endswith(".txt") or fname.endswith(".xml")):
            raise HTTPException(400, "Solo se aceptan archivos .txt o .xml")
        raw = await file.read()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("latin-1", errors="replace")

        # Si el archivo contiene un brain-import → importación estructurada
        try:
            data = parse_brain_import(content)
        except ValueError as e:
            raise HTTPException(400, f"El archivo contiene un brain-import inválido: {e}")
        if data is not None:
            result = await do_import(p, data)
            return {"profile": p.name, "imported": True, **result}

        entry = p.register_document(file.filename, content)

        # Registro en Google Sheets vía GAS (si el perfil lo configura)
        sheet_result = "no_configurado"
        gas_url = p.storage.get("gas_url", "")
        if gas_url:
            try:
                async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                    r = await client.post(gas_url, data={
                        "action": "registerDocument",
                        "sheet": p.storage.get("sheet", "Documentos"),
                        "profile": p.name,
                        "name": entry["name"],
                        "chars": str(entry["chars"]),
                        "ts": entry["ts"],
                        "content": content[:45_000],  # límite práctico de celda en Sheets
                    })
                    r.raise_for_status()
                    p.mark_sheet_ok(entry["stored_as"])
                    entry["sheet"] = True
                    sheet_result = "ok"
            except Exception as e:
                sheet_result = f"error: {str(e)[:120]}"

        return {"registered": entry, "sheets": sheet_result, "profile": p.name}

    return app


def main():
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Brain Server — chat unificado multi-LLM")
    parser.add_argument("--profiles", default="profiles", help="Directorio de perfiles YAML")
    parser.add_argument("--data", default="data", help="Directorio de datos (uploads/registros)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")))
    args = parser.parse_args()

    app = create_app(args.profiles, args.data)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
