"""Unit-Tests für StandortDaten."""

from __future__ import annotations

import dataclasses

import pytest

from lightroom_ollama_keywords.models import StandortDaten


class TestStandortDatenFrozen:
    """Validates: Requirement 8.2 — frozen dataclass."""

    def test_mutation_raises_frozen_instance_error(self) -> None:
        sd = StandortDaten(
            stadt="Berlin", region="Berlin", land="DE",
            breitengrad=52.52, laengengrad=13.405,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            sd.stadt = "München"  # type: ignore[misc]

    def test_ist_frozen_dataclass(self) -> None:
        assert dataclasses.is_dataclass(StandortDaten)
        assert StandortDaten.__dataclass_params__.frozen  # type: ignore[attr-defined]


class TestStandortDatenAlsStichwortListe:
    """Validates: Requirement 8.4 — als_stichwort_liste mit leeren Feldern."""

    def test_alle_felder_gefuellt(self) -> None:
        sd = StandortDaten(
            stadt="München", region="Bayern", land="DE",
            breitengrad=48.14, laengengrad=11.58,
        )
        assert sd.als_stichwort_liste() == ["München", "Bayern", "DE"]

    def test_stadt_leer(self) -> None:
        sd = StandortDaten(
            stadt="", region="Bayern", land="DE",
            breitengrad=48.14, laengengrad=11.58,
        )
        assert sd.als_stichwort_liste() == ["Bayern", "DE"]

    def test_region_leer(self) -> None:
        sd = StandortDaten(
            stadt="München", region="", land="DE",
            breitengrad=48.14, laengengrad=11.58,
        )
        assert sd.als_stichwort_liste() == ["München", "DE"]

    def test_land_leer(self) -> None:
        sd = StandortDaten(
            stadt="München", region="Bayern", land="",
            breitengrad=48.14, laengengrad=11.58,
        )
        assert sd.als_stichwort_liste() == ["München", "Bayern"]

    def test_alle_felder_leer(self) -> None:
        sd = StandortDaten(
            stadt="", region="", land="",
            breitengrad=0.0, laengengrad=0.0,
        )
        assert sd.als_stichwort_liste() == []


class TestStandortDatenKoordinatenValidierung:
    """Validates: Requirement 8.3 — ValueError bei ungültigen Koordinaten."""

    def test_breitengrad_zu_gross(self) -> None:
        with pytest.raises(ValueError, match="Breitengrad"):
            StandortDaten(stadt="X", region="X", land="X", breitengrad=91.0, laengengrad=0.0)

    def test_breitengrad_zu_klein(self) -> None:
        with pytest.raises(ValueError, match="Breitengrad"):
            StandortDaten(stadt="X", region="X", land="X", breitengrad=-91.0, laengengrad=0.0)

    def test_laengengrad_zu_gross(self) -> None:
        with pytest.raises(ValueError, match="Längengrad"):
            StandortDaten(stadt="X", region="X", land="X", breitengrad=0.0, laengengrad=181.0)

    def test_laengengrad_zu_klein(self) -> None:
        with pytest.raises(ValueError, match="Längengrad"):
            StandortDaten(stadt="X", region="X", land="X", breitengrad=0.0, laengengrad=-181.0)

    def test_grenzwerte_gueltig(self) -> None:
        """Boundary values should be accepted."""
        sd = StandortDaten(stadt="X", region="X", land="X", breitengrad=90.0, laengengrad=180.0)
        assert sd.breitengrad == 90.0
        assert sd.laengengrad == 180.0

        sd2 = StandortDaten(stadt="X", region="X", land="X", breitengrad=-90.0, laengengrad=-180.0)
        assert sd2.breitengrad == -90.0
        assert sd2.laengengrad == -180.0
