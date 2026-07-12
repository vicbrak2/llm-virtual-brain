"""Test en vivo (requiere .env con keys reales). No corre en CI.

Uso: uv run --with httpx --with pydantic --with pyyaml python tests/test_live.py <ruta_env>
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from brain import Brain, provider_from_dict


def load_env(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


async def main():
    env_path = sys.argv[1] if len(sys.argv) > 1 else ".env"
    load_env(env_path)

    defs = [
        {"name": "cerebras", "key": os.getenv("CEREBRAS_API_KEY", "")},
        {"name": "groq", "key": os.getenv("GROQ_API_KEY", "")},
        {"name": "openrouter", "key": os.getenv("OPENROUTER_API_KEY", ""),
         "headers": {"HTTP-Referer": "https://jarvis.local", "X-Title": "Jarvis FOCUS OS"}},
        {"name": "hf", "key": os.getenv("HF_TOKEN", "")},
    ]
    providers = [provider_from_dict(d) for d in defs if d["key"]]
    print(f"providers configurados: {[p.name for p in providers]}")

    # 1) Llamada normal (debe responder el primero)
    brain = Brain(providers=providers, app_name="live_test")
    out = await brain.complete(
        [{"role": "user", "content": "Responde solo con la palabra: OK"}],
        max_tokens=200, temperature=0.0,
    )
    print(f"[1] normal → {brain.status()['active']}: {out.strip()[:60]!r}")

    # 2) Rotación forzada: primer provider con key rota → debe rotar al siguiente
    bad_first = [provider_from_dict({"name": "cerebras", "key": "csk-invalida"})] + providers[1:]
    brain2 = Brain(providers=bad_first, app_name="live_test_rot")
    out2 = await brain2.complete(
        [{"role": "user", "content": "Responde solo con la palabra: ROTADO"}],
        max_tokens=200, temperature=0.0,
    )
    st = brain2.status()
    assert st["active"] != "cerebras", "debió rotar fuera de cerebras"
    print(f"[2] rotación → {st['active']}: {out2.strip()[:60]!r}")

    print("LIVE OK")


asyncio.run(main())
