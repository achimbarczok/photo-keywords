"""Tests für StichwortSchreiber – Property-Tests und Unit-Tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from photo_keywords.errors import MetadataWriteError
from photo_keywords.stichwort_schreiber import StichwortSchreiber


# ------------------------------------------------------------------
# Strategien für Property-Tests
# ------------------------------------------------------------------

# Keywords: nicht-leere Strings ohne Kommas (realistische IPTC-Keywords)
keyword_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"),
        whitelist_characters="-_",
    ),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0)

keyword_set_strategy = st.frozensets(keyword_strategy, min_size=0, max_size=20)


# ------------------------------------------------------------------
# Property 4: Keyword-Zusammenführung ohne Datenverlust
# ------------------------------------------------------------------


class TestKeywordZusammenführungProperty:
    """**Validates: Requirements 3.2, 3.3**"""

    @given(
        vorhandene=keyword_set_strategy,
        neue=keyword_set_strategy,
    )
    @settings(max_examples=200)
    def test_ergebnis_ist_vereinigung(
        self, vorhandene: frozenset[str], neue: frozenset[str]
    ) -> None:
        """Property 4: Ergebnis = exakte Vereinigung beider Mengen.

        **Validates: Requirements 3.2, 3.3**
        """
        ergebnis = StichwortSchreiber._keywords_zusammenführen(
            set(vorhandene), set(neue)
        )
        assert ergebnis == set(vorhandene) | set(neue)

    @given(
        vorhandene=keyword_set_strategy,
        neue=keyword_set_strategy,
    )
    @settings(max_examples=200)
    def test_alle_vorhandenen_enthalten(
        self, vorhandene: frozenset[str], neue: frozenset[str]
    ) -> None:
        """Property 4: Alle vorhandenen Keywords bleiben erhalten.

        **Validates: Requirements 3.2, 3.3**
        """
        ergebnis = StichwortSchreiber._keywords_zusammenführen(
            set(vorhandene), set(neue)
        )
        assert set(vorhandene).issubset(ergebnis)

    @given(
        vorhandene=keyword_set_strategy,
        neue=keyword_set_strategy,
    )
    @settings(max_examples=200)
    def test_alle_neuen_enthalten(
        self, vorhandene: frozenset[str], neue: frozenset[str]
    ) -> None:
        """Property 4: Alle neuen Keywords sind im Ergebnis enthalten.

        **Validates: Requirements 3.2, 3.3**
        """
        ergebnis = StichwortSchreiber._keywords_zusammenführen(
            set(vorhandene), set(neue)
        )
        assert set(neue).issubset(ergebnis)

    @given(
        vorhandene=keyword_set_strategy,
        neue=keyword_set_strategy,
    )
    @settings(max_examples=200)
    def test_keine_duplikate(
        self, vorhandene: frozenset[str], neue: frozenset[str]
    ) -> None:
        """Property 4: Ergebnis enthält keine Duplikate (set-Eigenschaft).

        **Validates: Requirements 3.2, 3.3**
        """
        ergebnis = StichwortSchreiber._keywords_zusammenführen(
            set(vorhandene), set(neue)
        )
        # Ein set hat per Definition keine Duplikate;
        # prüfe, dass die Größe der Vereinigung stimmt
        assert len(ergebnis) == len(set(vorhandene) | set(neue))


# ------------------------------------------------------------------
# Unit-Tests: MetadataWriteError bei Schreibfehler (Task 8.3)
# ------------------------------------------------------------------


class TestMetadataWriteError:
    """Unit-Tests für MetadataWriteError-Verhalten.

    Anforderungen: 3.4
    """

    @patch("photo_keywords.stichwort_schreiber.subprocess.run")
    def test_schreibfehler_enthält_dateipfad(self, mock_run: MagicMock) -> None:
        """MetadataWriteError enthält den Dateipfad bei Schreibfehler."""
        mock_run.side_effect = RuntimeError("disk full")

        schreiber = StichwortSchreiber()
        test_path = r"C:\Fotos\test_bild.jpg"

        with pytest.raises(MetadataWriteError, match=r"test_bild\.jpg"):
            schreiber.stichwörter_schreiben(test_path, ["Landschaft", "Natur"])

    @patch("photo_keywords.stichwort_schreiber.subprocess.run")
    def test_schreibfehler_ist_metadata_write_error(
        self, mock_run: MagicMock
    ) -> None:
        """Schreibfehler wird als MetadataWriteError geworfen."""
        mock_run.side_effect = OSError("permission denied")

        schreiber = StichwortSchreiber()

        with pytest.raises(MetadataWriteError):
            schreiber.stichwörter_schreiben("/tmp/foto.jpg", ["Keyword"])
