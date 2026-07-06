"""Cargadores de prompts (YAML, JSON, en-memoria)."""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional


class PromptLoader(ABC):
    """Base para cargadores de prompts."""

    @abstractmethod
    def get(self, stage_name: str) -> str:
        """Obtener prompt por nombre/etapa."""
        pass

    @abstractmethod
    def set(self, stage_name: str, prompt_text: str) -> None:
        """Guardar/actualizar prompt en runtime."""
        pass


class DictPromptLoader(PromptLoader):
    """Prompts en-memoria (diccionario Python)."""

    def __init__(self, prompts_dict: Dict[str, str]):
        """
        Args:
            prompts_dict: {stage_name: prompt_text, ...}
        """
        self.prompts = prompts_dict

    def get(self, stage_name: str) -> str:
        return self.prompts.get(stage_name, "")

    def set(self, stage_name: str, prompt_text: str) -> None:
        self.prompts[stage_name] = prompt_text


class JSONPromptLoader(PromptLoader):
    """Cargador de prompts desde archivo JSON."""

    def __init__(self, json_path: str):
        """
        Args:
            json_path: Path al archivo JSON.
                       Formato: {"prompts": {"stage1": "...", "stage2": "..."}}
        """
        self.json_path = Path(json_path)
        self._load()

    def _load(self):
        try:
            with open(self.json_path) as f:
                data = json.load(f)
                self.prompts = data.get("prompts", {})
        except Exception as e:
            raise ImportError(f"JSONPromptLoader error: {e}")

    def get(self, stage_name: str) -> str:
        return self.prompts.get(stage_name, "")

    def set(self, stage_name: str, prompt_text: str) -> None:
        self.prompts[stage_name] = prompt_text
        # Opcionalmente guardar de vuelta al archivo
        self._save()

    def _save(self):
        """Guardar prompts de vuelta al archivo JSON."""
        try:
            with open(self.json_path, "w") as f:
                json.dump({"prompts": self.prompts}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[prompt] JSON save error: {e}")


class YAMLPromptLoader(PromptLoader):
    """Cargador de prompts desde archivo YAML."""

    def __init__(self, yaml_path: str):
        """
        Args:
            yaml_path: Path al archivo YAML.
                       Formato:
                       prompts:
                         stage1: |
                           Multi-line
                           prompt...
                         stage2: Single line prompt
        """
        self.yaml_path = Path(yaml_path)
        try:
            import yaml
            self.yaml = yaml
        except ImportError:
            raise ImportError("YAMLPromptLoader requires PyYAML: pip install pyyaml")
        self._load()

    def _load(self):
        try:
            with open(self.yaml_path) as f:
                data = self.yaml.safe_load(f)
                self.prompts = data.get("prompts", {}) if data else {}
        except Exception as e:
            raise ImportError(f"YAMLPromptLoader error: {e}")

    def get(self, stage_name: str) -> str:
        return self.prompts.get(stage_name, "")

    def set(self, stage_name: str, prompt_text: str) -> None:
        self.prompts[stage_name] = prompt_text
        self._save()

    def _save(self):
        """Guardar prompts de vuelta al archivo YAML."""
        try:
            with open(self.yaml_path, "w") as f:
                self.yaml.dump(
                    {"prompts": self.prompts},
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False
                )
        except Exception as e:
            print(f"[prompt] YAML save error: {e}")


def loader_from_dict(config: Dict) -> PromptLoader:
    """Construir PromptLoader desde dict de config."""
    loader_type = config.get("type", "dict").lower()

    if loader_type == "yaml":
        return YAMLPromptLoader(config.get("path", "prompts.yaml"))
    elif loader_type == "json":
        return JSONPromptLoader(config.get("path", "prompts.json"))
    elif loader_type == "dict":
        return DictPromptLoader(config.get("prompts", {}))
    else:
        # Default: dict vacío
        return DictPromptLoader({})
