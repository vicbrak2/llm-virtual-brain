"""Conducir el flujo del creador para el agente interno de Qamiluna Studio,
hasta la fase de confirmación (el OK lo da Vic)."""
import json
import urllib.request

U = "http://localhost:8901"
history = []

def turn(msg):
    req = urllib.request.Request(
        f"{U}/api/chat",
        data=json.dumps({"message": msg, "history": history,
                         "profile": "creador", "max_tokens": 1200}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=150) as r:
        d = json.loads(r.read().decode("utf-8"))
    history.append({"role": "user", "content": msg})
    history.append({"role": "assistant", "content": d["reply"]})
    return d

idea = ("Quiero un agente de chat interno para el equipo de Qamiluna Studio (estudio de maquillaje "
        "y estilismo). Las usuarias son las integrantes del equipo: maquilladoras (MUA), estilistas "
        "y contables. Debe responder dudas operativas sobre: precios de servicios, traslados, "
        "publicidades/promociones vigentes, agendamientos, y detalles de las planillas Sheet del "
        "team. Su conocimiento sale de los documentos que le subamos (listas de precios, políticas, "
        "resúmenes de planillas). Si un dato no está en los documentos, debe decirlo y NO inventar "
        "(especialmente precios). Tono: cercano y profesional, en español, tuteo.")

answers = [
    "Qamiluna Team",
    "que no invente precios ni fechas; que no comparta datos con clientes finales (es solo interno); "
    "si preguntan algo contable sensible que derive a la contable del equipo; nada de datos personales de clientas",
    "español rioplatense, tuteo, respuestas cortas y accionables",
    "sí, exacto",
]

d = turn(idea)
print(f"[creador] {d['reply']}\n{'─'*60}")
for a in answers:
    if "Confirmas la creaci" in d["reply"] or "Responde OK" in d["reply"]:
        break
    d = turn(a)
    print(f"[vic-proxy] {a[:70]}...\n[creador] {d['reply']}\n{'─'*60}")

print("\n=== ESTADO FINAL (esperando OK de Vic) ===")
# Guardar historia para retomar con el OK
with open("tests/qamiluna_history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False)
