"""Property-basierte Tests für KlassifikationsRouter."""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from lightroom_ollama_keywords.klassifikations_router import (
    KlassifikationsRouter,
    _KATEGORIE_LOOKUP,
)
from lightroom_ollama_keywords.models import (
    FotoKategorie,
    KategorieConfig,
    KlassifikationsConfig,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Arbitrary text strings for parsing tests
_arbitrary_text = st.text(min_size=0, max_size=100)

# Known category names (exact values from FotoKategorie)
_known_category_names = [k.value for k in FotoKategorie]

# Strategy for a valid FotoKategorie member
_foto_kategorie = st.sampled_from(list(FotoKategorie))

# Strategy for case/whitespace variations of known category names
_category_variation = st.one_of(
    # Exact match
    st.sampled_from(_known_category_names),
    # Lowercase
    st.sampled_from(_known_category_names).map(str.lower),
    # Uppercase
    st.sampled_from(_known_category_names).map(str.upper),
    # With leading/trailing whitespace
    st.sampled_from(_known_category_names).flatmap(
        lambda name: st.tuples(
            st.text(alphabet=" \t\n\r", min_size=0, max_size=5),
            st.just(name),
            st.text(alphabet=" \t\n\r", min_size=0, max_size=5),
        ).map(lambda t: t[0] + t[1] + t[2])
    ),
    # Lowercase with whitespace
    st.sampled_from(_known_category_names).flatmap(
        lambda name: st.tuples(
            st.text(alphabet=" \t\n\r", min_size=0, max_size=5),
            st.just(name.lower()),
            st.text(alphabet=" \t\n\r", min_size=0, max_size=5),
        ).map(lambda t: t[0] + t[1] + t[2])
    ),
)

# Strategy for a non-empty prompt string
_prompt_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())

# Strategy for an optional model name (None or non-empty string)
_optional_model = st.one_of(st.none(), st.text(min_size=1, max_size=50).filter(lambda s: s.strip()))

# Strategy for KategorieConfig
_kategorie_config = st.builds(
    KategorieConfig,
    prompt=_prompt_text,
    modell=_optional_model,
)

# Strategy for a complete KategorieConfig mapping (all categories have a config)
_full_kategorien_mapping = st.fixed_dictionaries(
    {k: _kategorie_config for k in FotoKategorie}
)


# ---------------------------------------------------------------------------
# Property 1: Kategorie-Parsing — Normalisierung und Fallback
# ---------------------------------------------------------------------------


class TestKategorieParsingProperty:
    """**Validates: Requirements 1.2, 5.2, 8.1, 8.3, 8.4**

    Property 1: Kategorie-Parsing — Normalisierung und Fallback.
    Für alle Strings: kategorie_parsen gibt immer ein gültiges FotoKategorie-Mitglied
    zurück. Variationen in Groß-/Kleinschreibung und Whitespace werden korrekt
    normalisiert. Unbekannte Strings ergeben SONSTIGES.
    """

    @given(text=_arbitrary_text)
    @settings(max_examples=200)
    def test_always_returns_valid_foto_kategorie(self, text: str) -> None:
        """For all strings, kategorie_parsen returns a valid FotoKategorie member."""
        result = KlassifikationsRouter.kategorie_parsen(text)
        assert isinstance(result, FotoKategorie), (
            f"Expected FotoKategorie, got {type(result)} for input {text!r}"
        )
        assert result in FotoKategorie, (
            f"Result {result!r} is not a valid FotoKategorie member"
        )

    @given(variation=_category_variation)
    @settings(max_examples=200)
    def test_case_whitespace_variations_normalized(self, variation: str) -> None:
        """Case/whitespace variations of known category names are correctly normalized."""
        result = KlassifikationsRouter.kategorie_parsen(variation)
        # The stripped, lowered version should be in the lookup
        normalised = variation.strip().lower()
        if normalised in _KATEGORIE_LOOKUP:
            expected = _KATEGORIE_LOOKUP[normalised]
            assert result == expected, (
                f"Input {variation!r} (normalised: {normalised!r}) should map to "
                f"{expected!r}, got {result!r}"
            )

    @given(text=_arbitrary_text)
    @settings(max_examples=200)
    def test_unknown_strings_yield_sonstiges(self, text: str) -> None:
        """Unknown strings yield SONSTIGES."""
        normalised = text.strip().lower()
        if normalised not in _KATEGORIE_LOOKUP:
            result = KlassifikationsRouter.kategorie_parsen(text)
            assert result == FotoKategorie.SONSTIGES, (
                f"Unknown input {text!r} should yield SONSTIGES, got {result!r}"
            )


# ---------------------------------------------------------------------------
# Property 2: Kategorie Round-Trip — Parsen → Formatieren → Parsen
# ---------------------------------------------------------------------------


class TestKategorieRoundTripProperty:
    """**Validates: Requirements 8.2**

    Property 2: Kategorie Round-Trip.
    Für alle gültigen FotoKategorie-Werte: kategorie_parsen(kategorie_formatieren(kategorie))
    ergibt dieselbe FotoKategorie.
    """

    @given(kategorie=_foto_kategorie)
    @settings(max_examples=200)
    def test_round_trip_parse_format_parse(self, kategorie: FotoKategorie) -> None:
        """parse(format(k)) == k for all valid FotoKategorie values."""
        formatted = KlassifikationsRouter.kategorie_formatieren(kategorie)
        parsed = KlassifikationsRouter.kategorie_parsen(formatted)
        assert parsed == kategorie, (
            f"Round-trip failed: {kategorie!r} → {formatted!r} → {parsed!r}"
        )


# ---------------------------------------------------------------------------
# Property 3: Prompt- und Modellauswahl nach Kategorie
# ---------------------------------------------------------------------------


class TestPromptModellAuswahlProperty:
    """**Validates: Requirements 2.1, 3.1, 3.2**

    Property 3: Prompt- und Modellauswahl nach Kategorie.
    Für alle FotoKategorie-Werte und gültige KategorieConfig-Mappings:
    Der Router wählt den korrekten Prompt. Bei alternativem Modell wird dieses
    verwendet, sonst das Standard-Modell.
    """

    @given(
        kategorie=_foto_kategorie,
        kategorien=_full_kategorien_mapping,
        standard_modell=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
        fallback_prompt=st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
    )
    @settings(max_examples=200)
    def test_correct_prompt_and_model_selection(
        self,
        kategorie: FotoKategorie,
        kategorien: dict[FotoKategorie, KategorieConfig],
        standard_modell: str,
        fallback_prompt: str,
    ) -> None:
        """Router selects correct prompt and model for each category."""
        config = KlassifikationsConfig(
            modell="klassifikations-modell",
            prompt="Klassifiziere dieses Foto",
            kategorien=kategorien,
        )

        router = KlassifikationsRouter(
            endpoint="http://dummy:11434",
            klassifikations_config=config,
            standard_modell=standard_modell,
            fallback_prompt=fallback_prompt,
        )

        # Test the internal method directly
        prompt, modell = router._prompt_und_modell_fuer(kategorie)

        expected_config = kategorien[kategorie]

        # Prompt should match the category config
        assert prompt == expected_config.prompt, (
            f"For {kategorie!r}: expected prompt {expected_config.prompt!r}, got {prompt!r}"
        )

        # Model: if category config has a model, use it; otherwise standard model
        if expected_config.modell:
            assert modell == expected_config.modell, (
                f"For {kategorie!r}: expected model {expected_config.modell!r}, got {modell!r}"
            )
        else:
            assert modell == standard_modell, (
                f"For {kategorie!r}: expected standard model {standard_modell!r}, got {modell!r}"
            )
