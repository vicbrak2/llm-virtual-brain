"""Tests de humo (sin red): construcción, config, parsing."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from brain import (
    Brain,
    BrainConfig,
    ProviderConfig,
    provider_from_dict,
    extract_json,
    DictPromptLoader,
)
from brain.config import _substitute_env_vars


def test_provider_from_dict_jarvis_style():
    """Acepta los dicts estilo Jarvis (key/headers como alias)."""
    p = provider_from_dict({
        "name": "openrouter",
        "key": "sk-test",
        "headers": {"X-Title": "Test"},
    })
    assert p.api_key == "sk-test"
    assert p.extra_headers["X-Title"] == "Test"
    assert "openrouter.ai" in p.url  # default aplicado
    assert p.model  # default aplicado


def test_provider_known_defaults_and_overrides():
    p = provider_from_dict({"name": "cerebras", "api_key": "k", "model": "custom-model"})
    assert p.token_param == "max_completion_tokens"
    assert p.extra_body == {"reasoning_effort": "low"}
    assert p.model == "custom-model"  # override respetado


def test_brain_from_components():
    p = provider_from_dict({"name": "groq", "api_key": "k"})
    b = Brain(providers=[p], prompt_loader=DictPromptLoader({"default": "hola"}))
    s = b.status()
    assert s["enabled"] and s["count"] == 1 and s["providers"][0]["name"] == "groq"


def test_brain_from_config():
    cfg = BrainConfig(
        app_name="test_app",
        providers=[ProviderConfig(name="groq", api_key="k")],
    )
    b = Brain(cfg)
    assert b.app_name == "test_app"
    assert b.providers[0].name == "groq"
    assert "api.groq.com" in b.providers[0].url


def test_extract_json():
    assert extract_json('bla {"a": 1} bla') == {"a": 1}
    assert extract_json("sin json") is None


def test_providers_sin_key_se_omiten_de_la_cadena():
    """Providers con key vacía o placeholder ${VAR} quedan fuera de la cadena."""
    ps = [
        provider_from_dict({"name": "groq", "api_key": "gsk_real"}),
        provider_from_dict({"name": "cerebras", "api_key": "${CEREBRAS_API_KEY}"}),  # sin sustituir
        provider_from_dict({"name": "hf", "api_key": ""}),  # vacía
    ]
    b = Brain(providers=ps)
    assert [p.name for p in b.providers] == ["groq"]
    assert sorted(p.name for p in b.skipped_providers) == ["cerebras", "hf"]
    s = b.status()
    assert s["count"] == 1
    assert {e["name"] for e in s["skipped"]} == {"cerebras", "hf"}


def test_provider_custom_sin_key_se_acepta():
    """Un provider custom (p. ej. servidor local) puede no tener API key."""
    p = provider_from_dict({"name": "ollama_local", "url": "http://localhost:11434/v1/chat/completions", "model": "llama3"})
    b = Brain(providers=[p])
    assert [x.name for x in b.providers] == ["ollama_local"]


def test_env_substitution_with_default():
    os.environ["BRAIN_TEST_VAR"] = "valor"
    data = {"a": "${BRAIN_TEST_VAR}", "b": "${BRAIN_NO_EXISTE:defecto}", "c": "${BRAIN_NO_EXISTE_2}"}
    out = _substitute_env_vars(data)
    assert out["a"] == "valor"
    assert out["b"] == "defecto"
    assert out["c"] == "${BRAIN_NO_EXISTE_2}"  # sin default → intacto


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"OK   {name}")
    print("Todos los tests de humo pasaron.")
