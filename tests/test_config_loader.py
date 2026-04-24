"""Property-basierte Tests für den ConfigLoader."""

from __future__ import annotations

import os
from dataclasses import asdict

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from photo_keywords.config_loader import ConfigLoader
from photo_keywords.errors import ConfigError
from photo_keywords.models import Config


# --- Hypothesis strategies for valid Config fields ---

# Non-empty printable strings without YAML-special characters that could break parsing
_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd"), whitelist_characters="_/."),
    min_size=1,
    max_size=60,
).filter(lambda s: s.strip() == s and not s.startswith("#"))

_endpoint = st.builds(
    lambda port: f"http://localhost:{port}",
    st.integers(min_value=1024, max_value=65535),
)

_batch_size = st.integers(min_value=1, max_value=10000)

_exiftool_path = st.one_of(st.none(), _safe_text)

_benchmark_models = st.lists(_safe_text, min_size=0, max_size=5)

_config_strategy = st.builds(
    Config,
    catalog_path=_safe_text,
    ollama_endpoint=_endpoint,
    model_name=_safe_text,
    batch_size=_batch_size,
    prompt_template=_safe_text,
    tracking_db_path=_safe_text,
    log_file_path=_safe_text,
    exiftool_path=_exiftool_path,
    benchmark_models=_benchmark_models,
    benchmark_output_csv=_safe_text,
)


class TestConfigRoundTrip:
    """Property 7: Konfigurations-Round-Trip.

    **Validates: Requirements 6.1**
    """

    @given(config=_config_strategy)
    @settings(max_examples=100)
    def test_yaml_round_trip(self, config: Config, tmp_path_factory):
        """For all valid Config objects, serializing to YAML and deserializing
        should produce an equivalent Config object."""
        # Serialize to YAML
        tmp_dir = tmp_path_factory.mktemp("cfg")
        config_file = tmp_dir / "config.yaml"
        config_file.write_text(yaml.dump(asdict(config), default_flow_style=False), encoding="utf-8")

        # Deserialize via ConfigLoader
        loader = ConfigLoader()
        loaded = loader.load(str(config_file))

        # Assert all fields are equal
        assert loaded.catalog_path == config.catalog_path
        assert loaded.ollama_endpoint == config.ollama_endpoint
        assert loaded.model_name == config.model_name
        assert loaded.batch_size == config.batch_size
        assert loaded.prompt_template == config.prompt_template
        assert loaded.tracking_db_path == config.tracking_db_path
        assert loaded.log_file_path == config.log_file_path
        assert loaded.exiftool_path == config.exiftool_path
        assert loaded.benchmark_models == config.benchmark_models
        assert loaded.benchmark_output_csv == config.benchmark_output_csv


# --- Strategy for a valid config dict (all fields present) ---

_valid_config_dict = st.fixed_dictionaries({
    "catalog_path": _safe_text,
    "model_name": _safe_text,
    "ollama_endpoint": _endpoint,
    "batch_size": _batch_size,
    "prompt_template": _safe_text,
    "tracking_db_path": _safe_text,
    "log_file_path": _safe_text,
    "exiftool_path": _safe_text,
    "benchmark_models": _benchmark_models,
    "benchmark_output_csv": _safe_text,
})

_required_param = st.sampled_from(["catalog_path", "model_name"])


class TestMissingRequiredParameter:
    """Property 8: Validierung fehlender Pflichtparameter.

    **Validates: Requirements 6.2**
    """

    @given(config_dict=_valid_config_dict, missing=_required_param)
    @settings(max_examples=100)
    def test_missing_required_param_raises_config_error(
        self, config_dict: dict, missing: str, tmp_path_factory
    ):
        """For all configurations with exactly one missing required parameter,
        ConfigLoader should raise ConfigError with the parameter name in the message."""
        # Remove exactly one required parameter
        partial = {k: v for k, v in config_dict.items() if k != missing}

        # Write partial config to YAML
        tmp_dir = tmp_path_factory.mktemp("cfg")
        config_file = tmp_dir / "config.yaml"
        config_file.write_text(
            yaml.dump(partial, default_flow_style=False), encoding="utf-8"
        )

        # Load should raise ConfigError with the missing param name
        loader = ConfigLoader()
        with pytest.raises(ConfigError, match=missing):
            loader.load(str(config_file))


class TestConfigLoaderDefaults:
    """Unit-Tests für korrekte Standardwerte bei fehlenden optionalen Parametern.

    Anforderungen: 6.3
    """

    def test_defaults_when_optional_params_missing(self, tmp_path):
        """A YAML with only catalog_path and model_name should produce a Config
        with all default values filled in correctly."""
        config_file = tmp_path / "minimal.yaml"
        config_file.write_text(
            yaml.dump(
                {"catalog_path": "/photos/catalog.lrcat", "model_name": "llava"},
                default_flow_style=False,
            ),
            encoding="utf-8",
        )

        loader = ConfigLoader()
        config = loader.load(str(config_file))

        assert config.catalog_path == "/photos/catalog.lrcat"
        assert config.model_name == "llava"
        assert config.ollama_endpoint == "http://localhost:11434"
        assert config.batch_size == 50
        assert config.prompt_template.startswith("Describe this image")
        assert config.tracking_db_path == "./tracking.db"
        assert config.log_file_path == "./keyword_generator.log"
        assert config.exiftool_path is None
        assert config.benchmark_models == []
        assert config.benchmark_output_csv == "./benchmark_results.csv"


class TestConfigLoaderMissingFile:
    """Unit-Tests für ConfigError bei fehlender YAML-Datei.

    Anforderungen: 6.2
    """

    def test_nonexistent_yaml_raises_config_error(self):
        """Passing a path to a non-existent file should raise ConfigError."""
        loader = ConfigLoader()
        with pytest.raises(ConfigError):
            loader.load("/does/not/exist/config.yaml")


class TestConfigLoaderClassification:
    """Unit-Tests für den erweiterten ConfigLoader mit Klassifikations-Konfiguration.

    Anforderungen: 4.3, 3.3, 4.5
    """

    def test_classification_missing_yields_none(self, tmp_path):
        """Classification fehlt → klassifikation = None (Anforderung 4.3)."""
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

        assert config.klassifikation is None

    def test_document_category_with_alternative_model(self, tmp_path):
        """Dokument-Kategorie mit alternativem OCR-Modell ladbar (Anforderung 3.3)."""
        config_data = {
            "catalog_path": "/photos/catalog.lrcat",
            "model_name": "llava",
            "classification": {
                "model": "gemma4:e2b",
                "prompt": "Classify this photo",
                "categories": {
                    "Dokument": {
                        "prompt": "Analyze this document for OCR keywords.",
                        "model": "glm-ocr",
                    },
                    "Sonstiges": {
                        "prompt": "Describe this image with keywords.",
                    },
                },
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(config_data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        loader = ConfigLoader()
        config = loader.load(str(config_file))

        assert config.klassifikation is not None
        from photo_keywords.models import FotoKategorie

        dokument_config = config.klassifikation.kategorien[FotoKategorie.DOKUMENT]
        assert dokument_config.modell == "glm-ocr"
        assert "OCR" in dokument_config.prompt or "document" in dokument_config.prompt.lower()

    def test_classification_prompt_configurable(self, tmp_path):
        """Klassifikations-Prompt als konfigurierbarer Wert (Anforderung 4.5)."""
        custom_prompt = "Bitte klassifiziere dieses Foto in eine Kategorie."
        config_data = {
            "catalog_path": "/photos/catalog.lrcat",
            "model_name": "llava",
            "classification": {
                "model": "gemma4:e2b",
                "prompt": custom_prompt,
                "categories": {
                    "Landschaft": {
                        "prompt": "Landscape keywords please.",
                    },
                },
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(config_data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        loader = ConfigLoader()
        config = loader.load(str(config_file))

        assert config.klassifikation is not None
        assert config.klassifikation.prompt == custom_prompt
