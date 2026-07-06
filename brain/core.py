"""Core Brain: Orquestador de LLM multi-proveedor con rotación dinámica."""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Optional, Dict, List
import httpx

from .errors import BrainError, ProviderError
from .providers import Provider
from .context import ContextProvider
from .prompts import PromptLoader


@dataclass
class Message:
    """Mensaje en la cadena LLM."""
    role: str  # "system", "user", "assistant"
    content: str

    def to_dict(self) -> Dict:
        return {"role": self.role, "content": self.content}


class Brain:
    """
    Orquestador de LLM agnóstico y reutilizable.

    Características:
    - Rotación dinámica entre providers (si uno falla, intenta el siguiente).
    - Sticky: recuerda qué provider respondió bien para no reintentar caídos.
    - Multi-etapa: puede encadenar formatter → analyzer → custom.
    - Contexto pluggable: Sheets, SQL, vault, custom.
    - Agnóstico: funciona para task manager, contraseñas, precios, etc.
    """

    def __init__(
        self,
        providers: List[Provider],
        context_provider: Optional[ContextProvider] = None,
        prompt_loader: Optional[PromptLoader] = None,
        timeout_seconds: int = 30,
        app_name: str = "brain_app"
    ):
        """
        Args:
            providers: Lista de Provider en orden de preferencia.
            context_provider: Cargador de contexto (opcional).
            prompt_loader: Cargador de prompts (opcional).
            timeout_seconds: Timeout HTTP para requests a providers.
            app_name: Nombre de la app (para logging).
        """
        self.providers = providers
        self.context_provider = context_provider
        self.prompt_loader = prompt_loader
        self.timeout_seconds = timeout_seconds
        self.app_name = app_name

        # Estado sticky (rotación dinámica)
        self._active_idx = 0
        self._last_used = None

        if not self.providers:
            raise BrainError("At least one provider is required")

    async def think(
        self,
        user_msg: str,
        context_data: Optional[Dict] = None,
        max_tokens: int = 600,
        temperature: float = 0.2,
        stage_name: str = "default"
    ) -> str:
        """
        Piensa (consulta LLM) respecto a un mensaje del usuario.

        Args:
            user_msg: Mensaje del usuario.
            context_data: Datos de contexto (tareas, precios, etc.).
            max_tokens: Límite de tokens en la respuesta.
            temperature: Creatividad (0.0 = determinista).
            stage_name: Nombre del prompt/etapa a usar.

        Returns:
            str: Respuesta del LLM.

        Raises:
            BrainError: Si todos los providers fallan.
        """
        # 1. Cargar prompt
        system_prompt = ""
        if self.prompt_loader:
            system_prompt = self.prompt_loader.get(stage_name)

        # 2. Enriquecer contexto
        enriched = context_data or {}
        if self.context_provider:
            try:
                enriched = await self.context_provider.enrich(user_msg, enriched)
            except Exception as e:
                print(f"[brain] context enrichment failed: {e}")
                # Continuar sin contexto si falla

        # 3. Construir messages
        messages = self._build_messages(system_prompt, user_msg, enriched)

        # 4. Llamar a providers en cadena
        return await self._call_providers_chain(messages, max_tokens, temperature)

    async def think_json(
        self,
        user_msg: str,
        context_data: Optional[Dict] = None,
        max_tokens: int = 900,
        temperature: float = 0.0,
        stage_name: str = "default"
    ) -> Dict:
        """Igual que think() pero parseando JSON de la respuesta."""
        raw = await self.think(user_msg, context_data, max_tokens, temperature, stage_name)
        return self._extract_json(raw)

    async def think_multi_stage(
        self,
        user_msg: str,
        stages: List[str],
        context_data: Optional[Dict] = None
    ) -> str:
        """
        Ejecuta múltiples etapas secuencialmente.

        Ejemplo: formatter → analyzer
        La salida de formatter se usa como input del analyzer.
        """
        result = user_msg
        for stage in stages:
            result = await self.think(result, context_data, stage_name=stage)
        return result

    async def _call_providers_chain(
        self,
        messages: List[Message],
        max_tokens: int,
        temperature: float
    ) -> str:
        """Intenta providers en cadena con rotación dinámica y sticky."""
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

                    # Log si rotó
                    if offset > 0:
                        print(f"[brain] rotación dinám → {provider.name} ({provider.model})")

                    # Sticky: recordar que este provider respondió
                    self._active_idx = idx
                    self._last_used = provider.name

                    return response

                except Exception as e:
                    error_msg = str(e)[:100]
                    errors.append(f"{provider.name}: {error_msg}")
                    print(f"[brain] {provider.name} failed, trying next: {error_msg}")
                    continue

        error_summary = " | ".join(errors)
        raise BrainError(f"Todos los providers fallaron: {error_summary}")

    async def _call_provider(
        self,
        client: httpx.AsyncClient,
        provider: Provider,
        messages: List[Message],
        max_tokens: int,
        temperature: float
    ) -> str:
        """Llama a un provider individual."""
        headers = provider.get_headers()
        payload = provider.get_payload(messages, max_tokens, temperature)

        r = await client.post(provider.url, headers=headers, json=payload)
        r.raise_for_status()

        response_json = r.json()
        content = provider.parse_response(response_json)

        if not content.strip():
            raise ValueError("Respuesta vacía del LLM")

        return content

    def _build_messages(
        self,
        system_prompt: str,
        user_msg: str,
        context: Dict
    ) -> List[Message]:
        """Construir lista de messages con sistema + contexto + usuario."""
        messages = []

        # Sistema
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))

        # Contexto como mensaje de sistema adicional (evita confusión)
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            messages.append(Message(
                role="system",
                content=f"CONTEXTO:\n{context_str}"
            ))

        # Usuario
        messages.append(Message(role="user", content=user_msg))

        return messages

    def _extract_json(self, text: str) -> Dict:
        """Extraer primer JSON válido de un texto."""
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        raise BrainError(f"No valid JSON found in response: {text[:200]}")

    def status(self) -> Dict:
        """Estado actual de Brain."""
        return {
            "app": self.app_name,
            "active": self._last_used or self.providers[self._active_idx].name,
            "providers_count": len(self.providers),
            "providers": [
                {
                    "order": i,
                    "name": p.name,
                    "model": p.model
                }
                for i, p in enumerate(self.providers)
            ]
        }
