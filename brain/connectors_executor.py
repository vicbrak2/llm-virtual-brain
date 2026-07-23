"""
Ejecutores de conectores: integración con APIs externas (Instagram, Facebook, backend).

Arquitectura:
- Cada connector tiene un config: {"name": "...", "type": "...", "config": {...}}
- Al hacer /api/chat con connectors, se ejecutan en paralelo antes de inyectar el contexto
- Resultados se inyectan como: "CONNECTOR_RESULTS: {name} via {type}: {data}"

Esto permite que el LLM use datos en vivo sin que el usuario haga múltiples requests.
"""

import asyncio
import json
import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime


async def execute_connector(
    connector_config: Dict,
    context_user_message: str = ""
) -> Dict[str, Any]:
    """
    Ejecutar un conector y devolver datos para inyectar en el LLM.

    Args:
        connector_config: {"name": "instagram_qamiluna", "type": "instagram", "config": {...}}
        context_user_message: mensaje del usuario para contexto

    Returns:
        {"status": "ok"|"pending"|"error", "data": {...}, "error": "..."}
    """
    conn_type = connector_config.get("type", "").lower()
    conn_name = connector_config.get("name", "unknown")

    handlers = {
        "instagram": handle_instagram,
        "facebook": handle_facebook,
        "backend": handle_backend,
        "qs_manager": handle_qs_manager,
    }

    handler = handlers.get(conn_type)
    if not handler:
        return {
            "status": "error",
            "error": f"Tipo de conector no soportado: {conn_type}",
            "data": None,
        }

    try:
        result = await handler(conn_name, connector_config.get("config", {}), context_user_message)
        return result
    except Exception as e:
        return {"status": "error", "error": str(e), "data": None}


async def handle_instagram(
    name: str, config: Dict, user_msg: str
) -> Dict[str, Any]:
    """Instagram Graph API executor (stub — ready for real implementation)"""
    # En producción: llamar a Instagram Graph API con credenciales
    # Por ahora: retorna datos simulados para demo

    return {
        "status": "ok",
        "data": {
            "account": config.get("account", "@unknown"),
            "period": "last_7_days",
            "metrics": {
                "impressions": 1243,
                "reach": 856,
                "engagement": 127,
                "followers": 3421,
            },
            "note": "[DEMO] Datos simulados; en producción usa Instagram API real.",
        },
    }


async def handle_facebook(
    name: str, config: Dict, user_msg: str
) -> Dict[str, Any]:
    """Facebook Ads API executor (stub — ready for real implementation)"""
    # En producción: llamar a Facebook Ads Insights API
    # Por ahora: retorna datos simulados para demo

    return {
        "status": "ok",
        "data": {
            "ad_account": config.get("ad_account", "unknown"),
            "period": "last_30_days",
            "insights": {
                "impressions": 5200,
                "spend": 250.50,
                "conversions": 18,
                "roas": 2.8,
            },
            "note": "[DEMO] Datos simulados; en producción usa Facebook Ads API real.",
        },
    }


async def handle_backend(
    name: str, config: Dict, user_msg: str
) -> Dict[str, Any]:
    """Backend internal connector executor (stub)"""
    # En producción: llamar a backend interno (Jarvis, QS Manager, etc.)
    # Por ahora: retorna datos simulados para demo

    return {
        "status": "ok",
        "data": {
            "endpoint": config.get("endpoint", "/unknown"),
            "tasks_pending": 2,
            "high_priority": 1,
            "note": "[DEMO] Datos simulados; en producción usa backend interno real.",
        },
    }


async def handle_qs_manager(
    name: str, config: Dict, user_msg: str
) -> Dict[str, Any]:
    """QS Manager Web App connector — fetch active services + transport values."""
    gas_url = config.get("gas_url") or ""
    api_key = config.get("api_key") or ""

    if not gas_url or not api_key:
        return {
            "status": "error",
            "error": "Missing gas_url or api_key in connector config",
            "data": None,
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            services_result = await client.post(
                gas_url,
                json={
                    "action": "list_active_services",
                    "api_key": api_key,
                }
            )
            services_response = services_result.json() if services_result.status_code == 200 else {}

            transport_result = await client.post(
                gas_url,
                json={
                    "action": "get_transport_values",
                    "api_key": api_key,
                    "limit": 200,
                }
            )
            transport_response = transport_result.json() if transport_result.status_code == 200 else {}

        return {
            "status": "ok",
            "data": {
                "services": services_response.get("result", {}).get("services", [])[:10],
                "transport_groups": transport_response.get("result", {}).get("groups", []),
                "generated_at": str(services_response.get("result", {}).get("generated_at", "")),
            },
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"QS Manager connector error: {str(e)}",
            "data": None,
        }


async def execute_all_connectors(
    connectors: List[Dict], user_msg: str = ""
) -> str:
    """
    Ejecutar múltiples conectores en paralelo y formatear para inyectar en el LLM.

    Returns: string inyectable como contexto del LLM
    """
    if not connectors:
        return ""

    results = await asyncio.gather(
        *[execute_connector(c, user_msg) for c in connectors],
        return_exceptions=False,
    )

    lines = ["[CONNECTOR RESULTS]\n"]
    for connector_config, result in zip(connectors, results):
        name = connector_config.get("name", "unknown")
        status = result.get("status", "unknown")
        if status == "ok":
            data = result.get("data", {})
            data_str = json.dumps(data, ensure_ascii=False)[:150]
            lines.append(f"✓ {name}: {data_str}")
        else:
            lines.append(f"✗ {name}: {result.get('error', 'Error')}")

    return "\n".join(lines)
