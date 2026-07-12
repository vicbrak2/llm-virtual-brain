"""Core Brain: Orquestador de LLM multi-proveedor con rotación dinámica."""

import json
import re
from dataclasses import dataclass
from typing import Optional, Dict, List, Union

import httpx

from .errors import BrainError
from .providers import Provider, provider_from_dict
from .context import ContextProvider, context_from_dict
from .prompts import PromptLoader, loader_from_dict


@dataclass
class Message:
    """Mensaje en la conversación LLM."""
    role: str  # "system", "user", "assistant"
    content: str

    def to_dict(self) -> Dict:
        return {"role": self.role, "content": self.content}


class Brain:
    """
    Orquestador de LLM agnóstico y reutilizable.

    - Rotación dinámica entre providers (si uno falla, intenta el siguiente
      con los MISMOS mensajes — nunca pierde contexto).
    - Sticky: recuerda qué provider respondió bien para no reintentar caídos.
    - Multi-etapa: formatter → analyzer → custom.
    - Contexto pluggable: Sheets, SQL, vault, custom.

    Se puede construir de dos formas:
        Brain(config)                          # BrainConfig (de load_config_from_yaml)
        Brain(providers=[...], ...)            # componentes explícitos
    """

    def __init__(
        self,
        config=None,
        *,
        providers: Optional[List[Provider]] = None,
        context_provider: Optional[ContextProvider] = None,
        prompt_loader: Optional[PromptLoader] = None,
        timeout_seconds: int = 30,
        app_name: str = "brain_app",
    ):
        if config is not None:
            # Construcción desde BrainConfig
            providers = [
                provider_from_dict(p if isinstance(p, dict) else p.model_dump())
                for p in config.providers
            ]
            ctx = getattr(config, "context", None)
            if ctx is not None and getattr(ctx, "type", "none") != "none":
                context_provider = context_from_dict({"type": ctx.type, **ctx.config})
            pr = getattr(config, "prompts", None)
            if pr is not None:
                prompt_loader = loader_from_dict({"type": pr.type, **pr.config})
            timeout_seconds = getattr(config, "timeout_seconds", timeout_seconds)
            app_name = getattr(config, "app_name", app_name)

        self.providers = providers or []
        self.context_provider = context_provider
        self.prompt_loader = prompt_loader
        self.timeout_seconds = timeout_seconds
        self.app_name = app_name

        # Estado sticky (rotación dinámica)
        self._active_idx = 0
        self._last_used: Optional[str] = None

        if not self.providers:
            raise BrainError("Se requiere al menos un provider")

    # ── API de bajo nivel: mensajes ya construidos ─────────────────────────
    async def complete(
        self,
        messages: List[Union[Dict, Message]],
        max_tokens: int = 600,
        temperature: float = 0.2,
    ) -> str:
        """
        Completar una conversación ya construida (lista de dicts o Message).
        Ideal cuando la app arma sus propios messages (historial, contexto custom).
        Rota providers automáticamente si alguno falla.
        """
        return await self._call_providers_chain(messages, max_tokens, temperature)

    # ── API de alto nivel: prompt por etapa + contexto ─────────────────────
    async def think(
        self,
        user_msg: str,
        context_data: Optional[Dict] = None,
        max_tokens: int = 600,
        temperature: float = 0.2,
        stage_name: str = "default",
    ) -> str:
        """
        Consultar al LLM: carga el prompt de la etapa, enriquece contexto
        (si hay ContextProvider) y llama a la cadena de providers.
        """
        system_prompt = ""
        if self.prompt_loader:
            system_prompt = self.prompt_loader.get(stage_name)

        enriched = dict(context_data or {})
        if self.context_provider:
            try:
                enriched = await self.context_provider.enrich(user_msg, enriched)
            except Exception as e:
                print(f"[brain] contexto falló (continúo sin él): {e}")

        messages = self._build_messages(system_prompt, user_msg, enriched)
        return await self._call_providers_chain(messages, max_tokens, temperature)

    async def think_json(
        self,
        user_msg: str,
        context_data: Optional[Dict] = None,
        max_tokens: int = 900,
        temperature: float = 0.0,
        stage_name: str = "default",
    ) -> Dict:
        """Igual que think() pero parseando el primer JSON de la respuesta."""
        raw = await self.think(user_msg, context_data, max_tokens, temperature, stage_name)
        parsed = extract_json(raw)
        if parsed is None:
            raise BrainError(f"Sin JSON válido en la respuesta: {raw[:200]}")
        return parsed

    async def think_multi_stage(
        self,
        user_msg: str,
        stages: List[str],
        context_data: Optional[Dict] = None,
    ) -> str:
        """Ejecuta etapas en secuencia; la salida de una alimenta la siguiente."""
        result = user_msg
        for stage in stages:
            result = await self.think(result, context_data, stage_name=stage)
        return result

    # ── Internals ───────────────────────────────────────────────────────────
    async def _call_providers_chain(
        self,
        messages: List,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Cadena con rotación dinámica y sticky index."""
        n = len(self.providers)
        errors = []

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for offset in range(n):
                idx = (self._active_idx + offset) % n
                provider = self.providers[idx]
                try:
                    response = await self._call_provider(
                        client, provider, messages, max_tokens, temperature
                    )
                    if offset:
                        print(f"[brain] rotación dinámica → {provider.name} ({provider.model})")
                    self._active_idx = idx
                    self._last_used = provider.name
                    return response
                except Exception as e:
                    body = ""
                    resp = getattr(e, "response", None)
                    if resp is not None:
                        try:
                            body = resp.text[:120]
                        except Exception:
                            body = ""
                    errors.append(f"{provider.name}: {str(e)[:80]} {body}".strip())
                    continue

        raise BrainError("Todos los providers fallaron · " + " | ".join(errors))

    async def _call_provider(
        self,
        client: httpx.AsyncClient,
        provider: Provider,
        messages: List,
        max_tokens: int,
        temperature: float,
    ) -> str:
        headers = provider.get_headers()
        payload = provider.get_payload(messages, max_tokens, temperature)

        r = await client.post(provider.url, headers=headers, json=payload)
        r.raise_for_status()

        content = provider.parse_response(r.json())
        if not content.strip():
            raise ValueError("respuesta vacía (sin content)")
        return content

    def _build_messages(self, system_prompt: str, user_msg: str, context: Dict) -> List[Message]:
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            messages.append(Message(role="system", content=f"CONTEXTO:\n{context_str}"))
        messages.append(Message(role="user", content=user_msg))
        return messages

    def status(self) -> Dict:
        """Estado actual: provider activo, cadena configurada."""
        active = self._last_used or (self.providers[self._active_idx].name if self.providers else None)
        return {
            "app": self.app_name,
            "enabled": bool(self.providers),
            "active": active,
            "count": len(self.providers),
            "providers": [
                {"order": i, "name": p.name, "model": p.model}
                for i, p in enumerate(self.providers)
            ],
        }


def extract_json(text: str) -> Optional[Dict]:
    """Extraer el primer objeto JSON de un texto (o None)."""
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return None
