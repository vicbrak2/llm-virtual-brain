"""OK de Vic → despliegue del agente Qamiluna Team."""
import json
import urllib.request

U = "http://localhost:8901"
with open("tests/qamiluna_history.json", encoding="utf-8") as f:
    history = json.load(f)

req = urllib.request.Request(
    f"{U}/api/chat",
    data=json.dumps({"message": "OK", "history": history,
                     "profile": "creador", "max_tokens": 1600}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=180) as r:
    d = json.loads(r.read().decode("utf-8"))

print(d["reply"])
print()
if "agent_created" in d:
    print("CREATED_TAG=" + d["agent_created"]["tag"])
    print("SHEETS=" + d["agent_created"]["sheets"])
else:
    print("SIN agent_created — respuesta cruda arriba")
