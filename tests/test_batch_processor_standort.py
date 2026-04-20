"""Tests für BatchProcessor Standort-Verarbeitung (Task 6.6).

Tests für:
- Neue Konstruktor-Parameter (gps_leser, standort_resolver, katalog_conn)
- GPS → Standort → Analyse-Flow in batch_verarbeiten()
- _keywords_zusammenfuehren() statische Methode
- Zusammengeführte Keywords an StichwortSchreiber

Requirements: 4.1, 4.2, 4.3, 4.4, 7.4, 7.5
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, call

import pytest

from lightroom_ollama_keywords.batch_processor import BatchProcessor
from lightroom_ollama_keywords.models import (
    BatchErgebnis,
    FotoEintrag,
    FotoKategorie,
    KlassifikationsErgebnis,
    StandortDaten,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _standort(
    stadt: str = "Berlin",
    region: str = "Berlin",
    land: str = "DE",
    lat: float = 52.52,
    lon: float = 13.405,
) -> StandortDaten:
    return StandortDaten(stadt=stadt, region=region, land=land, breitengrad=lat, laengengrad=lon)


def _make_processor(
    ollama=None,
    schreiber=None,
    tracker=None,
    router=None,
    gps_leser=None,
    standort_resolver=None,
    katalog_conn=None,
) -> BatchProcessor:
    return BatchProcessor(
        ollama=ollama or MagicMock(analyse_bild=MagicMock(return_value=["landscape"])),
        schreiber=schreiber or MagicMock(),
        tracker=tracker or MagicMock(),
        model_name="llava",
        model_version="1.0",
        klassifikations_router=router,
        gps_leser=gps_leser,
        standort_resolver=standort_resolver,
        katalog_conn=katalog_conn,
    )


# ---------------------------------------------------------------------------
# Tests: _keywords_zusammenfuehren (static method)
# ---------------------------------------------------------------------------

class TestKeywordsZusammenfuehren:
    """Tests für BatchProcessor._keywords_zusammenfuehren().

    Requirements: 4.1, 4.2, 4.3, 4.4
    """

    def test_standort_none_returns_ki_keywords(self):
        """Req 4.3: Ohne Standort nur KI-Keywords."""
        result = BatchProcessor._keywords_zusammenfuehren(["a", "b"], None)
        assert result == ["a", "b"]

    def test_standort_keywords_first(self):
        """Req 4.1: Standort-Stichwörter stehen vor KI-Keywords."""
        sd = _standort(stadt="Berlin", region="Berlin", land="DE")
        result = BatchProcessor._keywords_zusammenfuehren(["landscape"], sd)
        assert result[0] == "Berlin"
        assert result[-1] == "landscape"

    def test_no_duplicates(self):
        """Req 4.2: Keine Duplikate in der zusammengeführten Liste."""
        sd = _standort(stadt="Berlin", region="Berlin", land="DE")
        result = BatchProcessor._keywords_zusammenfuehren(["Berlin", "landscape"], sd)
        assert result.count("Berlin") == 1

    def test_empty_strings_filtered(self):
        """Req 4.4: Leere Strings werden herausgefiltert."""
        sd = _standort(stadt="Berlin", region="", land="DE")
        result = BatchProcessor._keywords_zusammenfuehren(["", "landscape"], sd)
        assert "" not in result
        assert "Berlin" in result
        assert "DE" in result
        assert "landscape" in result

    def test_all_ki_keywords_present(self):
        """Req 4.1: Alle KI-Keywords sind im Ergebnis enthalten."""
        sd = _standort()
        ki = ["sunset", "ocean", "waves"]
        result = BatchProcessor._keywords_zusammenfuehren(ki, sd)
        for kw in ki:
            assert kw in result

    def test_all_standort_keywords_present(self):
        """Req 4.1: Alle nicht-leeren Standort-Stichwörter sind im Ergebnis."""
        sd = _standort(stadt="München", region="Bayern", land="DE")
        result = BatchProcessor._keywords_zusammenfuehren(["landscape"], sd)
        assert "München" in result
        assert "Bayern" in result
        assert "DE" in result

    def test_standort_none_filters_empty_ki_keywords(self):
        """Req 4.4: Auch ohne Standort werden leere KI-Keywords gefiltert."""
        result = BatchProcessor._keywords_zusammenfuehren(["a", "", "b", ""], None)
        assert result == ["a", "b"]


# ---------------------------------------------------------------------------
# Tests: batch_verarbeiten with Standort
# ---------------------------------------------------------------------------

class TestBatchVerarbeitenMitStandort:
    """Tests für batch_verarbeiten() mit GPS/Standort-Verarbeitung.

    Requirements: 4.1, 7.4, 7.5
    """

    def test_gps_und_standort_an_analyse_uebergeben(self):
        """Req 7.5: GPS wird ermittelt, Standort aufgelöst und an Analyse übergeben."""
        sd = _standort()
        mock_gps = MagicMock()
        mock_gps.gps_ermitteln.return_value = (52.52, 13.405)
        mock_resolver = MagicMock()
        mock_resolver.standort_aufloesen.return_value = sd
        mock_ollama = MagicMock()
        mock_ollama.analyse_bild.return_value = ["landscape"]

        processor = _make_processor(
            ollama=mock_ollama,
            gps_leser=mock_gps,
            standort_resolver=mock_resolver,
        )
        fotos = [FotoEintrag(1, "/foto1.jpg")]
        processor.batch_verarbeiten(fotos)

        # GPS was queried
        mock_gps.gps_ermitteln.assert_called_once_with("/foto1.jpg", None, 1)
        # Standort was resolved
        mock_resolver.standort_aufloesen.assert_called_once_with(52.52, 13.405)
        # Analyse received standort_daten
        mock_ollama.analyse_bild.assert_called_once_with("/foto1.jpg", sd)

    def test_merged_keywords_written(self):
        """Req 4.1: Zusammengeführte Keywords werden an StichwortSchreiber übergeben."""
        sd = _standort(stadt="Berlin", region="Berlin", land="DE")
        mock_gps = MagicMock()
        mock_gps.gps_ermitteln.return_value = (52.52, 13.405)
        mock_resolver = MagicMock()
        mock_resolver.standort_aufloesen.return_value = sd
        mock_ollama = MagicMock()
        mock_ollama.analyse_bild.return_value = ["landscape", "nature"]
        mock_schreiber = MagicMock()

        processor = _make_processor(
            ollama=mock_ollama,
            schreiber=mock_schreiber,
            gps_leser=mock_gps,
            standort_resolver=mock_resolver,
        )
        fotos = [FotoEintrag(1, "/foto1.jpg")]
        processor.batch_verarbeiten(fotos)

        # Schreiber should receive merged keywords (Standort first)
        written_keywords = mock_schreiber.stichwörter_schreiben.call_args[0][1]
        assert written_keywords[0] == "Berlin"
        assert "DE" in written_keywords
        assert "landscape" in written_keywords
        assert "nature" in written_keywords

    def test_no_gps_leser_skips_standort(self):
        """Req 7.4: Ohne gps_leser keine Standort-Verarbeitung."""
        mock_ollama = MagicMock()
        mock_ollama.analyse_bild.return_value = ["landscape"]
        mock_schreiber = MagicMock()

        processor = _make_processor(ollama=mock_ollama, schreiber=mock_schreiber)
        fotos = [FotoEintrag(1, "/foto1.jpg")]
        processor.batch_verarbeiten(fotos)

        # Analyse called without standort
        mock_ollama.analyse_bild.assert_called_once_with("/foto1.jpg", None)
        # Only KI keywords written
        mock_schreiber.stichwörter_schreiben.assert_called_once_with("/foto1.jpg", ["landscape"])

    def test_no_gps_found_processes_without_standort(self):
        """Req 7.5: Kein GPS → Foto ohne Standort-Stichwörter verarbeiten."""
        mock_gps = MagicMock()
        mock_gps.gps_ermitteln.return_value = None
        mock_resolver = MagicMock()
        mock_ollama = MagicMock()
        mock_ollama.analyse_bild.return_value = ["landscape"]

        processor = _make_processor(
            ollama=mock_ollama,
            gps_leser=mock_gps,
            standort_resolver=mock_resolver,
        )
        fotos = [FotoEintrag(1, "/foto1.jpg")]
        processor.batch_verarbeiten(fotos)

        # Resolver should NOT be called
        mock_resolver.standort_aufloesen.assert_not_called()
        # Analyse called with None standort
        mock_ollama.analyse_bild.assert_called_once_with("/foto1.jpg", None)

    def test_katalog_conn_passed_to_gps_leser(self):
        """Katalog-Connection wird an gps_ermitteln übergeben."""
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_gps = MagicMock()
        mock_gps.gps_ermitteln.return_value = None
        mock_resolver = MagicMock()

        processor = _make_processor(
            gps_leser=mock_gps,
            standort_resolver=mock_resolver,
            katalog_conn=mock_conn,
        )
        fotos = [FotoEintrag(42, "/foto.jpg")]
        processor.batch_verarbeiten(fotos)

        mock_gps.gps_ermitteln.assert_called_once_with("/foto.jpg", mock_conn, 42)

    def test_standort_with_router(self):
        """Standort wird auch an KlassifikationsRouter übergeben."""
        sd = _standort()
        mock_gps = MagicMock()
        mock_gps.gps_ermitteln.return_value = (52.52, 13.405)
        mock_resolver = MagicMock()
        mock_resolver.standort_aufloesen.return_value = sd
        mock_router = MagicMock()
        mock_router.bild_analysieren.return_value = KlassifikationsErgebnis(
            kategorie=FotoKategorie.LANDSCHAFT,
            keywords=["landscape"],
            klassifikations_zeit_ms=100.0,
            keyword_zeit_ms=200.0,
            verwendeter_prompt_typ="Landschaft",
            verwendetes_modell="llava",
        )

        processor = _make_processor(
            router=mock_router,
            gps_leser=mock_gps,
            standort_resolver=mock_resolver,
        )
        fotos = [FotoEintrag(1, "/foto1.jpg")]
        processor.batch_verarbeiten(fotos)

        mock_router.bild_analysieren.assert_called_once_with("/foto1.jpg", sd)

    def test_gps_error_graceful_degradation(self):
        """GPS-Fehler führt zu graceful degradation, nicht zu Abbruch."""
        mock_gps = MagicMock()
        mock_gps.gps_ermitteln.side_effect = RuntimeError("GPS kaputt")
        mock_resolver = MagicMock()
        mock_ollama = MagicMock()
        mock_ollama.analyse_bild.return_value = ["landscape"]

        processor = _make_processor(
            ollama=mock_ollama,
            gps_leser=mock_gps,
            standort_resolver=mock_resolver,
        )
        fotos = [FotoEintrag(1, "/foto1.jpg")]
        ergebnis = processor.batch_verarbeiten(fotos)

        # Photo still processed successfully (without standort)
        assert ergebnis.verarbeitet == 1
        assert ergebnis.fehler == 0
        mock_ollama.analyse_bild.assert_called_once_with("/foto1.jpg", None)

    def test_resolver_error_graceful_degradation(self):
        """Resolver-Fehler führt zu graceful degradation."""
        mock_gps = MagicMock()
        mock_gps.gps_ermitteln.return_value = (52.52, 13.405)
        mock_resolver = MagicMock()
        mock_resolver.standort_aufloesen.side_effect = RuntimeError("Resolver kaputt")
        mock_ollama = MagicMock()
        mock_ollama.analyse_bild.return_value = ["landscape"]

        processor = _make_processor(
            ollama=mock_ollama,
            gps_leser=mock_gps,
            standort_resolver=mock_resolver,
        )
        fotos = [FotoEintrag(1, "/foto1.jpg")]
        ergebnis = processor.batch_verarbeiten(fotos)

        assert ergebnis.verarbeitet == 1
        assert ergebnis.fehler == 0
        mock_ollama.analyse_bild.assert_called_once_with("/foto1.jpg", None)
