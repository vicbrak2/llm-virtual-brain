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
import time
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import load_config_from_yaml
from .core import Brain

MAX_DOC_CHARS = 60_000          # límite por documento subido
CONTEXT_BUDGET_CHARS = 12_000   # presupuesto de contexto de documentos por chat


class ChatRequest(BaseModel):
    message: str
    history: List[Dict] = []
    profile: Optional[str] = None
    max_tokens: int = 700
    temperature: float = 0.3


class ActivateRequest(BaseModel):
    name: str


class ProfileRuntime:
    """Un perfil cargado: Brain + metadatos + storage."""

    def __init__(self, name: str, yaml_path: Path, data_dir: Path):
        self.name = name
        self.yaml_path = yaml_path
        import yaml as _yaml
        with open(yaml_path, encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}
        self.description = raw.pop("description", "")
        self.storage = raw.pop("storage", {}) or {}
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
            return FileResponse(ui_file, media_type="text/html")
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
                    "app_name": p.brain.app_name,
                    "description": p.description,
                    "providers": [pr.name for pr in p.brain.providers],
                    "documents": len(p.documents()),
                    "sheets": bool(p.storage.get("gas_url")),
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

        # Prompt de sistema: etapa "chat" del perfil (o genérico)
        system = ""
        if p.brain.prompt_loader:
            system = p.brain.prompt_loader.get("chat")
        if not system:
            system = (
                f"Eres el asistente '{p.brain.app_name}'. Responde en el idioma del usuario, "
                "de forma clara y accionable, apoyándote en los documentos del contexto cuando existan."
            )

        docs = p.docs_context()
        messages = [{"role": "system", "content": system}]
        if docs:
            messages.append({
                "role": "system",
                "content": f"BASE DE CONOCIMIENTO (documentos subidos por el usuario):\n\n{docs}",
            })
        for h in body.history[-8:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": body.message})

        try:
            reply = await p.brain.complete(
                messages, max_tokens=body.max_tokens, temperature=body.temperature
            )
        except Exception as e:
            raise HTTPException(502, f"Todos los proveedores fallaron: {str(e)[:200]}")

        st = p.brain.status()
        return {"reply": reply, "provider": st["active"], "profile": p.name}

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...), profile: Optional[str] = Form(None)):
        p = get_profile(profile)
        if not (file.filename or "").lower().endswith(".txt"):
            raise HTTPException(400, "Solo se aceptan archivos .txt")
        raw = await file.read()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("latin-1", errors="replace")

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
