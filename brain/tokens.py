"""
Almacén y refresco automático de tokens de conectores Meta.

`data/tokens.json` guarda los tokens renovados (sobreviven reinicios porque
data/ es volumen). `get_token(ENV)` devuelve el token vigente: primero el del
store, si no el del `.env`. Un loop diario renueva los que estén por vencer:

  - INSTAGRAM_ACCESS_TOKEN  → GET graph.instagram.com/refresh_access_token
                              (grant ig_refresh_token; requiere token >24h)
  - THREADS_ACCESS_TOKEN    → GET graph.threads.net/refresh_access_token
                              (grant th_refresh_token)
  - META_ADS_ACCESS_TOKEN   → GET graph.facebook.com/oauth/access_token
                              (grant fb_exchange_token; requiere META_APP_ID
                              y META_APP_SECRET en .env)

Los tokens de Instagram/Threads duran 60 días y son renovables sin usuario.
El de Meta (Facebook Login) se re-emite como long-lived de ~60 días.
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import httpx

STORE_PATH = Path(os.getenv("BRAIN_DATA", "data")) / "tokens.json"
REFRESH_BELOW_DAYS = 45          # renovar cuando queden menos de estos días
MIN_AGE_HOURS = 24               # IG exige que el token tenga >24h para renovarse
CHECK_EVERY_SECONDS = 24 * 3600  # una pasada por día


def _load_store() -> Dict:
    if STORE_PATH.exists():
        try:
            return json.loads(STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_store(store: Dict):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def get_token(env_name: str) -> str:
    """Token vigente: el renovado del store si existe, si no el del .env."""
    entry = _load_store().get(env_name)
    if entry and entry.get("token"):
        return entry["token"]
    return os.getenv(env_name, "").strip()


def token_days_left(env_name: str) -> Optional[int]:
    """Días restantes según el store (None si nunca se renovó por acá)."""
    entry = _load_store().get(env_name)
    if entry and entry.get("expires_at"):
        return max(0, int((entry["expires_at"] - time.time()) / 86400))
    return None


def _record(store: Dict, env_name: str, token: str, expires_in: Optional[int]):
    store[env_name] = {
        "token": token,
        "refreshed_at": time.time(),
        "expires_at": time.time() + expires_in if expires_in else None,
    }


def _needs_refresh(store: Dict, env_name: str) -> bool:
    entry = store.get(env_name)
    if not entry:
        return True  # nunca renovado: intentar (fija expires_at conocido)
    age_h = (time.time() - entry.get("refreshed_at", 0)) / 3600
    if age_h < MIN_AGE_HOURS:
        return False
    exp = entry.get("expires_at")
    if exp is None:
        return True
    return (exp - time.time()) / 86400 < REFRESH_BELOW_DAYS


async def refresh_all() -> List[str]:
    """Una pasada de renovación. Devuelve líneas de log (para stdout/health)."""
    logs: List[str] = []
    store = _load_store()
    changed = False

    async with httpx.AsyncClient(timeout=30) as client:
        # ── Instagram (IG Login) ────────────────────────────────────────
        ig = get_token("INSTAGRAM_ACCESS_TOKEN")
        if ig and _needs_refresh(store, "INSTAGRAM_ACCESS_TOKEN"):
            try:
                r = await client.get(
                    "https://graph.instagram.com/refresh_access_token",
                    params={"grant_type": "ig_refresh_token", "access_token": ig})
                r.raise_for_status()
                d = r.json()
                _record(store, "INSTAGRAM_ACCESS_TOKEN",
                        d["access_token"], d.get("expires_in"))
                changed = True
                logs.append(f"instagram: renovado, vence en {d.get('expires_in', 0)//86400} días")
            except Exception as e:
                logs.append(f"instagram: refresh falló — {str(e)[:120]}")

        # ── Threads ─────────────────────────────────────────────────────
        th = get_token("THREADS_ACCESS_TOKEN")
        if th and _needs_refresh(store, "THREADS_ACCESS_TOKEN"):
            try:
                r = await client.get(
                    "https://graph.threads.net/refresh_access_token",
                    params={"grant_type": "th_refresh_token", "access_token": th})
                r.raise_for_status()
                d = r.json()
                _record(store, "THREADS_ACCESS_TOKEN",
                        d["access_token"], d.get("expires_in"))
                changed = True
                logs.append(f"threads: renovado, vence en {d.get('expires_in', 0)//86400} días")
            except Exception as e:
                logs.append(f"threads: refresh falló — {str(e)[:120]}")

        # ── Meta (Facebook Login: ads/página/whatsapp) ──────────────────
        fb = get_token("META_ADS_ACCESS_TOKEN")
        app_id = os.getenv("META_APP_ID", "").strip()
        app_secret = os.getenv("META_APP_SECRET", "").strip()
        if fb and app_id and app_secret and _needs_refresh(store, "META_ADS_ACCESS_TOKEN"):
            try:
                r = await client.get(
                    "https://graph.facebook.com/v23.0/oauth/access_token",
                    params={"grant_type": "fb_exchange_token",
                            "client_id": app_id, "client_secret": app_secret,
                            "fb_exchange_token": fb})
                r.raise_for_status()
                d = r.json()
                _record(store, "META_ADS_ACCESS_TOKEN",
                        d["access_token"], d.get("expires_in"))
                changed = True
                logs.append(f"meta: renovado (long-lived, ~{(d.get('expires_in') or 5184000)//86400} días)")
            except Exception as e:
                logs.append(f"meta: refresh falló — {str(e)[:120]}")
        elif fb and not (app_id and app_secret):
            logs.append("meta: sin META_APP_ID/META_APP_SECRET — no se puede auto-renovar")

    if changed:
        _save_store(store)
    return logs


async def refresh_loop():
    """Loop en background: una renovación al arrancar y luego una por día."""
    import asyncio
    while True:
        try:
            for line in await refresh_all():
                print(f"[tokens] {line}")
        except Exception as e:
            print(f"[tokens] pasada de refresh falló: {str(e)[:150]}")
        await asyncio.sleep(CHECK_EVERY_SECONDS)
