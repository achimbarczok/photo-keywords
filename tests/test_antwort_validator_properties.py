"""Property-basierte Tests für AntwortValidator."""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from photo_keywords.antwort_validator import AntwortValidator
from photo_keywords.models import ValidierungsConfig


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Single word: 1 word with only letters, no spaces
_single_word = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=1,
    max_size=15,
)

# Multi-word string: guaranteed to have many words (for sentence detection)
_sentence = st.lists(
    _single_word,
    min_size=4,
    max_size=10,
).map(" ".join)

# Short keyword: 1-2 words, no refusal phrases
_short_keyword = st.lists(
    _single_word,
    min_size=1,
    max_size=2,
).map(" ".join)

# A known refusal phrase
_refusal_phrase = st.sampled_from(AntwortValidator.ABLEHNUNGS_PHRASEN)


# ---------------------------------------------------------------------------
# Property 1: Durchschnittliche Wortanzahl erkennt Sätze
# ---------------------------------------------------------------------------


class TestProperty1DurchschnittlicheWortanzahl:
    """**Validates: Requirements 1.2**

    Property 1: Für alle Listen von Strings, bei denen die durchschnittliche
    Wortanzahl pro Eintrag den konfigurierten Schwellenwert überschreitet,
    soll der AntwortValidator die Antwort als ungültig bewerten.
    """

    @given(sentences=st.lists(_sentence, min_size=2, max_size=5))
    @settings(max_examples=100)
    def test_high_avg_word_count_is_invalid(self, sentences: list[str]) -> None:
        config = ValidierungsConfig(wortanzahl_schwellenwert=3.0)
        validator = AntwortValidator(config)

        # Compute average word count
        avg = sum(len(s.split()) for s in sentences) / len(sentences)
        assume(avg > config.wortanzahl_schwellenwert)

        # Also assume no refusal phrases are present (to isolate this property)
        for s in sentences:
            for phrase in AntwortValidator.ABLEHNUNGS_PHRASEN:
                assume(phrase not in s.lower())

        ergebnis = validator.validieren(sentences)
        assert not ergebnis.gueltig, (
            f"Expected invalid for avg word count {avg:.1f} > {config.wortanzahl_schwellenwert}"
        )
        assert ergebnis.grund is not None
        assert "Wortanzahl" in ergebnis.grund


# ---------------------------------------------------------------------------
# Property 2: Ablehnungsphrasen-Erkennung (case-insensitiv, Teilstring)
# ---------------------------------------------------------------------------


class TestProperty2AblehnungsphrasenErkennung:
    """**Validates: Requirements 1.3, 6.2, 6.4**

    Property 2: Für alle Stichwortlisten und für alle bekannten
    Ablehnungsphrasen in beliebiger Groß-/Kleinschreibung: Wenn ein
    beliebiger Eintrag der Liste die Ablehnungsphrase als Teilstring
    enthält, soll der AntwortValidator die Antwort als ungültig bewerten.
    """

    @given(
        phrase=_refusal_phrase,
        prefix=st.text(min_size=0, max_size=10),
        suffix=st.text(min_size=0, max_size=10),
        case_fn=st.sampled_from([str.lower, str.upper, str.title]),
        other_keywords=st.lists(_short_keyword, min_size=0, max_size=3),
        insert_pos=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=100)
    def test_refusal_phrase_detected_case_insensitive(
        self,
        phrase: str,
        prefix: str,
        suffix: str,
        case_fn,
        other_keywords: list[str],
        insert_pos: int,
    ) -> None:
        config = ValidierungsConfig()
        validator = AntwortValidator(config)

        # Build an entry containing the refusal phrase in varied case
        entry_with_phrase = prefix + case_fn(phrase) + suffix

        # Insert into keyword list at a random position
        keywords = list(other_keywords)
        pos = min(insert_pos, len(keywords))
        keywords.insert(pos, entry_with_phrase)

        ergebnis = validator.validieren(keywords)
        assert not ergebnis.gueltig, (
            f"Expected invalid when refusal phrase '{phrase}' is present (as '{entry_with_phrase}')"
        )


# ---------------------------------------------------------------------------
# Property 3: Einzeleintrag-Erkennung
# ---------------------------------------------------------------------------


class TestProperty3EinzeleintagErkennung:
    """**Validates: Requirements 1.4**

    Property 3: Für alle Antworten, die aus genau einem Eintrag bestehen,
    dessen Wortanzahl den konfigurierten Einzeleintrag-Schwellenwert
    überschreitet, soll der AntwortValidator die Antwort als ungültig bewerten.
    """

    @given(
        words=st.lists(_single_word, min_size=5, max_size=15),
    )
    @settings(max_examples=100)
    def test_single_long_entry_is_invalid(self, words: list[str]) -> None:
        config = ValidierungsConfig(einzeleintrag_schwellenwert=4)
        validator = AntwortValidator(config)

        entry = " ".join(words)
        assume(len(entry.split()) > config.einzeleintrag_schwellenwert)

        # Ensure no refusal phrases
        for phrase in AntwortValidator.ABLEHNUNGS_PHRASEN:
            assume(phrase not in entry.lower())

        ergebnis = validator.validieren([entry])
        assert not ergebnis.gueltig, (
            f"Expected invalid for single entry with {len(words)} words > {config.einzeleintrag_schwellenwert}"
        )
        assert ergebnis.grund is not None
        assert "Einzeleintrag" in ergebnis.grund


# ---------------------------------------------------------------------------
# Property 4: Ergebnis-Struktur-Invariante
# ---------------------------------------------------------------------------


class TestProperty4ErgebnisStrukturInvariante:
    """**Validates: Requirements 1.5**

    Property 4: Für alle Eingaben an den AntwortValidator soll das
    zurückgegebene ValidierungsErgebnis folgende Invariante erfüllen:
    gueltig=False ↔ grund ist nicht-leerer String,
    gueltig=True ↔ grund ist None.
    """

    @given(
        keywords=st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
                min_size=0,
                max_size=50,
            ),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=100)
    def test_result_structure_invariant(self, keywords: list[str]) -> None:
        config = ValidierungsConfig()
        validator = AntwortValidator(config)

        ergebnis = validator.validieren(keywords)

        if ergebnis.gueltig:
            assert ergebnis.grund is None, (
                f"gueltig=True but grund is not None: {ergebnis.grund!r}"
            )
        else:
            assert isinstance(ergebnis.grund, str) and len(ergebnis.grund) > 0, (
                f"gueltig=False but grund is not a non-empty string: {ergebnis.grund!r}"
            )


# ---------------------------------------------------------------------------
# Property 5: Gültige Stichwortlisten werden akzeptiert
# ---------------------------------------------------------------------------


class TestProperty5GueltigeStichwortlisten:
    """**Validates: Requirements 1.7**

    Property 5: Für alle nicht-leeren Listen von kurzen Stichwörtern
    (jeder Eintrag hat höchstens 2 Wörter, kein Eintrag enthält eine
    Ablehnungsphrase), soll der AntwortValidator die Antwort als gültig bewerten.
    """

    @given(
        keywords=st.lists(_short_keyword, min_size=2, max_size=10),
    )
    @settings(max_examples=100)
    def test_valid_keyword_lists_accepted(self, keywords: list[str]) -> None:
        config = ValidierungsConfig(wortanzahl_schwellenwert=3.0)
        validator = AntwortValidator(config)

        # Ensure no refusal phrases in any keyword
        for kw in keywords:
            for phrase in AntwortValidator.ABLEHNUNGS_PHRASEN:
                assume(phrase not in kw.lower())

        # Ensure average word count is within threshold
        avg = sum(len(kw.split()) for kw in keywords) / len(keywords)
        assume(avg <= config.wortanzahl_schwellenwert)

        ergebnis = validator.validieren(keywords)
        assert ergebnis.gueltig, (
            f"Expected valid for short keywords {keywords}, but got: {ergebnis.grund}"
        )
