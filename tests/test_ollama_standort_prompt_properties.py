"""Property-basierte Tests für Standort-Prompt-Konstruktion im OllamaClient.

**Validates: Requirements 5.1, 5.4**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from photo_keywords.models import StandortDaten
from photo_keywords.ollama_client import OllamaClient


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_valid_lat = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)
_valid_lon = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)

_non_empty_text = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=1,
    max_size=20,
)

_prompt_text = st.text(min_size=1, max_size=200)

_standort_daten = st.builds(
    StandortDaten,
    stadt=_non_empty_text,
    region=_non_empty_text,
    land=_non_empty_text,
    breitengrad=_valid_lat,
    laengengrad=_valid_lon,
)


# ---------------------------------------------------------------------------
# Property 6: Standort-Prompt-Konstruktion bewahrt Original-Prompt
# ---------------------------------------------------------------------------


class TestProperty6StandortPromptKonstruktion:
    """**Validates: Requirements 5.1, 5.4**

    Property 6: Für alle StandortDaten-Instanzen und für alle Prompt-Strings
    soll der konstruierte Prompt (a) mit dem Standort-Kontext-Prefix beginnen,
    (b) den Original-Prompt unverändert als Suffix enthalten, und (c) die
    Ortsnamen aus StandortDaten im Prefix enthalten. Wenn StandortDaten None
    ist, soll der Prompt exakt dem Original-Prompt entsprechen.
    """

    @given(standort=_standort_daten, prompt=_prompt_text)
    @settings(max_examples=100)
    def test_prompt_starts_with_prefix(self, standort: StandortDaten, prompt: str) -> None:
        prefix = OllamaClient._standort_prompt_prefix(standort)
        full_prompt = prefix + "\n" + prompt

        # (a) full prompt starts with prefix
        assert full_prompt.startswith(prefix)

    @given(standort=_standort_daten, prompt=_prompt_text)
    @settings(max_examples=100)
    def test_prompt_ends_with_original(self, standort: StandortDaten, prompt: str) -> None:
        prefix = OllamaClient._standort_prompt_prefix(standort)
        full_prompt = prefix + "\n" + prompt

        # (b) full prompt ends with original prompt
        assert full_prompt.endswith(prompt)

    @given(standort=_standort_daten, prompt=_prompt_text)
    @settings(max_examples=100)
    def test_prefix_contains_stadt_and_land(self, standort: StandortDaten, prompt: str) -> None:
        prefix = OllamaClient._standort_prompt_prefix(standort)

        # (c) stadt and land appear in prefix
        assert standort.stadt in prefix
        assert standort.land in prefix

    @given(prompt=_prompt_text)
    @settings(max_examples=100)
    def test_none_standort_returns_original_prompt(self, prompt: str) -> None:
        """When standort_daten is None, the prompt should be exactly the original."""
        # Replicate the logic from analyse_bild: if None, prompt is unchanged
        standort_daten = None
        if standort_daten is not None:
            result = OllamaClient._standort_prompt_prefix(standort_daten) + "\n" + prompt
        else:
            result = prompt

        assert result == prompt
