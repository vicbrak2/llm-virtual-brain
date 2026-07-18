"""Core Brain: Orquestador de LLM multi-proveedor con rotación dinámica."""

import json
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Dict, List, Union

import httpx

from .errors import BrainError
from .providers import KNOWN_PROVIDERS, Provider, provider_from_dict
from .context import ContextProvider, context_from_dict
from .prompts import PromptLoader, loader_from_dict

MAX_CONTINUATIONS = 3  # reintentos de "continúa" ante una respuesta cortada por max_tokens

OnStep = Optional[Callable[[Dict], Awaitable[None]] ]  # callback opcional para estado en vivo


@dataclass
class Message:
    """Mensaje en la conversación LLM."""
    role: str  # "system", "user", "assistant"
    content: str

    def to_dict(self) -> Dict:
        return {"role": self.role, "content": self.content}


def provider_configured(provider: Provider) -> bool:
    """¿Tiene el provider una API key usable?

    - Key con placeholder ${VAR} sin sustituir → la env var no existe → NO configurado.
    - Key vacía en un provider conocido (todos requieren key) → NO configurado.
    - Key vacía en un provider custom (p. ej. servidor local) → se acepta.
    """
    key = (provider.api_key or "").strip()
    if "${" in key:
        return False
    if not key and provider.name in KNOWN_PROVIDERS:
        return False
    return True


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

        # Orquestación: solo entran a la cadena los providers con API key usable.
        # Los demás quedan registrados como "skipped" (visibles en status()) para
        # que la cadena no gaste llamadas en providers sin credenciales.
        self.all_providers = providers or []
        self.providers = [p for p in self.all_providers if provider_configured(p)]
        self.skipped_providers = [p for p in self.all_providers if not provider_configured(p)]
        self.context_provider = context_provider
        self.prompt_loader = prompt_loader
        self.timeout_seconds = timeout_seconds
        self.app_name = app_name

        # Estado sticky (rotación dinámica) — índice sobre self.providers (configurados)
        self._active_idx = 0
        self._last_used: Optional[str] = None

        if not self.all_providers:
            raise BrainError("Se requiere al menos un provider")
        if self.skipped_providers:
            names = ", ".join(p.name for p in self.skipped_providers)
            print(f"[brain:{app_name}] providers sin API key (omitidos de la cadena): {names}")

    # ── API de bajo nivel: mensajes ya construidos ─────────────────────────
    async def complete(
        self,
        messages: List[Union[Dict, Message]],
        max_tokens: int = 600,
        temperature: float = 0.2,
        on_step: OnStep = None,
    ) -> str:
        """
        Completar una conversación ya construida (lista de dicts o Message).
        Ideal cuando la app arma sus propios messages (historial, contexto custom).
        Rota providers automáticamente si alguno falla.
        """
        return await self._call_providers_chain(messages, max_tokens, temperature, on_step)

    async def complete_refined(
        self,
        messages: List[Union[Dict, Message]],
        max_tokens: int = 600,
        temperature: float = 0.2,
        max_steps: int = 3,
        on_step: OnStep = None,
    ) -> tuple:
        """
        Pipeline multi-LLM: el primer provider redacta un borrador y los
        siguientes lo refinan en secuencia (cada paso usa un provider distinto).
        Devuelve (texto_final, trace) donde trace registra el trabajo de cada
        LLM: paso, rol (borrador/refina/final), provider, modelo, ms, si hubo
        que continuar por corte de max_tokens, y salida.
        Si un provider falla en su paso, el siguiente disponible lo cubre; el
        fallo queda registrado en el trace.
        `on_step` (opcional, async) se invoca en cada evento — start/done/error
        por intento — para exponer estado en vivo de la orquestación.
        """
        if not self.providers:
            # Mismo error que la cadena clásica
            return await self._call_providers_chain(messages, max_tokens, temperature, on_step), []

        steps = max(1, min(max_steps, len(self.providers)))
        trace: List[Dict] = []
        current: Optional[str] = None
        used: set = set()

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for step in range(steps):
                role = "borrador" if step == 0 else ("final" if step == steps - 1 else "refina")
                step_messages = messages if step == 0 else self._build_refine_messages(messages, current)

                done = False
                for provider in self.providers:
                    if provider.name in used:
                        continue
                    t0 = time.monotonic()
                    await _emit(on_step, {"step": step + 1, "role": role,
                                          "provider": provider.name, "model": provider.model,
                                          "phase": "start"})
                    try:
                        out, still_truncated, continuations = await self._call_provider_complete(
                            client, provider, step_messages, max_tokens, temperature
                        )
                        ms = int((time.monotonic() - t0) * 1000)
                        trace.append({
                            "step": step + 1, "role": role, "provider": provider.name,
                            "model": provider.model, "ms": ms, "output": out,
                            "continuations": continuations, "truncated": still_truncated,
                        })
                        await _emit(on_step, {"step": step + 1, "role": role,
                                              "provider": provider.name, "model": provider.model,
                                              "phase": "done", "ms": ms,
                                              "continuations": continuations})
                        used.add(provider.name)
                        current = out
                        self._last_used = provider.name
                        done = True
                        break
                    except Exception as e:
                        ms = int((time.monotonic() - t0) * 1000)
                        trace.append({
                            "step": step + 1, "role": role, "provider": provider.name,
                            "model": provider.model, "ms": ms,
                            "error": str(e)[:120],
                        })
                        await _emit(on_step, {"step": step + 1, "role": role,
                                              "provider": provider.name, "model": provider.model,
                                              "phase": "error", "ms": ms, "error": str(e)[:120]})
                        used.add(provider.name)
                if not done:
                    break  # sin providers libres para este paso: entregar lo que haya

        if current is None:
            errs = " | ".join(f"{t['provider']}: {t.get('error', '?')}" for t in trace)
            raise BrainError("Todos los providers fallaron · " + errs)
        return current, trace

    def _build_refine_messages(self, messages: List, draft: str) -> List[Dict]:
        """Conversación para un paso de refinado: historial original + borrador
        del LLM anterior + instrucción de mejorarlo sin romper estructura."""
        base = [
            m if isinstance(m, dict) else {"role": m.role, "content": m.content}
            for m in messages
        ]
        return base + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": (
                "Revisa tu respuesta anterior como editor experto: corrige errores, "
                "completa lo que falte y mejora claridad y estructura. Mantén el idioma "
                "del usuario y CONSERVA intactos los bloques estructurados (XML, JSON, "
                "código, etiquetas como <brain-agent>) si existen. Devuelve ÚNICAMENTE "
                "la versión final mejorada, sin comentarios sobre el borrador."
            )},
        ]

    # ── API de alto nivel: prompt por etapa + contexto ─────────────────────
    async def think(
        self,
        user_msg: str,
        context_data: Optional[Dict] = None,
        max_tokens: int = 600,
        temperature: float = 0.2,
        stage_name: str = "default",
        on_step: OnStep = None,
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
        return await self._call_providers_chain(messages, max_tokens, temperature, on_step)

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
        on_step: OnStep = None,
    ) -> str:
        """Cadena con rotación dinámica y sticky index."""
        if not self.providers:
            faltantes = ", ".join(p.name for p in self.skipped_providers) or "ninguno definido"
            raise BrainError(
                "Ningún provider tiene API key configurada "
                f"(providers sin key: {faltantes}). Define las variables de entorno "
                "(CEREBRAS_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, MISTRAL_API_KEY, "
                "OPENROUTER_API_KEY, HF_TOKEN) o edita el YAML del perfil."
            )
        n = len(self.providers)
        errors = []

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for offset in range(n):
                idx = (self._active_idx + offset) % n
                provider = self.providers[idx]
                t0 = time.monotonic()
                await _emit(on_step, {"step": 1, "role": "respuesta",
                                      "provider": provider.name, "model": provider.model,
                                      "phase": "start"})
                try:
                    response, _truncated, continuations = await self._call_provider_complete(
                        client, provider, messages, max_tokens, temperature
                    )
                    if offset:
                        print(f"[brain] rotación dinámica → {provider.name} ({provider.model})")
                    self._active_idx = idx
                    self._last_used = provider.name
                    await _emit(on_step, {"step": 1, "role": "respuesta",
                                          "provider": provider.name, "model": provider.model,
                                          "phase": "done",
                                          "ms": int((time.monotonic() - t0) * 1000),
                                          "continuations": continuations})
                    return response
                except Exception as e:
                    body = ""
                    resp = getattr(e, "response", None)
                    if resp is not None:
                        try:
                            body = resp.text[:120]
                        except Exception:
                            body = ""
                    msg = f"{str(e)[:80]} {body}".strip()
                    errors.append(f"{provider.name}: {msg}")
                    await _emit(on_step, {"step": 1, "role": "respuesta",
                                          "provider": provider.name, "model": provider.model,
                                          "phase": "error",
                                          "ms": int((time.monotonic() - t0) * 1000),
                                          "error": msg[:120]})
                    continue

        raise BrainError("Todos los providers fallaron · " + " | ".join(errors))

    async def _call_provider(
        self,
        client: httpx.AsyncClient,
        provider: Provider,
        messages: List,
        max_tokens: int,
        temperature: float,
    ) -> tuple:
        headers = provider.get_headers()
        payload = provider.get_payload(messages, max_tokens, temperature)

        r = await client.post(provider.url, headers=headers, json=payload)
        r.raise_for_status()

        content, truncated = provider.parse_response(r.json())
        if not content.strip():
            raise ValueError("respuesta vacía (sin content)")
        return content, truncated

    async def _call_provider_complete(
        self,
        client: httpx.AsyncClient,
        provider: Provider,
        messages: List,
        max_tokens: int,
        temperature: float,
    ) -> tuple:
        """Llama al provider y, si la respuesta quedó cortada por max_tokens
        (finish_reason == "length"), la continúa automáticamente con el MISMO
        provider hasta completarla o agotar MAX_CONTINUATIONS intentos.
        Garantiza una respuesta íntegra sin importar dónde cada LLM decida
        cortar su salida. Devuelve (texto_completo, sigue_truncado, n_continuaciones)."""
        content, truncated = await self._call_provider(client, provider, messages, max_tokens, temperature)
        full = content
        convo = [m if isinstance(m, dict) else {"role": m.role, "content": m.content} for m in messages]
        attempts = 0
        while truncated and attempts < MAX_CONTINUATIONS:
            attempts += 1
            convo = convo + [
                {"role": "assistant", "content": full},
                {"role": "user", "content": (
                    "Tu respuesta anterior quedó cortada por límite de longitud. "
                    "Continúa EXACTAMENTE donde quedaste, sin repetir nada de lo ya "
                    "escrito, sin reintroducciones ni comentarios sobre el corte."
                )},
            ]
            content, truncated = await self._call_provider(client, provider, convo, max_tokens, temperature)
            full += content
        return full, truncated, attempts

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
        """Estado actual: provider activo, cadena configurada y omitidos."""
        active = self._last_used or (self.providers[self._active_idx].name if self.providers else None)
        return {
            "app": self.app_name,
            "enabled": bool(self.providers),
            "active": active,
            "count": len(self.providers),
            "providers": [
                {"order": i, "name": p.name, "model": p.model, "configured": True}
                for i, p in enumerate(self.providers)
            ],
            "skipped": [
                {"name": p.name, "model": p.model, "reason": "sin API key"}
                for p in self.skipped_providers
            ],
        }


async def _emit(on_step: OnStep, event: Dict) -> None:
    """Dispara el callback de estado en vivo sin romper la orquestación si falla."""
    if on_step is None:
        return
    try:
        await on_step(event)
    except Exception:
        pass  # el monitor es best-effort; nunca debe tumbar una respuesta


def extract_json(text: str) -> Optional[Dict]:
    """Extraer el primer objeto JSON de un texto (o None)."""
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return None
