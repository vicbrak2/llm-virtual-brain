"""
Ejecutores de conectores API para agentes Brain.

Cada conector registrado en profiles_meta.json con un `type` soportado se
ejecuta antes del chat: sus datos entran al contexto del LLM como
"DATOS EN VIVO". Los resultados se cachean para no golpear la API en cada
mensaje.

Soportados:
    instagram — Instagram API con Instagram Login (graph.instagram.com).
        Credenciales vía env: INSTAGRAM_ACCESS_TOKEN.
        Permisos: instagram_business_basic (+ instagram_business_manage_insights
        para alcance, guardados, vistas, demografía y horarios de audiencia —
        si el token no los tiene, esas secciones se omiten sin fallar).
    meta_ads — Meta Marketing API (graph.facebook.com): campañas y resultados.
        Credenciales vía env: META_ADS_ACCESS_TOKEN (Facebook Login, scope
        ads_read) y META_AD_ACCOUNT_ID. Sin credenciales queda como pendiente.
"""

import os
import time
from collections import defaultdict
from typing import Dict, List, Optional

import httpx

IG_GRAPH = "https://graph.instagram.com/v23.0"
CACHE_TTL_SECONDS = 600          # 10 min: métricas sociales no cambian por mensaje
MEDIA_LIMIT = 15                 # publicaciones detalladas en el contexto
HISTORY_LIMIT = 100              # publicaciones para el resumen histórico mensual
INSIGHTS_MEDIA = 8               # publicaciones recientes con insights detallados

_cache: Dict[str, Dict] = {}     # key → {"ts": epoch, "data": str|None}


def _cached(key: str) -> Optional[str]:
    hit = _cache.get(key)
    if hit and (time.time() - hit["ts"]) < CACHE_TTL_SECONDS:
        return hit["data"]
    return None


def _store(key: str, data: Optional[str]):
    _cache[key] = {"ts": time.time(), "data": data}


async def _get(client: httpx.AsyncClient, path: str, **params) -> Dict:
    r = await client.get(f"{IG_GRAPH}/{path}", params=params)
    r.raise_for_status()
    return r.json()


async def _media_insights(client: httpx.AsyncClient, token: str, media_id: str,
                          media_type: str) -> Dict[str, int]:
    """Insights por publicación. Devuelve {} si el permiso no está o la API falla."""
    metrics = "reach,saved,shares,views,total_interactions"
    try:
        data = await _get(client, f"{media_id}/insights",
                          metric=metrics, access_token=token)
        return {d["name"]: (d.get("values") or [{}])[0].get("value", 0)
                for d in data.get("data", [])}
    except Exception:
        return {}


async def _recent_comments(client: httpx.AsyncClient, token: str,
                           media: List[Dict], own_username: str,
                           max_posts: int = 15) -> List[str]:
    """Comentarios recientes en las últimas publicaciones, marcando los que
    aún no tienen respuesta de la cuenta. Requiere instagram_business_manage_comments."""
    lines: List[str] = []
    unanswered = 0
    for m in media[:max_posts]:
        try:
            data = await _get(client, f"{m['id']}/comments",
                              fields="id,text,username,timestamp,"
                                     "replies{username,text}",
                              access_token=token)
        except Exception:
            continue
        caption = (m.get("caption") or "").replace("\n", " ")[:40]
        for c in data.get("data", []):
            if c.get("username") == own_username:
                continue  # comentario propio
            replies = (c.get("replies") or {}).get("data", [])
            answered = any(r.get("username") == own_username for r in replies)
            if not answered:
                unanswered += 1
            estado = "respondido" if answered else "SIN RESPONDER"
            fecha = (c.get("timestamp") or "")[:10]
            texto = (c.get("text") or "").replace("\n", " ")[:100]
            lines.append(f"- [{fecha}] @{c.get('username')} en \"{caption}\": "
                         f"\"{texto}\" ({estado})")
    if lines:
        lines.insert(0, f"Comentarios recientes en las últimas {max_posts} publicaciones "
                        f"({unanswered} sin responder):")
    return lines


async def _active_stories(client: httpx.AsyncClient, token: str) -> List[str]:
    """Historias activas (últimas 24h) con métricas si hay permiso de insights."""
    try:
        data = await _get(client, "me/stories",
                          fields="id,media_type,timestamp", access_token=token)
    except Exception:
        return []
    stories = data.get("data", [])
    if not stories:
        return []
    lines = [f"Historias activas ahora: {len(stories)}"]
    for s in stories[:6]:
        ins = {}
        try:
            d = await _get(client, f"{s['id']}/insights",
                           metric="reach,views,replies", access_token=token)
            ins = {x["name"]: (x.get("values") or [{}])[0].get("value", 0)
                   for x in d.get("data", [])}
        except Exception:
            pass
        extra = ""
        if ins:
            extra = f" — alcance {ins.get('reach', '?')}, {ins.get('views', '?')} vistas, " \
                    f"{ins.get('replies', 0)} respuestas"
        lines.append(f"- [{(s.get('timestamp') or '')[11:16]}] {s.get('media_type', '?')}{extra}")
    return lines


async def _dm_followup(client: httpx.AsyncClient, token: str,
                       own_username: str, max_convs: int = 15) -> List[str]:
    """Estado de seguimiento de los DMs: quién habló último en cada conversación.
    Requiere instagram_business_manage_messages. NOTA: Meta solo expone
    conversaciones con actividad posterior a la conexión de la app; el
    historial anterior no es accesible por API."""
    try:
        data = await _get(client, "me/conversations",
                          platform="instagram",
                          fields="id,updated_time,participants,"
                                 "messages.limit(3){from,created_time,message}",
                          limit=str(max_convs), access_token=token)
    except Exception:
        return []
    convs = data.get("data", [])
    if not convs:
        return []
    pendientes = 0
    lines: List[str] = []
    for conv in convs:
        participants = (conv.get("participants") or {}).get("data", [])
        other = next((p.get("username", p.get("name", "?")) for p in participants
                      if p.get("username") != own_username), "?")
        msgs = (conv.get("messages") or {}).get("data", [])
        if not msgs:
            continue
        last = msgs[0]  # más reciente primero
        last_from = (last.get("from") or {}).get("username", "?")
        fecha = (last.get("created_time") or "")[:10]
        texto = (last.get("message") or "").replace("\n", " ")[:80]
        if last_from == own_username:
            estado = "respondido por el equipo"
        else:
            estado = "ESPERANDO RESPUESTA del equipo"
            pendientes += 1
        lines.append(f"- @{other} [último mensaje {fecha}]: \"{texto}\" ({estado})")
    if lines:
        lines.insert(0, f"Mensajes directos (DMs) — {pendientes} conversaciones "
                        f"esperando respuesta del equipo:")
        lines.append("(Nota: la API solo muestra conversaciones con actividad "
                     "desde que se conectó la integración; DMs antiguos no aparecen.)")
    return lines


async def _account_insights(client: httpx.AsyncClient, token: str, user_id: str) -> List[str]:
    """Alcance de la cuenta, demografía y horarios online de la audiencia.
    Devuelve líneas de texto; vacío si no hay permiso de insights."""
    lines: List[str] = []
    # Alcance últimos 28 días
    try:
        data = await _get(client, f"{user_id}/insights",
                          metric="reach", period="days_28", access_token=token)
        vals = (data.get("data") or [{}])[0].get("values") or []
        if vals:
            lines.append(f"- Alcance últimos 28 días: {vals[-1].get('value', '?')} cuentas únicas")
    except Exception:
        pass
    # Vistas/interacciones agregadas 28 días (total_value)
    try:
        data = await _get(client, f"{user_id}/insights",
                          metric="views,total_interactions,accounts_engaged",
                          period="days_28", metric_type="total_value", access_token=token)
        for d in data.get("data", []):
            v = (d.get("total_value") or {}).get("value")
            if v is not None:
                nombre = {"views": "Vistas totales", "total_interactions": "Interacciones totales",
                          "accounts_engaged": "Cuentas que interactuaron"}.get(d["name"], d["name"])
                lines.append(f"- {nombre} (28 días): {v}")
    except Exception:
        pass
    # Demografía de seguidores
    try:
        data = await _get(client, f"{user_id}/insights",
                          metric="follower_demographics", period="lifetime",
                          metric_type="total_value", breakdown="age", access_token=token)
        results = ((data.get("data") or [{}])[0].get("total_value") or {}) \
            .get("breakdowns", [{}])[0].get("results", [])
        if results:
            top = sorted(results, key=lambda r: -r.get("value", 0))[:3]
            desc = ", ".join(f"{r['dimension_values'][0]}: {r['value']}" for r in top)
            lines.append(f"- Edades principales de seguidores: {desc}")
    except Exception:
        pass
    try:
        data = await _get(client, f"{user_id}/insights",
                          metric="follower_demographics", period="lifetime",
                          metric_type="total_value", breakdown="city", access_token=token)
        results = ((data.get("data") or [{}])[0].get("total_value") or {}) \
            .get("breakdowns", [{}])[0].get("results", [])
        if results:
            top = sorted(results, key=lambda r: -r.get("value", 0))[:3]
            desc = ", ".join(f"{r['dimension_values'][0]} ({r['value']})" for r in top)
            lines.append(f"- Ciudades principales: {desc}")
    except Exception:
        pass
    # Horarios en que la audiencia está online
    try:
        data = await _get(client, f"{user_id}/insights",
                          metric="online_followers", period="lifetime", access_token=token)
        vals = (data.get("data") or [{}])[0].get("values") or []
        if vals:
            hourly = vals[-1].get("value") or {}
            if hourly:
                top = sorted(hourly.items(), key=lambda kv: -kv[1])[:4]
                desc = ", ".join(f"{int(h):02d}:00 UTC ({v})" for h, v in top)
                lines.append(f"- Horas con más seguidores online (dato medido): {desc}")
    except Exception:
        pass
    return lines


async def fetch_instagram_context() -> Optional[str]:
    """Snapshot completo de la cuenta de Instagram para el contexto del LLM:
    perfil, insights de cuenta (si hay permiso), últimas publicaciones con
    métricas (+ insights por post), agregados y resumen histórico mensual."""
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not token:
        return None

    cached = _cached("instagram")
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=40) as client:
            prof = await _get(client, "me",
                              fields="id,username,account_type,followers_count,"
                                     "follows_count,media_count",
                              access_token=token)
            media_all: List[Dict] = []
            page = await _get(client, "me/media",
                              fields="id,caption,media_type,media_product_type,"
                                     "timestamp,like_count,comments_count,permalink",
                              limit=str(HISTORY_LIMIT), access_token=token)
            media_all = page.get("data", [])

            followers = prof.get("followers_count") or 0
            recientes = media_all[:MEDIA_LIMIT]

            # Insights por publicación (solo las más recientes, si hay permiso)
            insights_by_id: Dict[str, Dict] = {}
            for m in recientes[:INSIGHTS_MEDIA]:
                ins = await _media_insights(client, token, m["id"],
                                            m.get("media_type", ""))
                if ins:
                    insights_by_id[m["id"]] = ins

            account_lines = await _account_insights(client, token, prof["id"])
            comment_lines = await _recent_comments(client, token, recientes,
                                                   prof.get("username", ""))
            story_lines = await _active_stories(client, token)
            dm_lines = await _dm_followup(client, token, prof.get("username", ""))
    except Exception as e:
        print(f"[connectors] instagram fetch falló: {str(e)[:200]}")
        _store("instagram", None)
        return None

    lines = [
        f"Cuenta: @{prof.get('username')} ({prof.get('account_type', '?')})",
        f"Seguidores: {followers} | Seguidos: {prof.get('follows_count', '?')} | "
        f"Publicaciones totales: {prof.get('media_count', '?')}",
    ]
    if account_lines:
        lines += ["", "Métricas de la cuenta (Insights):"] + account_lines
    if story_lines:
        lines += [""] + story_lines
    if comment_lines:
        lines += [""] + comment_lines
    if dm_lines:
        lines += [""] + dm_lines

    lines += ["", f"Últimas {len(recientes)} publicaciones (más reciente primero):"]
    total_likes = total_comments = 0
    best = None
    for m in recientes:
        likes = m.get("like_count") or 0
        comments = m.get("comments_count") or 0
        total_likes += likes
        total_comments += comments
        if best is None or (likes + comments) > (best.get("like_count", 0) + best.get("comments_count", 0)):
            best = m
        caption = (m.get("caption") or "").replace("\n", " ")[:80]
        fecha = (m.get("timestamp") or "")[:10]
        extra = ""
        ins = insights_by_id.get(m["id"])
        if ins:
            parts = []
            if ins.get("reach"):
                parts.append(f"alcance {ins['reach']}")
            if ins.get("views"):
                parts.append(f"{ins['views']} vistas")
            if ins.get("saved"):
                parts.append(f"{ins['saved']} guardados")
            if ins.get("shares"):
                parts.append(f"{ins['shares']} compartidos")
            if parts:
                extra = " | " + ", ".join(parts)
        lines.append(
            f"- [{fecha}] {m.get('media_product_type') or m.get('media_type', '?')}: "
            f"{likes} me gusta, {comments} comentarios{extra} — \"{caption}\" "
            f"→ {m.get('permalink', '')}"
        )

    if recientes:
        n = len(recientes)
        lines += ["", "Agregados sobre esas publicaciones:"]
        lines.append(f"- Promedio: {total_likes / n:.1f} me gusta y {total_comments / n:.1f} comentarios por publicación")
        if followers:
            engagement = (total_likes + total_comments) / n / followers * 100
            lines.append(f"- Engagement estimado: {engagement:.2f}% ((likes+comentarios promedio) / seguidores)")
        if best is not None:
            best_caption = (best.get("caption") or "").replace("\n", " ")[:80]
            lines.append(f"- Mejor publicación: {best.get('like_count', 0)} me gusta / "
                         f"{best.get('comments_count', 0)} comentarios — \"{best_caption}\"")

    # Resumen histórico mensual (hasta HISTORY_LIMIT publicaciones)
    if len(media_all) > len(recientes):
        monthly = defaultdict(lambda: {"posts": 0, "likes": 0, "comments": 0})
        for m in media_all:
            month = (m.get("timestamp") or "")[:7]
            if not month:
                continue
            monthly[month]["posts"] += 1
            monthly[month]["likes"] += m.get("like_count") or 0
            monthly[month]["comments"] += m.get("comments_count") or 0
        lines += ["", f"Resumen histórico mensual (últimas {len(media_all)} publicaciones):"]
        for month in sorted(monthly, reverse=True)[:8]:
            s = monthly[month]
            lines.append(f"- {month}: {s['posts']} publicaciones, "
                         f"{s['likes'] / s['posts']:.1f} likes promedio, "
                         f"{s['comments']} comentarios en total")

    result = "\n".join(lines)
    _store("instagram", result)
    return result


FB_GRAPH = "https://graph.facebook.com/v23.0"


async def _fb_get(client: httpx.AsyncClient, path: str, **params) -> Dict:
    r = await client.get(f"{FB_GRAPH}/{path}", params=params)
    r.raise_for_status()
    return r.json()


def _money(cents, currency: str) -> str:
    """Presupuestos/gastos de Marketing API vienen en centavos de la moneda."""
    try:
        return f"{int(cents) / 100:,.0f} {currency}".replace(",", ".")
    except (TypeError, ValueError):
        return "?"


async def fetch_meta_ads_context() -> Optional[str]:
    """Campañas de Meta Ads (Marketing API) con resultados de los últimos 28 días.

    Credenciales vía env: META_ADS_ACCESS_TOKEN (token de Facebook Login con
    `ads_read`) y META_AD_ACCOUNT_ID (con o sin prefijo act_).
    """
    token = os.getenv("META_ADS_ACCESS_TOKEN", "").strip()
    account = os.getenv("META_AD_ACCOUNT_ID", "").strip()
    if not token or not account:
        return None
    if not account.startswith("act_"):
        account = f"act_{account}"

    cached = _cached("meta_ads")
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=40) as client:
            acct = await _fb_get(client, account,
                                 fields="name,currency,account_status",
                                 access_token=token)
            currency = acct.get("currency", "")
            camps = await _fb_get(client, f"{account}/campaigns",
                                  fields="name,effective_status,objective,"
                                         "daily_budget,lifetime_budget,"
                                         "start_time,stop_time",
                                  limit="25", access_token=token)
            campaigns = camps.get("data", [])
            ins = await _fb_get(client, f"{account}/insights",
                                level="campaign", date_preset="last_28d",
                                fields="campaign_id,campaign_name,spend,reach,"
                                       "impressions,clicks,ctr,actions",
                                access_token=token)
            by_id = {i.get("campaign_id"): i for i in ins.get("data", [])}
    except Exception as e:
        print(f"[connectors] meta_ads fetch falló: {str(e)[:200]}")
        _store("meta_ads", None)
        return None

    lines = [f"PUBLICIDAD META ADS — cuenta '{acct.get('name', account)}' (moneda {currency})"]
    if not campaigns:
        lines.append("Sin campañas creadas en la cuenta.")
    active = [c for c in campaigns if c.get("effective_status") == "ACTIVE"]
    rest = [c for c in campaigns if c.get("effective_status") != "ACTIVE"]
    for title, group in (("CAMPAÑAS ACTIVAS (promociones vigentes)", active),
                         ("OTRAS CAMPAÑAS (pausadas/terminadas)", rest[:10])):
        if not group:
            continue
        lines.append(f"\n{title}:")
        for c in group:
            budget = ""
            if c.get("daily_budget"):
                budget = f" · presupuesto diario {_money(c['daily_budget'], currency)}"
            elif c.get("lifetime_budget"):
                budget = f" · presupuesto total {_money(c['lifetime_budget'], currency)}"
            lines.append(f"- {c.get('name', '?')} [{c.get('effective_status', '?')}] · "
                         f"objetivo {c.get('objective', '?')}{budget}")
            i = by_id.get(c.get("id"))
            if i:
                acciones = ", ".join(
                    f"{a.get('value')} {a.get('action_type', '').replace('_', ' ')}"
                    for a in (i.get("actions") or [])[:4])
                lines.append(f"  Últimos 28 días: gasto {_money(float(i.get('spend', 0)) * 100, currency)}, "
                             f"alcance {i.get('reach', '?')}, {i.get('impressions', '?')} impresiones, "
                             f"{i.get('clicks', '?')} clics (CTR {i.get('ctr', '?')}%)"
                             + (f" · acciones: {acciones}" if acciones else ""))

    result = "\n".join(lines)
    _store("meta_ads", result)
    return result


async def run_connectors(connectors: list) -> Dict[str, Optional[str]]:
    """Ejecutar los conectores soportados de un perfil.

    Devuelve {nombre: contexto|None}. Los tipos no soportados se devuelven
    con None (el server los reporta como configurados-pero-pendientes).
    """
    results: Dict[str, Optional[str]] = {}
    for c in connectors or []:
        name = c.get("name", c.get("type", "conector"))
        if c.get("type") == "instagram":
            results[name] = await fetch_instagram_context()
        elif c.get("type") in ("meta_ads", "ads"):
            results[name] = await fetch_meta_ads_context()
        else:
            results[name] = None
    return results
