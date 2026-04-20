"""Unit-Tests für StandortResolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lightroom_ollama_keywords.standort_resolver import StandortResolver


class TestStandortAufloesen:
    """Tests für StandortResolver.standort_aufloesen()."""

    def test_null_island_returns_none(self) -> None:
        """(0.0, 0.0) wird als ungültig behandelt und gibt None zurück."""
        resolver = StandortResolver()
        with patch.dict("sys.modules", {"reverse_geocoder": MagicMock()}):
            result = resolver.standort_aufloesen(0.0, 0.0)
        assert result is None

    def test_invalid_breitengrad_too_high_returns_none(self) -> None:
        """Breitengrad > 90 gibt None zurück."""
        resolver = StandortResolver()
        with patch.dict("sys.modules", {"reverse_geocoder": MagicMock()}):
            result = resolver.standort_aufloesen(91.0, 13.0)
        assert result is None

    def test_invalid_breitengrad_too_low_returns_none(self) -> None:
        """Breitengrad < -90 gibt None zurück."""
        resolver = StandortResolver()
        with patch.dict("sys.modules", {"reverse_geocoder": MagicMock()}):
            result = resolver.standort_aufloesen(-91.0, 13.0)
        assert result is None

    def test_invalid_laengengrad_too_high_returns_none(self) -> None:
        """Längengrad > 180 gibt None zurück."""
        resolver = StandortResolver()
        with patch.dict("sys.modules", {"reverse_geocoder": MagicMock()}):
            result = resolver.standort_aufloesen(52.0, 181.0)
        assert result is None

    def test_invalid_laengengrad_too_low_returns_none(self) -> None:
        """Längengrad < -180 gibt None zurück."""
        resolver = StandortResolver()
        with patch.dict("sys.modules", {"reverse_geocoder": MagicMock()}):
            result = resolver.standort_aufloesen(52.0, -181.0)
        assert result is None

    def test_valid_coordinates_returns_standort_daten(self) -> None:
        """Gültige Koordinaten geben StandortDaten zurück."""
        mock_rg = MagicMock()
        mock_rg.search.return_value = [
            {
                "name": "Berlin",
                "admin1": "Berlin",
                "cc": "DE",
                "lat": "52.52437",
                "lon": "13.41053",
                "admin2": "Berlin",
            }
        ]

        resolver = StandortResolver()
        with patch.dict("sys.modules", {"reverse_geocoder": mock_rg}):
            result = resolver.standort_aufloesen(52.52, 13.405)

        assert result is not None
        assert result.stadt == "Berlin"
        assert result.region == "Berlin"
        assert result.land == "DE"
        assert result.breitengrad == 52.52
        assert result.laengengrad == 13.405

    def test_import_error_when_not_installed(self) -> None:
        """ImportError mit beschreibender Meldung wenn reverse_geocoder fehlt."""
        resolver = StandortResolver()
        with patch.dict("sys.modules", {"reverse_geocoder": None}):
            with pytest.raises(ImportError, match="reverse_geocoder"):
                resolver.standort_aufloesen(52.52, 13.405)

    def test_internal_error_returns_none(self) -> None:
        """Interner Fehler bei reverse_geocoder gibt None zurück."""
        mock_rg = MagicMock()
        mock_rg.search.side_effect = RuntimeError("internal error")

        resolver = StandortResolver()
        with patch.dict("sys.modules", {"reverse_geocoder": mock_rg}):
            result = resolver.standort_aufloesen(52.52, 13.405)

        assert result is None

    def test_empty_results_returns_none(self) -> None:
        """Leere Ergebnisliste gibt None zurück."""
        mock_rg = MagicMock()
        mock_rg.search.return_value = []

        resolver = StandortResolver()
        with patch.dict("sys.modules", {"reverse_geocoder": mock_rg}):
            result = resolver.standort_aufloesen(52.52, 13.405)

        assert result is None

    def test_boundary_coordinates_valid(self) -> None:
        """Grenzwerte (-90, -180) und (90, 180) sind gültig."""
        mock_rg = MagicMock()
        mock_rg.search.return_value = [
            {"name": "South Pole", "admin1": "Antarctica", "cc": "AQ"}
        ]

        resolver = StandortResolver()
        with patch.dict("sys.modules", {"reverse_geocoder": mock_rg}):
            result = resolver.standort_aufloesen(-90.0, -180.0)

        assert result is not None
        assert result.stadt == "South Pole"


class TestKoordinatenGueltig:
    """Tests für StandortResolver._koordinaten_gueltig()."""

    def test_valid_coordinates(self) -> None:
        assert StandortResolver._koordinaten_gueltig(52.52, 13.405) is True

    def test_null_island_invalid(self) -> None:
        assert StandortResolver._koordinaten_gueltig(0.0, 0.0) is False

    def test_zero_lat_nonzero_lon_valid(self) -> None:
        assert StandortResolver._koordinaten_gueltig(0.0, 13.0) is True

    def test_nonzero_lat_zero_lon_valid(self) -> None:
        assert StandortResolver._koordinaten_gueltig(52.0, 0.0) is True

    def test_boundary_max(self) -> None:
        assert StandortResolver._koordinaten_gueltig(90.0, 180.0) is True

    def test_boundary_min(self) -> None:
        assert StandortResolver._koordinaten_gueltig(-90.0, -180.0) is True

    def test_out_of_range_lat(self) -> None:
        assert StandortResolver._koordinaten_gueltig(90.1, 0.0) is False

    def test_out_of_range_lon(self) -> None:
        assert StandortResolver._koordinaten_gueltig(0.0, 180.1) is False
