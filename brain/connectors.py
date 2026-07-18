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
    facebook_page — Página de Facebook (graph.facebook.com): perfil, fans y
        últimas publicaciones con reacciones/comentarios/compartidos.
        Reutiliza META_ADS_ACCESS_TOKEN (necesita pages_show_list +
        pages_read_engagement); toma la primera página de /me/accounts.
"""

import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from .tokens import get_token

IG_GRAPH = "https://graph.instagram.com/v23.0"
CACHE_TTL_SECONDS = 600          # 10 min: métricas sociales no cambian por mensaje
MEDIA_LIMIT = 15                 # publicaciones detalladas en el contexto
HISTORY_LIMIT = 100              # publicaciones para el resumen histórico mensual
INSIGHTS_MEDIA = 8               # publicaciones recientes con insights detallados

_cache: Dict[str, Dict] = {}     # key → {"ts": epoch, "data": str|None}
_status: Dict[str, Dict] = {}    # tipo → {"status": ok|pendiente|error, "detail": str, "ts": epoch}


def _set_status(kind: str, status: str, detail: str = ""):
    _status[kind] = {"status": status, "detail": detail, "ts": time.time()}


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


_HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)


def _hashtag_performance(media: List[Dict], insights_by_id: Dict[str, Dict],
                         min_posts: int = 2, top_n: int = 8) -> List[str]:
    """Agrega alcance/likes/guardados por hashtag a partir de los captions
    completos de `media`. Solo reporta hashtags usados en >= min_posts
    publicaciones (con menos, el promedio es ruido, no señal)."""
    stats: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"posts": 0, "likes": 0, "comments": 0, "reach": 0, "saved": 0, "con_alcance": 0})

    for m in media:
        caption = m.get("caption") or ""
        tags = {t.lower() for t in _HASHTAG_RE.findall(caption)}
        if not tags:
            continue
        likes = m.get("like_count") or 0
        comments = m.get("comments_count") or 0
        ins = insights_by_id.get(m["id"], {})
        reach = ins.get("reach") or 0
        saved = ins.get("saved") or 0
        for tag in tags:
            s = stats[tag]
            s["posts"] += 1
            s["likes"] += likes
            s["comments"] += comments
            if reach:
                s["reach"] += reach
                s["con_alcance"] += 1
            s["saved"] += saved

    calificables = {tag: s for tag, s in stats.items() if s["posts"] >= min_posts}
    if not calificables:
        return []

    def score(s: Dict[str, float]) -> float:
        # Alcance promedio si hay datos de insights; si no, engagement (likes+comentarios)
        if s["con_alcance"]:
            return s["reach"] / s["con_alcance"]
        return (s["likes"] + s["comments"]) / s["posts"]

    ranking = sorted(calificables.items(), key=lambda kv: score(kv[1]), reverse=True)[:top_n]

    lines = [f"Rendimiento por hashtag (usados en {min_posts}+ de las publicaciones analizadas):"]
    for tag, s in ranking:
        n = s["posts"]
        parts = [f"{s['likes']/n:.1f} likes/post", f"{s['comments']/n:.1f} comentarios/post"]
        if s["con_alcance"]:
            parts.insert(0, f"{s['reach']/s['con_alcance']:.0f} alcance/post")
        if s["saved"]:
            parts.append(f"{s['saved']/n:.1f} guardados/post")
        lines.append(f"- #{tag} ({n} publicaciones): " + ", ".join(parts))
    return lines


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
    token = get_token("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        _set_status("instagram", "pendiente", "falta INSTAGRAM_ACCESS_TOKEN en .env")
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
        _set_status("instagram", "error", str(e)[:120])
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

    hashtag_lines = _hashtag_performance(recientes, insights_by_id)
    if hashtag_lines:
        lines += [""] + hashtag_lines

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
    _set_status("instagram", "ok",
                f"@{prof.get('username', '?')} · {prof.get('followers_count', '?')} seguidores")
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
    token = get_token("META_ADS_ACCESS_TOKEN")
    account = os.getenv("META_AD_ACCOUNT_ID", "").strip()
    if not token or not account:
        _set_status("meta_ads", "pendiente", "faltan META_ADS_ACCESS_TOKEN / META_AD_ACCOUNT_ID en .env")
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
        _set_status("meta_ads", "error", str(e)[:120])
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
    _set_status("meta_ads", "ok",
                f"cuenta {acct.get('name', account)} · {len(active)} campañas activas")
    _store("meta_ads", result)
    return result


async def fetch_facebook_page_context() -> Optional[str]:
    """Snapshot de la página de Facebook: perfil, fans y últimas publicaciones.

    Reutiliza META_ADS_ACCESS_TOKEN (scopes pages_show_list +
    pages_read_engagement ya concedidos junto con ads_read).
    """
    token = os.getenv("FACEBOOK_PAGE_TOKEN", "").strip() or \
        get_token("META_ADS_ACCESS_TOKEN")
    if not token:
        _set_status("facebook_page", "pendiente", "falta META_ADS_ACCESS_TOKEN en .env")
        return None

    cached = _cached("facebook_page")
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=40) as client:
            accounts = await _fb_get(client, "me/accounts",
                                     fields="id,name,access_token,fan_count,"
                                            "followers_count,link,category",
                                     access_token=token)
            pages = accounts.get("data", [])
            if not pages:
                _set_status("facebook_page", "error",
                            "el token no administra ninguna página (pages_show_list)")
                _store("facebook_page", None)
                return None
            page = pages[0]
            page_token = page.get("access_token") or token
            try:
                # Con pages_read_user_content: posts con reacciones y comentarios
                posts = await _fb_get(client, f"{page['id']}/posts",
                                      fields="message,created_time,shares,"
                                             "reactions.summary(true),"
                                             "comments.summary(true),permalink_url",
                                      limit="10", access_token=page_token)
            except Exception:
                # Sin ese permiso: posts básicos (sin métricas de interacción)
                posts = await _fb_get(client, f"{page['id']}/posts",
                                      fields="message,created_time,shares,permalink_url",
                                      limit="10", access_token=page_token)
            post_list = posts.get("data", [])
    except Exception as e:
        print(f"[connectors] facebook_page fetch falló: {str(e)[:200]}")
        _set_status("facebook_page", "error", str(e)[:120])
        _store("facebook_page", None)
        return None

    lines = [f"PÁGINA DE FACEBOOK — '{page.get('name', '?')}' ({page.get('category', '')})",
             f"Fans: {page.get('fan_count', '?')} · Seguidores: {page.get('followers_count', '?')} "
             f"· {page.get('link', '')}"]
    if not post_list:
        lines.append("Sin publicaciones recientes en la página.")
    else:
        lines.append(f"\nÚLTIMAS {len(post_list)} PUBLICACIONES:")
        for p in post_list:
            texto = (p.get("message") or "(sin texto)").replace("\n", " ")[:80]
            fecha = (p.get("created_time") or "")[:10]
            shares = (p.get("shares") or {}).get("count", 0)
            if "reactions" in p or "comments" in p:
                reacts = ((p.get("reactions") or {}).get("summary") or {}).get("total_count", 0)
                comments = ((p.get("comments") or {}).get("summary") or {}).get("total_count", 0)
                lines.append(f"- [{fecha}] \"{texto}\" — {reacts} reacciones, "
                             f"{comments} comentarios, {shares} compartidos")
            else:
                lines.append(f"- [{fecha}] \"{texto}\" — {shares} compartidos "
                             f"(reacciones/comentarios requieren permiso pages_read_user_content)")

    result = "\n".join(lines)
    _set_status("facebook_page", "ok",
                f"página {page.get('name', '?')} · {page.get('fan_count', '?')} fans")
    _store("facebook_page", result)
    return result


async def fetch_whatsapp_context() -> Optional[str]:
    """WhatsApp Business (Cloud API): números, calidad, plantillas y
    analítica de conversaciones de los últimos 28 días.

    Credenciales vía env: WHATSAPP_BUSINESS_ACCOUNT_ID (WABA) y
    WHATSAPP_ACCESS_TOKEN (si falta, reutiliza META_ADS_ACCESS_TOKEN con
    scope whatsapp_business_management)."""
    token = get_token("WHATSAPP_ACCESS_TOKEN") or get_token("META_ADS_ACCESS_TOKEN")
    waba = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "").strip()
    if not token or not waba:
        _set_status("whatsapp", "pendiente",
                    "faltan WHATSAPP_BUSINESS_ACCOUNT_ID (Business Manager → WhatsApp) "
                    "y/o token con whatsapp_business_management")
        return None
    cached = _cached("whatsapp")
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            info = await _fb_get(client, waba, fields="name,message_template_namespace",
                                 access_token=token)
            phones = (await _fb_get(client, f"{waba}/phone_numbers",
                                    fields="display_phone_number,verified_name,"
                                           "quality_rating,code_verification_status",
                                    access_token=token)).get("data", [])
            templates = (await _fb_get(client, f"{waba}/message_templates",
                                       fields="name,status,category", limit="15",
                                       access_token=token)).get("data", [])
            analytics_lines: List[str] = []
            try:
                now = int(time.time())
                d = await _fb_get(client, waba,
                                  fields=f"analytics.start({now - 28*86400}).end({now}).granularity(MONTH)",
                                  access_token=token)
                pts = ((d.get("analytics") or {}).get("data_points")) or []
                sent = sum(p.get("sent", 0) for p in pts)
                delivered = sum(p.get("delivered", 0) for p in pts)
                if sent or delivered:
                    analytics_lines.append(f"- Mensajes últimos 28 días: {sent} enviados, {delivered} entregados")
            except Exception:
                pass
    except Exception as e:
        print(f"[connectors] whatsapp fetch falló: {str(e)[:200]}")
        _set_status("whatsapp", "error", str(e)[:120])
        _store("whatsapp", None)
        return None

    lines = [f"WhatsApp Business: {info.get('name', waba)}"]
    for p in phones:
        lines.append(f"- Número: {p.get('display_phone_number', '?')} "
                     f"({p.get('verified_name', '?')}) — calidad {p.get('quality_rating', '?')}")
    if templates:
        aprobadas = [t for t in templates if t.get("status") == "APPROVED"]
        lines.append(f"- Plantillas: {len(aprobadas)} aprobadas de {len(templates)} "
                     f"({', '.join(t['name'] for t in aprobadas[:6])})")
    else:
        lines.append("- Sin plantillas de mensaje creadas aún")
    lines += analytics_lines
    result = "\n".join(lines)
    _set_status("whatsapp", "ok", f"{len(phones)} número(s), {len(templates)} plantilla(s)")
    _store("whatsapp", result)
    return result


async def fetch_messenger_context() -> Optional[str]:
    """Bandeja de Messenger de la página de Facebook: quién espera respuesta.
    Reutiliza META_ADS_ACCESS_TOKEN; necesita el scope pages_messaging
    (el page token se obtiene de /me/accounts)."""
    token = get_token("META_ADS_ACCESS_TOKEN")
    if not token:
        _set_status("messenger", "pendiente", "falta META_ADS_ACCESS_TOKEN en .env")
        return None
    cached = _cached("messenger")
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            accounts = await _fb_get(client, "me/accounts",
                                     fields="id,name,access_token", access_token=token)
            pages = accounts.get("data", [])
            if not pages:
                _set_status("messenger", "error", "el token no administra ninguna página")
                _store("messenger", None)
                return None
            page = pages[0]
            page_token = page.get("access_token") or token
            data = await _fb_get(client, f"{page['id']}/conversations",
                                 platform="messenger",
                                 fields="participants,updated_time,"
                                        "messages.limit(2){from,created_time,message}",
                                 limit="15", access_token=page_token)
    except Exception as e:
        detail = str(e)[:150]
        if ("pages_messaging" in detail or "permission" in detail.lower()
                or "(#200)" in detail or "403" in detail):
            _set_status("messenger", "pendiente",
                        "el token no tiene el scope pages_messaging — regenerarlo agregándolo")
        else:
            print(f"[connectors] messenger fetch falló: {detail}")
            _set_status("messenger", "error", detail[:120])
        _store("messenger", None)
        return None

    convs = data.get("data", [])
    page_name = page.get("name", "página")
    if not convs:
        result = f"Messenger ({page_name}): sin conversaciones registradas."
        _set_status("messenger", "ok", "0 conversaciones")
        _store("messenger", result)
        return result
    pendientes = 0
    lines: List[str] = []
    for conv in convs:
        parts = (conv.get("participants") or {}).get("data", [])
        other = next((p.get("name", "?") for p in parts
                      if p.get("id") != page["id"]), "?")
        msgs = (conv.get("messages") or {}).get("data", [])
        if not msgs:
            continue
        last = msgs[0]
        fecha = (last.get("created_time") or "")[:10]
        texto = (last.get("message") or "").replace("\n", " ")[:80]
        if (last.get("from") or {}).get("id") == page["id"]:
            estado = "respondido por el equipo"
        else:
            estado = "ESPERANDO RESPUESTA del equipo"
            pendientes += 1
        lines.append(f"- {other} [último mensaje {fecha}]: \"{texto}\" ({estado})")
    lines.insert(0, f"Messenger ({page_name}) — {pendientes} conversaciones esperando respuesta:")
    result = "\n".join(lines)
    _set_status("messenger", "ok", f"{len(convs)} conversaciones, {pendientes} pendientes")
    _store("messenger", result)
    return result


TH_GRAPH = "https://graph.threads.net/v1.0"


async def fetch_threads_context() -> Optional[str]:
    """Perfil y últimos posts de Threads con vistas/likes si hay permiso de insights.
    Credenciales vía env: THREADS_ACCESS_TOKEN (Threads API, scope threads_basic
    + threads_manage_insights opcional)."""
    token = get_token("THREADS_ACCESS_TOKEN")
    if not token:
        _set_status("threads", "pendiente",
                    "falta THREADS_ACCESS_TOKEN (caso de uso 'API de Threads' → generar token)")
        return None
    cached = _cached("threads")
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.get(f"{TH_GRAPH}/me", params={
                "fields": "username,threads_biography", "access_token": token})
            r.raise_for_status()
            prof = r.json()
            r = await client.get(f"{TH_GRAPH}/me/threads", params={
                "fields": "id,text,timestamp,permalink", "limit": "10",
                "access_token": token})
            r.raise_for_status()
            posts = r.json().get("data", [])
            post_lines: List[str] = []
            for t in posts:
                extra = ""
                try:
                    ri = await client.get(f"{TH_GRAPH}/{t['id']}/insights", params={
                        "metric": "views,likes,replies,reposts", "access_token": token})
                    ri.raise_for_status()
                    ins = {x["name"]: (x.get("values") or [{}])[0].get("value", 0)
                           for x in ri.json().get("data", [])}
                    if ins:
                        extra = f" | {ins.get('views', 0)} vistas, {ins.get('likes', 0)} likes, " \
                                f"{ins.get('replies', 0)} respuestas"
                except Exception:
                    pass
                texto = (t.get("text") or "").replace("\n", " ")[:80]
                post_lines.append(f"- [{(t.get('timestamp') or '')[:10]}] \"{texto}\"{extra} "
                                  f"→ {t.get('permalink', '')}")
    except Exception as e:
        print(f"[connectors] threads fetch falló: {str(e)[:200]}")
        _set_status("threads", "error", str(e)[:120])
        _store("threads", None)
        return None

    lines = [f"Threads: @{prof.get('username', '?')}"]
    if post_lines:
        lines.append(f"Últimos {len(post_lines)} posts:")
        lines += post_lines
    else:
        lines.append("Sin posts publicados aún.")
    result = "\n".join(lines)
    _set_status("threads", "ok", f"{len(post_lines)} posts")
    _store("threads", result)
    return result


async def _meta_token_expiry() -> Optional[int]:
    """Días restantes del META_ADS_ACCESS_TOKEN (via debug_token; cache 1h)."""
    token = get_token("META_ADS_ACCESS_TOKEN")
    if not token:
        return None
    hit = _cache.get("meta_token_expiry")
    if hit and (time.time() - hit["ts"]) < 3600:
        return hit["data"]
    days = None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            d = await _fb_get(client, "debug_token",
                              input_token=token, access_token=token)
            expires = (d.get("data") or {}).get("expires_at") or 0
            if expires:
                days = max(0, int((expires - time.time()) / 86400))
    except Exception:
        pass
    _cache["meta_token_expiry"] = {"ts": time.time(), "data": days}
    return days


async def connectors_health(connectors: list, trigger: bool = True) -> List[Dict]:
    """Estado en vivo de los conectores de un perfil para /api/status y la UI.

    Con trigger=True ejecuta cada conector (usa el cache de 10 min, así que es
    barato); con trigger=False solo reporta el último estado conocido.
    Devuelve [{name, type, status, detail, expires_in_days}].
    """
    if trigger:
        await run_connectors(connectors)
    expiry = await _meta_token_expiry() if (trigger or _status) else None
    out = []
    for c in connectors or []:
        kind = c.get("type", "?")
        st = _status.get(kind, {"status": "pendiente", "detail": "sin datos aún (se activa con el primer chat)"})
        item = {"name": c.get("name", kind), "type": kind,
                "status": st["status"], "detail": st.get("detail", "")}
        if kind in ("meta_ads", "ads", "facebook_page") and expiry is not None:
            item["expires_in_days"] = expiry
        out.append(item)
    return out


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
        elif c.get("type") == "facebook_page":
            results[name] = await fetch_facebook_page_context()
        elif c.get("type") == "whatsapp":
            results[name] = await fetch_whatsapp_context()
        elif c.get("type") == "messenger":
            results[name] = await fetch_messenger_context()
        elif c.get("type") == "threads":
            results[name] = await fetch_threads_context()
        else:
            results[name] = None
    return results


# ============ WEBHOOK HANDLERS & GOOGLE SHEETS INTEGRATION ============

# Cola local anti-pérdida: si Sheets no responde, los leads quedan aquí
# y se reintentan en el loop periódico (cada 15 min). Vive en data/ porque
# es el volumen persistente en Docker (brain/ es efímero en el contenedor).
PENDING_LEADS_FILE = Path(os.getenv("BRAIN_DATA", "data")) / "pending_leads.jsonl"

# Encabezados por pestaña: el GAS crea la pestaña con estos headers si no existe.
TAB_HEADERS = {
    "LEADS_INSTAGRAM": ["Timestamp", "Nombre", "Teléfono", "Email", "Interés",
                        "Ciudad", "Score", "Status", "Asignada a", "Fecha Contacto"],
    "CONTACTOS_DIRECTOS": ["Timestamp", "Nombre", "Mensaje", "Plataforma",
                           "Leído", "Respondido", "Asignada a"],
    "CAMPAÑAS_ADS": ["Fecha", "Campaña", "Objetivo", "Spend ($)", "Impressiones",
                     "Clicks", "CTR (%)", "Conversiones", "ROAS", "Status"],
}


async def _append_to_gsheet(sheet_id: str, tab: str, values: List[List]) -> bool:
    """Agregar filas a una pestaña de Google Sheets vía GAS Web App.

    La API de Sheets no permite escrituras con API key, así que el append
    va por un Google Apps Script propio (env LEADS_GAS_URL) que abre el
    spreadsheet por id y agrega las filas. Ver docs/GAS_LEADS_SNIPPET.gs.
    """
    gas_url = os.getenv("LEADS_GAS_URL", "").strip()
    if not gas_url:
        print("[gsheet] falta LEADS_GAS_URL en .env (ver docs/GAS_LEADS_SNIPPET.gs)")
        return False
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.post(gas_url, json={
                "action": "appendRows",
                "spreadsheetId": sheet_id,
                "sheet": tab,
                "headers": TAB_HEADERS.get(tab, []),
                "rows": values,
            })
            r.raise_for_status()
            data = r.json()
            if data.get("ok") and not data.get("error"):
                return True
            print(f"[gsheet] GAS respondió error: {str(data)[:120]}")
            return False
    except Exception as e:
        print(f"[gsheet] append falló: {str(e)[:120]}")
        return False


def _queue_pending_lead(tab: str, row: List) -> None:
    """Guarda un lead que no pudo escribirse en Sheets para reintentarlo después."""
    try:
        with open(PENDING_LEADS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"tab": tab, "row": row}, ensure_ascii=False) + "\n")
        print(f"[gsheet] lead encolado en {PENDING_LEADS_FILE.name} (se reintenta cada 15 min)")
    except Exception as e:
        print(f"[gsheet] ERROR CRÍTICO: no se pudo encolar lead: {str(e)[:120]}")


async def flush_pending_leads() -> int:
    """Reintenta los leads pendientes de la cola local. Devuelve cuántos se insertaron."""
    if not PENDING_LEADS_FILE.exists():
        return 0
    sheet_id = os.getenv("GOOGLE_SHEETS_ID", "").strip()
    try:
        lines = PENDING_LEADS_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return 0
    if not lines:
        return 0

    remaining, flushed = [], 0
    for line in lines:
        try:
            item = json.loads(line)
        except Exception:
            continue  # línea corrupta: descartar
        if await _append_to_gsheet(sheet_id, item["tab"], [item["row"]]):
            flushed += 1
        else:
            remaining.append(line)

    PENDING_LEADS_FILE.write_text(
        "\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8")
    if flushed:
        print(f"[gsheet] cola vaciada: {flushed} lead(s) insertados, {len(remaining)} pendientes")
    return flushed


async def _fetch_lead_details(leadgen_id: str) -> Optional[Dict]:
    """Meta solo envía leadgen_id en el webhook real: los datos del formulario
    se obtienen con GET /{leadgen_id} (requiere permiso leads_retrieval)."""
    token = get_token("META_ADS_ACCESS_TOKEN")
    if not token:
        print("[webhook] sin META_ADS_ACCESS_TOKEN para leer el lead")
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://graph.facebook.com/v23.0/{leadgen_id}",
                params={"fields": "field_data,created_time", "access_token": token})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print(f"[webhook] fetch de lead {leadgen_id} falló: {str(e)[:120]}")
        return None


async def handle_instagram_leads_webhook(payload: Dict) -> bool:
    """Procesa webhook de Instagram Lead Ads.

    Soporta ambos formatos:
    - Real de Meta: entry[].changes[] con field="leadgen" y value.leadgen_id
      (los datos del formulario se buscan vía API con leads_retrieval).
    - De prueba/directo: entry[].leadgen[] con field_data inline.

    Extrae datos del formulario, calcula score, inserta en Google Sheets.
    NO responde automáticamente; solo captura y clasifica.
    """
    sheet_id = os.getenv("GOOGLE_SHEETS_ID", "").strip()
    if not sheet_id:
        print("[webhook] GOOGLE_SHEETS_ID no configurado")
        return False

    for entry in payload.get("entry", []):
        # Formato real de Meta: changes[] con leadgen_id → fetch vía API
        leadgens = list(entry.get("leadgen", []))
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            leadgen_id = str(change.get("value", {}).get("leadgen_id", ""))
            if not leadgen_id:
                continue
            detail = await _fetch_lead_details(leadgen_id)
            if detail:
                leadgens.append(detail)
            else:
                # Sin datos no se puede armar la fila; guardar el id para rescate manual
                _queue_pending_lead("LEADS_INSTAGRAM", [
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    f"(pendiente fetch lead {leadgen_id})",
                    "—", "—", "—", "—", 0, "🆕", "", ""])

        for leadgen in leadgens:
            lead_data = {}
            for field in leadgen.get("field_data", []):
                name = field.get("name", "").lower()
                values = field.get("values", [])
                if values:
                    lead_data[name] = values[0]

            # Calcular score: +1 por teléfono, +1 por email
            score = 0
            if lead_data.get("phone_number"):
                score += 1
            if lead_data.get("email"):
                score += 1

            # Preparar fila para Sheets (created_time puede ser unix int o ISO string)
            created = leadgen.get("created_time", time.time())
            try:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(created)))
            except (TypeError, ValueError):
                timestamp = str(created)[:19].replace("T", " ")
            row = [
                timestamp,
                lead_data.get("full_name", "—"),
                lead_data.get("phone_number", "—"),
                lead_data.get("email", "—"),
                lead_data.get("interested_in", "—"),
                lead_data.get("city", "—"),
                score,
                "🆕",  # Status
                "",    # Asignada a (manual)
                ""     # Fecha Contacto (manual)
            ]

            # Insertar en Sheets; si falla, encolar localmente (nunca perder un lead)
            success = await _append_to_gsheet(sheet_id, "LEADS_INSTAGRAM", [row])
            if success:
                print(f"[webhook] Lead capturado: {lead_data.get('full_name', '?')} "
                      f"({lead_data.get('interested_in', '?')})")
            else:
                _queue_pending_lead("LEADS_INSTAGRAM", row)
            # Notificar al equipo aunque Sheets falle: el lead existe igual
            await _notify_team_lead(lead_data)

    return True


async def _notify_team_lead(lead_data: Dict) -> None:
    """Envía notificación por email/Slack sobre nuevo lead."""
    name = lead_data.get("full_name", "Desconocido")
    interest = lead_data.get("interested_in", "—")
    phone = lead_data.get("phone_number", "—")

    message = f"📩 Nuevo lead de Instagram: {name} ({interest})\nTeléfono: {phone}"

    # Email notification
    emails = os.getenv("NOTIFICATION_EMAIL", "").split(",")
    if emails and emails[0].strip():
        print(f"[notify] Email sería enviado a: {emails}")
        # En producción: usar smtplib o SendGrid
        # send_email(emails, f"Nuevo lead: {name}", message)

    # Slack notification (si está configurado)
    slack_hook = os.getenv("SLACK_WEBHOOK", "").strip()
    if slack_hook and "YOUR/SLACK" not in slack_hook:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(slack_hook, json={"text": message})
                print(f"[notify] Slack enviado")
        except Exception as e:
            print(f"[notify] Slack falló: {str(e)[:80]}")


async def sync_meta_ads_insights() -> bool:
    """Sincroniza métricas de Meta Ads cada 6 horas.

    Si ROAS < 2, marca como ⚠️ Revisar en Sheets.
    """
    token = get_token("META_ADS_ACCESS_TOKEN")
    account = os.getenv("META_AD_ACCOUNT_ID", "").strip()
    sheet_id = os.getenv("GOOGLE_SHEETS_ID", "").strip()

    if not all([token, account, sheet_id]):
        print("[ads_sync] Faltan credenciales")
        return False

    if not account.startswith("act_"):
        account = f"act_{account}"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # Obtener insights de campañas
            ins = await _fb_get(client, f"{account}/insights",
                               level="campaign", date_preset="last_7d",
                               fields="campaign_id,campaign_name,spend,reach,"
                                      "impressions,clicks,ctr,actions",
                               access_token=token)

            campaigns = ins.get("data", [])
            timestamp = time.strftime("%Y-%m-%d")

            for camp in campaigns:
                spend = float(camp.get("spend", 0)) / 100  # Centavos a USD
                actions = camp.get("actions", [])
                revenue = sum(float(a.get("value", 0)) for a in actions if a.get("action_type") == "purchase")
                roas = (revenue / spend) if spend > 0 else 0

                status = "✅" if roas >= 2 else ("⚠️ Revisar" if roas >= 1.5 else "❌ Baja")

                row = [
                    timestamp,
                    camp.get("campaign_name", "?"),
                    "CONVERSIONS",
                    f"{spend:.2f}",
                    camp.get("impressions", "?"),
                    camp.get("clicks", "?"),
                    camp.get("ctr", "?"),
                    len(actions),
                    f"{roas:.2f}",
                    status
                ]

                await _append_to_gsheet(sheet_id, "CAMPAÑAS_ADS", [row])
                print(f"[ads_sync] {camp.get('campaign_name', '?')}: ROAS {roas:.2f} ({status})")

            return True
    except Exception as e:
        print(f"[ads_sync] Error: {str(e)[:120]}")
        return False


async def sync_instagram_dms() -> bool:
    """Sincroniza DMs de Instagram cada 15 minutos (lectura sin respuesta)."""
    token = get_token("INSTAGRAM_ACCESS_TOKEN")
    ig_user_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "").strip()
    sheet_id = os.getenv("GOOGLE_SHEETS_ID", "").strip()

    if not all([token, ig_user_id, sheet_id]):
        print("[dm_sync] Faltan credenciales")
        return False

    # Memoria de mensajes ya insertados (evita duplicar filas en cada pasada)
    seen_path = Path(os.getenv("BRAIN_DATA", "data")) / "dm_seen.json"
    try:
        seen = set(json.loads(seen_path.read_text(encoding="utf-8")))
    except Exception:
        seen = set()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            data = await _get(client, f"{ig_user_id}/conversations",
                            fields="id,updated_time,"
                                   "messages.limit(10){id,message,from,created_time}",
                            access_token=token)

            nuevos = 0
            for conv in data.get("data", []):
                for msg in conv.get("messages", {}).get("data", []):
                    msg_id = msg.get("id", "")
                    sender = msg.get("from", {}) or {}
                    # Solo mensajes entrantes (no los que envía la propia cuenta)
                    if not msg_id or msg_id in seen or sender.get("id") == ig_user_id:
                        continue
                    texto = (msg.get("message") or "").strip()
                    if not texto:
                        continue  # stickers/media sin texto

                    ts = str(msg.get("created_time", ""))[:19].replace("T", " ")
                    row = [
                        ts or time.strftime("%Y-%m-%d %H:%M:%S"),
                        sender.get("username", "desconocido"),
                        texto[:500],
                        "Instagram DM",
                        "✅",  # leído por Brain
                        "❌",  # no respondido aún (manual)
                        ""     # asignada a (manual)
                    ]
                    if await _append_to_gsheet(sheet_id, "CONTACTOS_DIRECTOS", [row]):
                        seen.add(msg_id)
                        nuevos += 1

            if nuevos:
                seen_path.parent.mkdir(parents=True, exist_ok=True)
                seen_path.write_text(json.dumps(sorted(seen)), encoding="utf-8")
                print(f"[dm_sync] {nuevos} mensaje(s) nuevo(s) sincronizados")
            return True

    except Exception as e:
        print(f"[dm_sync] Error: {str(e)[:120]}")
        return False
