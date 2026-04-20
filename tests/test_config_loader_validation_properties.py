"""Property-basierte Tests für ConfigLoader Validierungs-Konfiguration.

**Validates: Requirements 5.1**
"""

from __future__ import annotations

import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from lightroom_ollama_keywords.config_loader import ConfigLoader
from lightroom_ollama_keywords.models import ValidierungsConfig


# --- Hypothesis strategies for validation config fields ---

_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Pd"), whitelist_characters=" _/.,!"
    ),
    min_size=1,
    max_size=80,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0 and not s.startswith("#"))

_max_retries = st.integers(min_value=0, max_value=10)
_word_count_threshold = st.floats(min_value=1.0, max_value=20.0, allow_nan=False, allow_infinity=False)
_single_entry_threshold = st.integers(min_value=1, max_value=50)
_retry_prompt = _safe_text


class TestValidationConfigRoundTrip:
    """Property 7: Validierungs-Konfiguration Round-Trip.

    **Validates: Requirements 5.1**
    """

    @given(
        max_retries=_max_retries,
        word_count_threshold=_word_count_threshold,
        single_entry_threshold=_single_entry_threshold,
        retry_prompt=_retry_prompt,
    )
    @settings(max_examples=100)
    def test_validation_config_round_trip(
        self,
        max_retries: int,
        word_count_threshold: float,
        single_entry_threshold: int,
        retry_prompt: str,
        tmp_path_factory,
    ):
        """For all valid combinations of validation parameters, serializing as
        YAML and parsing through ConfigLoader should produce an equivalent
        ValidierungsConfig."""
        # Build YAML data with required fields + validation section
        config_data = {
            "catalog_path": "/photos/catalog.lrcat",
            "model_name": "llava",
            "validation": {
                "max_retries": max_retries,
                "word_count_threshold": word_count_threshold,
                "single_entry_threshold": single_entry_threshold,
                "retry_prompt": retry_prompt,
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

        assert loaded.validierung.max_retries == max_retries
        assert loaded.validierung.wortanzahl_schwellenwert == word_count_threshold
        assert loaded.validierung.einzeleintrag_schwellenwert == single_entry_threshold
        assert loaded.validierung.retry_prompt == retry_prompt
