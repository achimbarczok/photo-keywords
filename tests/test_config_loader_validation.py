"""Unit-Tests für ConfigLoader Validierungs-Parsing.

Anforderungen: 5.1, 5.2, 5.3
"""

from __future__ import annotations

import yaml

from lightroom_ollama_keywords.config_loader import ConfigLoader
from lightroom_ollama_keywords.models import ValidierungsConfig


class TestConfigLoaderValidationParsing:
    """Unit-Tests für das Parsen des optionalen validation-Abschnitts."""

    def test_yaml_without_validation_section_uses_defaults(self, tmp_path):
        """YAML ohne validation-Abschnitt → ValidierungsConfig mit Standardwerten."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {"catalog_path": "/photos/catalog.lrcat", "model_name": "llava"},
                default_flow_style=False,
            ),
            encoding="utf-8",
        )

        loader = ConfigLoader()
        config = loader.load(str(config_file))

        defaults = ValidierungsConfig()
        assert config.validierung.max_retries == defaults.max_retries
        assert config.validierung.wortanzahl_schwellenwert == defaults.wortanzahl_schwellenwert
        assert config.validierung.einzeleintrag_schwellenwert == defaults.einzeleintrag_schwellenwert
        assert config.validierung.retry_prompt == defaults.retry_prompt

    def test_yaml_with_partial_validation_section_fills_defaults(self, tmp_path):
        """YAML mit teilweisem validation-Abschnitt → Standardwerte für fehlende Felder."""
        config_data = {
            "catalog_path": "/photos/catalog.lrcat",
            "model_name": "llava",
            "validation": {
                "max_retries": 5,
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(config_data, default_flow_style=False),
            encoding="utf-8",
        )

        loader = ConfigLoader()
        config = loader.load(str(config_file))

        defaults = ValidierungsConfig()
        assert config.validierung.max_retries == 5
        assert config.validierung.wortanzahl_schwellenwert == defaults.wortanzahl_schwellenwert
        assert config.validierung.einzeleintrag_schwellenwert == defaults.einzeleintrag_schwellenwert
        assert config.validierung.retry_prompt == defaults.retry_prompt

    def test_yaml_with_complete_validation_section_loads_all(self, tmp_path):
        """YAML mit vollständigem validation-Abschnitt → alle Werte übernommen."""
        custom_prompt = "Only keywords, nothing else."
        config_data = {
            "catalog_path": "/photos/catalog.lrcat",
            "model_name": "llava",
            "validation": {
                "max_retries": 3,
                "word_count_threshold": 5.0,
                "single_entry_threshold": 6,
                "retry_prompt": custom_prompt,
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(config_data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        loader = ConfigLoader()
        config = loader.load(str(config_file))

        assert config.validierung.max_retries == 3
        assert config.validierung.wortanzahl_schwellenwert == 5.0
        assert config.validierung.einzeleintrag_schwellenwert == 6
        assert config.validierung.retry_prompt == custom_prompt
