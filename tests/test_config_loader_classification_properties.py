"""Property-basierte Tests für den ConfigLoader — Klassifikations-Konfiguration."""

from __future__ import annotations

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from lightroom_ollama_keywords.config_loader import ConfigLoader
from lightroom_ollama_keywords.errors import ConfigError
from lightroom_ollama_keywords.models import (
    FotoKategorie,
    KategorieConfig,
    KlassifikationsConfig,
)


# --- Hypothesis strategies ---

# Safe text that won't break YAML parsing
_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Pd"), whitelist_characters="_/. "
    ),
    min_size=1,
    max_size=60,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0 and not s.startswith("#"))

_foto_kategorie = st.sampled_from(list(FotoKategorie))

_kategorie_config = st.builds(
    KategorieConfig,
    prompt=_safe_text,
    modell=st.one_of(st.none(), _safe_text),
)

# At least one category, up to all 8
_kategorien_dict = st.dictionaries(
    keys=_foto_kategorie,
    values=_kategorie_config,
    min_size=1,
    max_size=len(FotoKategorie),
)

_klassifikations_config = st.builds(
    KlassifikationsConfig,
    modell=_safe_text,
    prompt=_safe_text,
    kategorien=_kategorien_dict,
)


def _serialize_config_to_yaml(klass_config: KlassifikationsConfig) -> dict:
    """Serialize a KlassifikationsConfig to the YAML dict format expected by ConfigLoader."""
    categories = {}
    for kategorie, cat_config in klass_config.kategorien.items():
        entry: dict = {"prompt": cat_config.prompt}
        if cat_config.modell is not None:
            entry["model"] = cat_config.modell
        categories[kategorie.value] = entry

    return {
        "model": klass_config.modell,
        "prompt": klass_config.prompt,
        "categories": categories,
    }


class TestClassificationConfigRoundTrip:
    """Property 4: Klassifikations-Konfigurations-Round-Trip.

    **Validates: Requirements 4.1, 4.2, 4.5**
    """

    @given(klass_config=_klassifikations_config)
    @settings(max_examples=100)
    def test_classification_config_round_trip(
        self, klass_config: KlassifikationsConfig, tmp_path_factory
    ):
        """For all valid KlassifikationsConfig objects: serializing as YAML and
        loading via ConfigLoader yields an equivalent config."""
        # Build a full config dict with required fields + classification
        config_dict = {
            "catalog_path": "/test/catalog.lrcat",
            "model_name": "test-model",
            "classification": _serialize_config_to_yaml(klass_config),
        }

        tmp_dir = tmp_path_factory.mktemp("cfg")
        config_file = tmp_dir / "config.yaml"
        config_file.write_text(
            yaml.dump(config_dict, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        loader = ConfigLoader()
        loaded = loader.load(str(config_file))

        # Classification should not be None
        assert loaded.klassifikation is not None
        loaded_klass = loaded.klassifikation

        # Model and prompt match
        assert loaded_klass.modell == klass_config.modell
        assert loaded_klass.prompt == klass_config.prompt

        # Same categories
        assert set(loaded_klass.kategorien.keys()) == set(klass_config.kategorien.keys())

        for kategorie, expected_cat in klass_config.kategorien.items():
            loaded_cat = loaded_klass.kategorien[kategorie]
            assert loaded_cat.prompt == expected_cat.prompt
            assert loaded_cat.modell == expected_cat.modell


class TestMissingCategoryPromptValidation:
    """Property 5: Validierung fehlender Kategorie-Prompts.

    **Validates: Requirements 4.4**
    """

    @given(
        valid_categories=_kategorien_dict,
        broken_kategorie=_foto_kategorie,
    )
    @settings(max_examples=100)
    def test_missing_prompt_raises_config_error(
        self,
        valid_categories: dict[FotoKategorie, KategorieConfig],
        broken_kategorie: FotoKategorie,
        tmp_path_factory,
    ):
        """For all configs with at least one category without a prompt:
        ConfigLoader raises ConfigError."""
        # Build categories dict — ensure at least one has no prompt
        categories_yaml: dict = {}
        for kategorie, cat_config in valid_categories.items():
            entry: dict = {"prompt": cat_config.prompt}
            if cat_config.modell is not None:
                entry["model"] = cat_config.modell
            categories_yaml[kategorie.value] = entry

        # Add or overwrite one category with missing prompt
        categories_yaml[broken_kategorie.value] = {}

        config_dict = {
            "catalog_path": "/test/catalog.lrcat",
            "model_name": "test-model",
            "classification": {
                "model": "gemma4:e2b",
                "prompt": "Classify this photo",
                "categories": categories_yaml,
            },
        }

        tmp_dir = tmp_path_factory.mktemp("cfg")
        config_file = tmp_dir / "config.yaml"
        config_file.write_text(
            yaml.dump(config_dict, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        loader = ConfigLoader()
        with pytest.raises(ConfigError):
            loader.load(str(config_file))
