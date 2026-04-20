"""Tests für BatchProcessor – Property-Tests und Unit-Tests."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from lightroom_ollama_keywords.batch_processor import BatchProcessor
from lightroom_ollama_keywords.models import FotoEintrag, BatchErgebnis
from lightroom_ollama_keywords.verarbeitungs_tracker import VerarbeitungsTracker


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _make_mock_ollama(keywords: list[str] | None = None):
    """Creates a mock OllamaClient that returns fixed keywords."""
    mock = MagicMock()
    mock.analyse_bild.return_value = keywords or ["landscape", "nature"]
    return mock


def _make_mock_schreiber():
    """Creates a mock StichwortSchreiber."""
    mock = MagicMock()
    mock.stichwörter_schreiben.return_value = None
    return mock


def _make_processor(
    ollama=None,
    schreiber=None,
    tracker=None,
    model_name="llava",
    model_version="1.0",
):
    return BatchProcessor(
        ollama=ollama or _make_mock_ollama(),
        schreiber=schreiber or _make_mock_schreiber(),
        tracker=tracker or MagicMock(),
        model_name=model_name,
        model_version=model_version,
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_foto_eintrag = st.builds(
    FotoEintrag,
    image_id=st.integers(min_value=1, max_value=10_000_000),
    file_path=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="/._-"),
        min_size=3,
        max_size=60,
    ).map(lambda s: "/" + s),
)


# ---------------------------------------------------------------------------
# Property 6: Batch-Größen-Begrenzung
# ---------------------------------------------------------------------------

class TestPropertyBatchGroessenBegrenzung:
    """Property 6: Batch-Größen-Begrenzung

    Für alle Foto-Listen und positive Batch-Größen: Anzahl verarbeiteter
    Fotos ≤ Batch-Größe.

    Mock-OllamaClient und Mock-StichwortSchreiber verwenden.

    **Validates: Requirement 5.1**
    """

    @given(
        fotos=st.lists(_foto_eintrag, min_size=0, max_size=50),
        batch_size=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100)
    def test_verarbeitete_fotos_kleiner_gleich_batch_groesse(self, fotos, batch_size):
        """The number of processed photos must be ≤ batch_size."""
        # Slice the list to batch_size (as main.py would do before calling batch_verarbeiten)
        batch = fotos[:batch_size]

        processor = _make_processor()
        ergebnis = processor.batch_verarbeiten(batch)

        assert ergebnis.verarbeitet <= batch_size
        assert ergebnis.verarbeitet + ergebnis.fehler == len(batch)


# ---------------------------------------------------------------------------
# Unit-Tests für BatchProcessor (Task 10.3)
# ---------------------------------------------------------------------------

class TestBatchProcessorHinweis:
    """Test: Hinweis 'Metadaten aus Datei lesen' wird ausgegeben.

    Requirements: 7.1
    """

    def test_hinweis_metadaten_aus_datei_lesen(self, capsys):
        fotos = [FotoEintrag(1, "/foto1.jpg")]
        processor = _make_processor()

        processor.batch_verarbeiten(fotos)

        captured = capsys.readouterr()
        assert "Metadaten aus Datei lesen" in captured.out


class TestBatchProcessorFehlerbehandlung:
    """Test: Fehler bei einzelnem Foto stoppt nicht die Batch-Verarbeitung.

    Requirements: 5.2, 5.3
    """

    def test_fehler_bei_einzelnem_foto_stoppt_nicht_batch(self, capsys):
        """If one photo fails, the remaining photos are still processed."""
        fotos = [
            FotoEintrag(1, "/foto1.jpg"),
            FotoEintrag(2, "/foto2.jpg"),
            FotoEintrag(3, "/foto3.jpg"),
        ]

        mock_ollama = _make_mock_ollama()
        # Second photo raises an error
        mock_ollama.analyse_bild.side_effect = [
            ["keyword1"],
            RuntimeError("Bild kaputt"),
            ["keyword3"],
        ]

        processor = _make_processor(ollama=mock_ollama)
        ergebnis = processor.batch_verarbeiten(fotos)

        # All three photos were attempted
        assert mock_ollama.analyse_bild.call_count == 3
        # Two succeeded, one failed
        assert ergebnis.verarbeitet == 2
        assert ergebnis.fehler == 1
        assert len(ergebnis.fehler_details) == 1
        assert "/foto2.jpg" in ergebnis.fehler_details[0]

    def test_leerer_batch(self, capsys):
        """An empty batch produces a valid result with zero counts."""
        processor = _make_processor()
        ergebnis = processor.batch_verarbeiten([])

        assert ergebnis.verarbeitet == 0
        assert ergebnis.fehler == 0
        assert ergebnis.fehler_details == []
        # Hint should still be shown
        captured = capsys.readouterr()
        assert "Metadaten aus Datei lesen" in captured.out


# ---------------------------------------------------------------------------
# Helpers for KlassifikationsRouter tests (Task 6.3)
# ---------------------------------------------------------------------------

from lightroom_ollama_keywords.models import FotoKategorie, KlassifikationsErgebnis


def _make_klassifikations_ergebnis(
    kategorie: FotoKategorie = FotoKategorie.LANDSCHAFT,
    keywords: list[str] | None = None,
    modell: str = "gemma4:e2b",
) -> KlassifikationsErgebnis:
    """Creates a KlassifikationsErgebnis for testing."""
    return KlassifikationsErgebnis(
        kategorie=kategorie,
        keywords=keywords or ["Sonnenuntergang", "Meer"],
        klassifikations_zeit_ms=150.0,
        keyword_zeit_ms=2500.0,
        verwendeter_prompt_typ=kategorie.value,
        verwendetes_modell=modell,
    )


def _make_mock_router(ergebnisse: list[KlassifikationsErgebnis] | KlassifikationsErgebnis | None = None):
    """Creates a mock KlassifikationsRouter."""
    mock = MagicMock()
    if ergebnisse is None:
        ergebnisse = _make_klassifikations_ergebnis()
    if isinstance(ergebnisse, list):
        mock.bild_analysieren.side_effect = ergebnisse
    else:
        mock.bild_analysieren.return_value = ergebnisse
    return mock


def _make_processor_with_router(
    router=None,
    ollama=None,
    schreiber=None,
    tracker=None,
    model_name="llava",
    model_version="1.0",
):
    return BatchProcessor(
        ollama=ollama or _make_mock_ollama(),
        schreiber=schreiber or _make_mock_schreiber(),
        tracker=tracker or MagicMock(),
        model_name=model_name,
        model_version=model_version,
        klassifikations_router=router,
    )


# ---------------------------------------------------------------------------
# Unit-Tests: BatchProcessor mit KlassifikationsRouter (Task 6.3)
# ---------------------------------------------------------------------------

class TestBatchProcessorMitRouter:
    """Tests für BatchProcessor mit KlassifikationsRouter.

    Requirements: 6.1, 6.2, 6.3
    """

    def test_delegiert_an_router_wenn_vorhanden(self):
        """Wenn KlassifikationsRouter vorhanden, wird bild_analysieren statt OllamaClient verwendet.

        Requirement 6.1
        """
        fotos = [FotoEintrag(1, "/foto1.jpg"), FotoEintrag(2, "/foto2.jpg")]
        mock_router = _make_mock_router()
        mock_ollama = _make_mock_ollama()

        processor = _make_processor_with_router(router=mock_router, ollama=mock_ollama)
        processor.batch_verarbeiten(fotos)

        # Router should be called for each photo (with standort_daten=None when no GPS configured)
        assert mock_router.bild_analysieren.call_count == 2
        mock_router.bild_analysieren.assert_any_call("/foto1.jpg", None)
        mock_router.bild_analysieren.assert_any_call("/foto2.jpg", None)
        # OllamaClient should NOT be called directly
        mock_ollama.analyse_bild.assert_not_called()

    def test_ohne_router_verwendet_ollama_direkt(self):
        """Ohne KlassifikationsRouter wird OllamaClient direkt verwendet.

        Requirement 6.1 (Rückwärtskompatibilität)
        """
        fotos = [FotoEintrag(1, "/foto1.jpg")]
        mock_ollama = _make_mock_ollama()

        processor = _make_processor_with_router(router=None, ollama=mock_ollama)
        processor.batch_verarbeiten(fotos)

        mock_ollama.analyse_bild.assert_called_once_with("/foto1.jpg", None)

    def test_konsole_zeigt_kategorie_und_modell_pro_foto(self, capsys):
        """Konsolenausgabe enthält Kategorie und Modell pro Foto.

        Requirement 6.2
        """
        fotos = [FotoEintrag(1, "/landschaft.jpg")]
        mock_router = _make_mock_router(
            _make_klassifikations_ergebnis(
                kategorie=FotoKategorie.LANDSCHAFT,
                modell="gemma4:e2b",
            )
        )

        processor = _make_processor_with_router(router=mock_router)
        processor.batch_verarbeiten(fotos)

        captured = capsys.readouterr()
        assert "Kategorie: Landschaft" in captured.out
        assert "Modell: gemma4:e2b" in captured.out

    def test_konsole_zeigt_verschiedene_kategorien(self, capsys):
        """Konsolenausgabe zeigt verschiedene Kategorien für verschiedene Fotos.

        Requirement 6.2
        """
        fotos = [
            FotoEintrag(1, "/landschaft.jpg"),
            FotoEintrag(2, "/portrait.jpg"),
            FotoEintrag(3, "/architektur.jpg"),
        ]
        ergebnisse = [
            _make_klassifikations_ergebnis(kategorie=FotoKategorie.LANDSCHAFT, modell="gemma4:e2b"),
            _make_klassifikations_ergebnis(kategorie=FotoKategorie.PORTRAET, modell="gemma4:e4b"),
            _make_klassifikations_ergebnis(kategorie=FotoKategorie.ARCHITEKTUR, modell="gemma4:e2b"),
        ]
        mock_router = _make_mock_router(ergebnisse)

        processor = _make_processor_with_router(router=mock_router)
        processor.batch_verarbeiten(fotos)

        captured = capsys.readouterr()
        assert "Kategorie: Landschaft" in captured.out
        assert "Kategorie: Porträt" in captured.out
        assert "Kategorie: Architektur" in captured.out

    def test_zusammenfassung_enthaelt_kategorie_statistik(self, capsys):
        """Zusammenfassung enthält Anzahl Fotos pro Kategorie.

        Requirement 6.3
        """
        fotos = [
            FotoEintrag(1, "/foto1.jpg"),
            FotoEintrag(2, "/foto2.jpg"),
            FotoEintrag(3, "/foto3.jpg"),
            FotoEintrag(4, "/foto4.jpg"),
        ]
        ergebnisse = [
            _make_klassifikations_ergebnis(kategorie=FotoKategorie.LANDSCHAFT),
            _make_klassifikations_ergebnis(kategorie=FotoKategorie.LANDSCHAFT),
            _make_klassifikations_ergebnis(kategorie=FotoKategorie.PORTRAET),
            _make_klassifikations_ergebnis(kategorie=FotoKategorie.ARCHITEKTUR),
        ]
        mock_router = _make_mock_router(ergebnisse)

        processor = _make_processor_with_router(router=mock_router)
        processor.batch_verarbeiten(fotos)

        captured = capsys.readouterr()
        assert "Fotos pro Kategorie:" in captured.out
        assert "Landschaft: 2" in captured.out
        assert "Porträt: 1" in captured.out
        assert "Architektur: 1" in captured.out

    def test_zusammenfassung_ohne_router_keine_kategorie_statistik(self, capsys):
        """Ohne Router wird keine Kategorie-Statistik ausgegeben.

        Requirement 6.3 (Rückwärtskompatibilität)
        """
        fotos = [FotoEintrag(1, "/foto1.jpg")]
        processor = _make_processor_with_router(router=None)
        processor.batch_verarbeiten(fotos)

        captured = capsys.readouterr()
        assert "Fotos pro Kategorie:" not in captured.out

    def test_router_fehler_wird_in_fehler_details_erfasst(self):
        """Wenn der Router einen Fehler wirft, wird er in fehler_details erfasst.

        Requirement 6.1
        """
        fotos = [FotoEintrag(1, "/foto1.jpg"), FotoEintrag(2, "/foto2.jpg")]
        mock_router = MagicMock()
        mock_router.bild_analysieren.side_effect = [
            RuntimeError("Router-Fehler"),
            _make_klassifikations_ergebnis(),
        ]

        processor = _make_processor_with_router(router=mock_router)
        ergebnis = processor.batch_verarbeiten(fotos)

        assert ergebnis.verarbeitet == 1
        assert ergebnis.fehler == 1
        assert "/foto1.jpg" in ergebnis.fehler_details[0]
