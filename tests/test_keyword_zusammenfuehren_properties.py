"""Property-basierte Tests für BatchProcessor._keywords_zusammenfuehren().

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from photo_keywords.batch_processor import BatchProcessor
from photo_keywords.models import StandortDaten


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_valid_lat = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)
_valid_lon = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)

_keyword_text = st.text(min_size=0, max_size=30)

_ki_keywords = st.lists(_keyword_text, min_size=0, max_size=20)

_non_empty_text = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=1,
    max_size=20,
)

_maybe_empty_text = st.one_of(st.just(""), _non_empty_text)

_standort_daten = st.builds(
    StandortDaten,
    stadt=_maybe_empty_text,
    region=_maybe_empty_text,
    land=_maybe_empty_text,
    breitengrad=_valid_lat,
    laengengrad=_valid_lon,
)


# ---------------------------------------------------------------------------
# Property 5: Keyword-Zusammenführung ist vollständig, duplikatfrei und
#              ohne leere Strings
# ---------------------------------------------------------------------------


class TestProperty5KeywordZusammenfuehrung:
    """**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

    Property 5: Für alle Listen von KI-Keywords und für alle
    StandortDaten-Instanzen soll die Zusammenführung ein Ergebnis liefern,
    das (a) alle KI-Keywords enthält, (b) alle nicht-leeren
    Standort-Stichwörter enthält, (c) keine Duplikate aufweist, und
    (d) keine leeren Strings enthält. Wenn StandortDaten None ist, soll
    das Ergebnis exakt den KI-Keywords entsprechen (minus leere Strings).
    """

    @given(ki_kw=_ki_keywords, sd=_standort_daten)
    @settings(max_examples=100)
    def test_merge_with_standort_daten(
        self, ki_kw: list[str], sd: StandortDaten
    ) -> None:
        result = BatchProcessor._keywords_zusammenfuehren(ki_kw, sd)

        # (a) all non-empty KI keywords present
        for kw in ki_kw:
            if kw:
                assert kw in result, f"KI keyword {kw!r} missing from result"

        # (b) all non-empty standort keywords present
        for kw in sd.als_stichwort_liste():
            if kw:
                assert kw in result, f"Standort keyword {kw!r} missing from result"

        # (c) no duplicates
        assert len(result) == len(set(result)), "Result contains duplicates"

        # (d) no empty strings
        for kw in result:
            assert kw != "", "Result contains empty string"

    @given(ki_kw=_ki_keywords)
    @settings(max_examples=100)
    def test_merge_with_none_standort(self, ki_kw: list[str]) -> None:
        result = BatchProcessor._keywords_zusammenfuehren(ki_kw, None)

        expected = list(dict.fromkeys(kw for kw in ki_kw if kw))

        # When StandortDaten is None, result equals KI keywords minus empty strings
        assert result == expected

        # (c) no duplicates
        assert len(result) == len(set(result)), "Result contains duplicates"

        # (d) no empty strings
        for kw in result:
            assert kw != "", "Result contains empty string"
