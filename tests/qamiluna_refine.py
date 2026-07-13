"""Refinar el resumen agregando reglas faltantes antes del OK de Vic."""
import json
import urllib.request

U = "http://localhost:8901"
with open("tests/qamiluna_history.json", encoding="utf-8") as f:
    history = json.load(f)

msg = ("Antes de confirmar, agrega estas reglas al agente: (1) es SOLO para uso interno del "
       "equipo, nunca debe redactar mensajes para clientas finales ni compartir info fuera del "
       "team; (2) si preguntan algo contable sensible (sueldos, ganancias, deudas) debe derivar "
       "a la contable del equipo; (3) no maneja datos personales de clientas; (4) respuestas "
       "cortas y accionables, español rioplatense con tuteo. Muestra el resumen actualizado.")

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
with open("tests/qamiluna_history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False)
print(d["reply"])
