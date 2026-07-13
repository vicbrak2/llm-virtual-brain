"""Test e2e del perfil creador: idea → refinamiento → confirmación → OK → agente desplegado."""
import json
import sys
import urllib.request

U = "http://localhost:8901"

def chat(message, history):
    req = urllib.request.Request(
        f"{U}/api/chat",
        data=json.dumps({
            "message": message, "history": history,
            "profile": "creador", "max_tokens": 1200,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=150) as r:
        return json.loads(r.read().decode("utf-8"))

history = []
def turn(msg):
    d = chat(msg, history)
    history.append({"role": "user", "content": msg})
    history.append({"role": "assistant", "content": d["reply"]})
    return d

# Turno 1: idea inicial
d = turn("quiero un agente que responda dudas sobre cuidado de plantas de interior, "
         "tono amable para principiantes, que use las fichas de plantas que yo le suba "
         "y que nunca invente datos de riego; si no sabe, que lo diga")
print("T1:", d["reply"][:300], "\n---")

# Hasta 4 turnos de refinamiento respondiendo genérico, luego OK
answers = ["Plantitas", "solo plantas de interior comunes; nada de diagnóstico de plagas graves, "
           "en ese caso que recomiende un vivero", "español, público principiante adulto", "sí"]
created = None
for a in answers:
    if "agent_created" in d:
        break
    if "¿Confirmas la creación?" in d["reply"] or "Responde OK" in d["reply"]:
        d = turn("OK")
        print("T-OK:", d["reply"][:400], "\n---")
        created = d.get("agent_created")
        break
    d = turn(a)
    print("T:", d["reply"][:300], "\n---")

if not created and "agent_created" not in d:
    # último intento: confirmar
    if "¿Confirmas" in d["reply"] or "OK" in d["reply"]:
        d = turn("OK")
        print("T-OK2:", d["reply"][:400], "\n---")
        created = d.get("agent_created")

created = created or d.get("agent_created")
if not created:
    print("NO SE CREÓ EL AGENTE. Última respuesta completa:")
    print(d["reply"])
    sys.exit(1)

print(f"AGENTE CREADO: tag={created['tag']} sheets={created['sheets']}")

# Probar el agente recién creado
req = urllib.request.Request(
    f"{U}/api/chat",
    data=json.dumps({"message": "hola! se me ponen amarillas las hojas del potus, que hago?",
                     "history": [], "profile": created["tag"]}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=150) as r:
    test = json.loads(r.read().decode("utf-8"))
print(f"\nTEST DEL AGENTE ({created['tag']}) via {test['provider']}:")
print(test["reply"][:400])
