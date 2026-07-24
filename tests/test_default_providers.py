from brain.config import DEFAULT_PROVIDERS, load_config_from_yaml


def test_default_providers_use_budget_upgrade_chain():
    assert [p["name"] for p in DEFAULT_PROVIDERS] == [
        "groq",
        "openrouter",
        "cerebras",
        "hf",
    ]
    assert DEFAULT_PROVIDERS[0]["model"] == "openai/gpt-oss-120b"
    assert DEFAULT_PROVIDERS[1]["model"] == "qwen/qwen3-30b-a3b-instruct-2507"
    assert DEFAULT_PROVIDERS[2]["model"] == "gpt-oss-120b"


def test_qamiluna_team_inherits_default_providers():
    config = load_config_from_yaml("profiles/qamiluna_team.yaml")

    assert [p.name for p in config.providers] == [
        "groq",
        "openrouter",
        "cerebras",
        "hf",
    ]
    assert config.providers[1].model == "qwen/qwen3-30b-a3b-instruct-2507"
    assert config.providers[2].model == "gpt-oss-120b"
