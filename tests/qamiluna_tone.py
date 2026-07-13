"""Ajuste de tono: chileno y cercano, sin modismos."""
import json
import urllib.request

U = "http://localhost:8901"
with open("tests/qamiluna_history.json", encoding="utf-8") as f:
    history = json.load(f)

msg = ("Cambio en el tono: debe ser español de Chile, cercano y profesional, PERO sin modismos "
       "ni jerga chilena (neutro-chileno: tuteo natural, nada de 'po', 'cachai', 'al tiro', etc.). "
       "Muestra el resumen final actualizado.")

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
