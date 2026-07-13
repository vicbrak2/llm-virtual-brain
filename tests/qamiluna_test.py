"""Testear el agente qamiluna_team con preguntas reales del equipo."""
import json
import urllib.request

U = "http://localhost:8901"

def ask(msg):
    req = urllib.request.Request(
        f"{U}/api/chat",
        data=json.dumps({"message": msg, "history": [],
                         "profile": "qamiluna_team", "max_tokens": 500}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=150) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d

tests = [
    ("MUA pregunta precio", "hola! cuanto sale el pack novia completo y que incluye?"),
    ("Estilista pregunta traslado", "tengo un evento en Rancagua el mes que viene, como funciona el traslado?"),
    ("TRAMPA precio inexistente", "cuanto cobramos por el servicio de unas esculpidas?"),
    ("Contable sensible → derivar", "cuanto ganó cada integrante el mes pasado?"),
    ("Agendamiento", "me confirmaron una novia para octubre, que tengo que hacer?"),
]

for label, q in tests:
    d = ask(q)
    print(f"■ {label}")
    print(f"  Q: {q}")
    print(f"  A ({d['provider']}): {d['reply'][:350]}")
    print()
