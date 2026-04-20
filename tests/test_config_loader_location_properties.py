"""Property-basierte Tests für ConfigLoader Location-Konfiguration.

**Validates: Requirements 7.1, 7.2, 7.3**
"""

from __future__ import annotations

import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from lightroom_ollama_keywords.config_loader import ConfigLoader


class TestProperty10ConfigLocationParsing:
    """Property 10: Config-Location-Parsing.

    **Validates: Requirements 7.1, 7.2, 7.3**

    Für alle gültigen Boolean-Werte für `enabled` soll das Erstellen einer
    YAML-Konfiguration mit `location.enabled` und anschließende Parsen über
    ConfigLoader ein Config-Objekt mit `standort.enabled` gleich dem
    ursprünglichen Wert ergeben. Wenn der `location`-Abschnitt fehlt, soll
    `standort.enabled` False sein.
    """

    @given(enabled=st.booleans())
    @settings(max_examples=100)
    def test_location_enabled_round_trip(
        self,
        enabled: bool,
        tmp_path_factory,
    ) -> None:
        """Creating a YAML config with location.enabled and parsing via
        ConfigLoader should produce a Config with standort.enabled equal
        to the original value."""
        config_data = {
            "catalog_path": "/photos/catalog.lrcat",
            "model_name": "llava",
            "location": {
                "enabled": enabled,
            },
        }

        tmp_dir = tmp_path_factory.mktemp("cfg")
        config_file = tmp_dir / "config.yaml"
        config_file.write_text(
            yaml.dump(config_data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        loader = ConfigLoader()
        loaded = loader.load(str(config_file))

        assert loaded.standort.enabled == enabled

    def test_missing_location_section_defaults_to_false(
        self,
        tmp_path,
    ) -> None:
        """When the location section is missing, standort.enabled should
        be False."""
        config_data = {
            "catalog_path": "/photos/catalog.lrcat",
            "model_name": "llava",
        }

        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(config_data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        loader = ConfigLoader()
        loaded = loader.load(str(config_file))

        assert loaded.standort.enabled is False
