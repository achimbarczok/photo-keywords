"""Property-basierte Tests für StandortResolver."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from photo_keywords.standort_resolver import StandortResolver


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_valid_lat = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)
_valid_lon = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Property 4: Gültige Koordinaten erzeugen gültige StandortDaten
# ---------------------------------------------------------------------------


class TestProperty4GueltigeKoordinaten:
    """**Validates: Requirements 3.1, 3.5**

    Property 4: Für alle gültigen GPS-Koordinatenpaare (breitengrad ∈ [-90, 90],
    laengengrad ∈ [-180, 180], nicht (0.0, 0.0)) soll standort_aufloesen ein
    StandortDaten-Objekt mit nicht-leeren Werten für stadt und land zurückgeben.
    """

    @given(lat=_valid_lat, lon=_valid_lon)
    @settings(max_examples=100)
    def test_valid_coordinates_produce_valid_standort_daten(
        self, lat: float, lon: float
    ) -> None:
        assume(not (lat == 0.0 and lon == 0.0))

        mock_rg = MagicMock()
        mock_rg.search.return_value = [
            {"name": "TestStadt", "admin1": "TestRegion", "cc": "TS"}
        ]

        original = sys.modules.get("reverse_geocoder")
        sys.modules["reverse_geocoder"] = mock_rg
        try:
            resolver = StandortResolver()
            result = resolver.standort_aufloesen(lat, lon)
        finally:
            if original is not None:
                sys.modules["reverse_geocoder"] = original
            else:
                sys.modules.pop("reverse_geocoder", None)

        assert result is not None
        assert result.stadt != ""
        assert result.land != ""
        assert result.breitengrad == lat
        assert result.laengengrad == lon
