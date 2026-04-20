"""Property-basierte Tests für StandortDaten."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lightroom_ollama_keywords.models import StandortDaten


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_valid_lat = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)
_valid_lon = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)

_invalid_lat = st.one_of(
    st.floats(max_value=-90.01, allow_nan=False, allow_infinity=False),
    st.floats(min_value=90.01, allow_nan=False, allow_infinity=False),
)
_invalid_lon = st.one_of(
    st.floats(max_value=-180.01, allow_nan=False, allow_infinity=False),
    st.floats(min_value=180.01, allow_nan=False, allow_infinity=False),
)

_non_empty_text = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=1,
    max_size=20,
)

_maybe_empty_text = st.one_of(st.just(""), _non_empty_text)


# ---------------------------------------------------------------------------
# Property 7: StandortDaten-Koordinatenvalidierung
# ---------------------------------------------------------------------------


class TestProperty7KoordinatenValidierung:
    """**Validates: Requirements 8.3**

    Property 7: Für alle Breitengrad-Werte außerhalb [-90, 90] oder
    Längengrad-Werte außerhalb [-180, 180] soll die Erstellung einer
    StandortDaten-Instanz einen ValueError auslösen. Für alle Werte
    innerhalb der gültigen Bereiche soll die Erstellung erfolgreich sein.
    """

    @given(lat=_invalid_lat, lon=_valid_lon)
    @settings(max_examples=100)
    def test_invalid_latitude_raises(self, lat: float, lon: float) -> None:
        with pytest.raises(ValueError, match="Breitengrad"):
            StandortDaten(stadt="X", region="X", land="X", breitengrad=lat, laengengrad=lon)

    @given(lat=_valid_lat, lon=_invalid_lon)
    @settings(max_examples=100)
    def test_invalid_longitude_raises(self, lat: float, lon: float) -> None:
        with pytest.raises(ValueError, match="Längengrad"):
            StandortDaten(stadt="X", region="X", land="X", breitengrad=lat, laengengrad=lon)

    @given(lat=_valid_lat, lon=_valid_lon)
    @settings(max_examples=100)
    def test_valid_coordinates_succeed(self, lat: float, lon: float) -> None:
        sd = StandortDaten(stadt="X", region="X", land="X", breitengrad=lat, laengengrad=lon)
        assert sd.breitengrad == lat
        assert sd.laengengrad == lon


# ---------------------------------------------------------------------------
# Property 8: als_stichwort_liste gibt nur nicht-leere Felder zurück
# ---------------------------------------------------------------------------


class TestProperty8AlsStichwortListe:
    """**Validates: Requirements 8.4, 8.5**

    Property 8: Für alle StandortDaten-Instanzen soll als_stichwort_liste()
    eine Liste zurückgeben, die (a) nur Elemente aus {stadt, region, land}
    enthält, (b) keine leeren Strings enthält, (c) genau die nicht-leeren
    Werte von stadt, region und land enthält, und (d) eine Länge zwischen
    0 und 3 hat.
    """

    @given(
        stadt=_maybe_empty_text,
        region=_maybe_empty_text,
        land=_maybe_empty_text,
        lat=_valid_lat,
        lon=_valid_lon,
    )
    @settings(max_examples=100)
    def test_als_stichwort_liste_properties(
        self, stadt: str, region: str, land: str, lat: float, lon: float
    ) -> None:
        sd = StandortDaten(
            stadt=stadt, region=region, land=land, breitengrad=lat, laengengrad=lon
        )
        result = sd.als_stichwort_liste()

        # (a) only contains elements from {stadt, region, land}
        for item in result:
            assert item in {stadt, region, land}

        # (b) no empty strings
        for item in result:
            assert item != ""

        # (c) contains exactly the non-empty values of stadt, region, land
        expected = [f for f in (stadt, region, land) if f]
        assert result == expected

        # (d) length between 0 and 3
        assert 0 <= len(result) <= 3
