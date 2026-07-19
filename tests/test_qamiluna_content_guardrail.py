from brain.server import _is_qamiluna_content_request, _sanitize_qamiluna_content_reply


def test_qamiluna_content_guardrail_detects_creative_requests():
    assert _is_qamiluna_content_request(
        "qamiluna_team",
        "Dame 3 captions para un post educativo del martes",
    )
    assert _is_qamiluna_content_request(
        "qamiluna_team",
        "Necesito un guion para Reel sobre maquillaje de novia",
    )


def test_qamiluna_content_guardrail_ignores_other_profiles_and_ops_questions():
    assert not _is_qamiluna_content_request(
        "general",
        "Dame 3 captions para un post educativo",
    )
    assert not _is_qamiluna_content_request(
        "qamiluna_team",
        "Cuanto sale el traslado a Rancagua?",
    )


def test_qamiluna_content_sanitizer_removes_generic_beauty_cliches():
    raw = (
        "Seras una princesa y vas a brillar en tu gran dia con un look unico "
        "y perfecto. No te pierdas la oportunidad de lucir hermosa en tu dia especial."
    )

    cleaned = _sanitize_qamiluna_content_reply(raw).lower()

    forbidden = [
        "princesa",
        "brillar",
        "gran dia",
        "look unico",
        "perfecto",
        "no te pierdas la oportunidad",
        "lucir hermosa",
        "dia especial",
    ]
    for phrase in forbidden:
        assert phrase not in cleaned
