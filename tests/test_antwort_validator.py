"""Unit-Tests für AntwortValidator."""

from __future__ import annotations

from photo_keywords.antwort_validator import AntwortValidator
from photo_keywords.models import ValidierungsConfig, ValidierungsErgebnis


class TestLeereListeUngueltig:
    """Test: Leere Liste → ungültig.

    Anforderung 1.6
    """

    def test_empty_list_is_invalid(self) -> None:
        config = ValidierungsConfig()
        validator = AntwortValidator(config)

        ergebnis = validator.validieren([])

        assert not ergebnis.gueltig
        assert ergebnis.grund is not None
        assert len(ergebnis.grund) > 0


class TestVordefinierteAblehnungsphrasen:
    """Test: Vordefinierte Ablehnungsphrasen vollständig vorhanden.

    Anforderung 6.1, 6.3
    """

    def test_required_phrases_present(self) -> None:
        """Alle in Anforderung 6.3 geforderten Phrasen müssen enthalten sein."""
        required = [
            "ich kann nicht",
            "ich kann das nicht",
            "i cannot",
            "i can't",
            "i'm sorry",
            "es tut mir leid",
            "nicht möglich",
            "unable to",
        ]
        for phrase in required:
            assert phrase in AntwortValidator.ABLEHNUNGS_PHRASEN, (
                f"Required refusal phrase missing: {phrase!r}"
            )

    def test_has_german_and_english_phrases(self) -> None:
        """Sowohl deutsche als auch englische Phrasen müssen vorhanden sein."""
        german_found = any(
            "ich" in p or "leid" in p or "möglich" in p or "leider" in p
            for p in AntwortValidator.ABLEHNUNGS_PHRASEN
        )
        english_found = any(
            "cannot" in p or "can't" in p or "sorry" in p or "unable" in p
            for p in AntwortValidator.ABLEHNUNGS_PHRASEN
        )
        assert german_found, "No German refusal phrases found"
        assert english_found, "No English refusal phrases found"


class TestValidierungsConfigStandardwerte:
    """Test: Standardwerte von ValidierungsConfig korrekt.

    Anforderung 5.2, 5.3
    """

    def test_default_max_retries(self) -> None:
        config = ValidierungsConfig()
        assert config.max_retries == 2

    def test_default_wortanzahl_schwellenwert(self) -> None:
        config = ValidierungsConfig()
        assert config.wortanzahl_schwellenwert == 3.0

    def test_default_einzeleintrag_schwellenwert(self) -> None:
        config = ValidierungsConfig()
        assert config.einzeleintrag_schwellenwert == 4

    def test_default_retry_prompt_is_nonempty_german(self) -> None:
        config = ValidierungsConfig()
        assert len(config.retry_prompt) > 0
        # Should contain German instruction keywords
        assert "Stichwörtern" in config.retry_prompt or "Komma" in config.retry_prompt or "Sätze" in config.retry_prompt
