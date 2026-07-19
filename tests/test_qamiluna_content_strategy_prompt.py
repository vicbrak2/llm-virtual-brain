from brain.config import load_config_from_yaml
from brain.prompts import loader_from_dict


def test_qamiluna_team_prompt_includes_phase_1_content_strategy():
    config = load_config_from_yaml("profiles/qamiluna_team.yaml")
    loader = loader_from_dict({"type": config.prompts.type, **config.prompts.config})
    prompt = loader.get("chat")

    required_phrases = [
        "Asistente de Contenido",
        "Dieta editorial objetivo",
        "30% educacion",
        "25% casos reales",
        "20% relatos de marca",
        "15% humor/identidad",
        "10% venta directa",
        "MusaQS",
        "CTA claro",
        "borrador para revisar",
        "No inventes precios",
        "Hook de 3 segundos",
        "Lista prohibida",
        "enseñar una idea concreta",
        "Borrador para revisar",
        "Historias destacadas",
        "Valores",
        "Agenda",
        "Testimonios",
    ]

    for phrase in required_phrases:
        assert phrase in prompt
