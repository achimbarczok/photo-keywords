"""Unit-Tests für VerarbeitungsTracker."""

import os
import sqlite3

import pytest

from photo_keywords.errors import TrackerError
from photo_keywords.models import FotoEintrag
from photo_keywords.verarbeitungs_tracker import VerarbeitungsTracker


class TestVerarbeitungsTrackerInit:
    """Tests für die Initialisierung des VerarbeitungsTrackers."""

    def test_erstellt_datenbank(self, tmp_path):
        db_path = str(tmp_path / "tracking.db")
        tracker = VerarbeitungsTracker(db_path)
        assert os.path.exists(db_path)
        tracker.close()

    def test_erstellt_schema(self, tmp_path):
        db_path = str(tmp_path / "tracking.db")
        tracker = VerarbeitungsTracker(db_path)
        tracker.close()

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='verarbeitungen'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_tracker_error_bei_nicht_zugreifbarem_pfad(self):
        bad_path = "/nicht/existierender/pfad/tracking.db"
        with pytest.raises(TrackerError, match=bad_path):
            VerarbeitungsTracker(bad_path)


class TestIstVerarbeitet:
    """Tests für ist_verarbeitet."""

    def test_false_fuer_neues_foto(self, tmp_path):
        tracker = VerarbeitungsTracker(str(tmp_path / "t.db"))
        assert tracker.ist_verarbeitet("/foto.jpg", "llava") is False
        tracker.close()

    def test_true_nach_speichern(self, tmp_path):
        tracker = VerarbeitungsTracker(str(tmp_path / "t.db"))
        tracker.verarbeitung_speichern("/foto.jpg", "llava", "1.0")
        assert tracker.ist_verarbeitet("/foto.jpg", "llava") is True
        tracker.close()


class TestUnverarbeiteteFiltern:
    """Tests für unverarbeitete_filtern."""

    def test_alle_unverarbeitet(self, tmp_path):
        tracker = VerarbeitungsTracker(str(tmp_path / "t.db"))
        fotos = [FotoEintrag(1, "/a.jpg"), FotoEintrag(2, "/b.jpg")]
        result = tracker.unverarbeitete_filtern(fotos, "llava")
        assert result == fotos
        tracker.close()

    def test_teilweise_verarbeitet(self, tmp_path):
        tracker = VerarbeitungsTracker(str(tmp_path / "t.db"))
        tracker.verarbeitung_speichern("/a.jpg", "llava", "1.0")
        fotos = [FotoEintrag(1, "/a.jpg"), FotoEintrag(2, "/b.jpg")]
        result = tracker.unverarbeitete_filtern(fotos, "llava")
        assert result == [FotoEintrag(2, "/b.jpg")]
        tracker.close()


class TestVerarbeitungSpeichern:
    """Tests für verarbeitung_speichern."""

    def test_speichert_eintrag(self, tmp_path):
        tracker = VerarbeitungsTracker(str(tmp_path / "t.db"))
        tracker.verarbeitung_speichern("/foto.jpg", "llava", "1.0")
        assert tracker.ist_verarbeitet("/foto.jpg", "llava") is True
        tracker.close()

    def test_insert_or_replace_aktualisiert(self, tmp_path):
        db_path = str(tmp_path / "t.db")
        tracker = VerarbeitungsTracker(db_path)
        tracker.verarbeitung_speichern("/foto.jpg", "llava", "1.0")
        tracker.verarbeitung_speichern("/foto.jpg", "llava", "2.0")

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT model_version FROM verarbeitungen WHERE file_path=? AND model_name=?",
            ("/foto.jpg", "llava"),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "2.0"
        conn.close()
        tracker.close()


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# ---------------------------------------------------------------------------
import tempfile

from hypothesis import given, settings
from hypothesis import strategies as st


# -- Strategies for generating FotoEintrag objects and model names --

_model_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=20,
)

_file_paths = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="/._-"),
    min_size=3,
    max_size=80,
).map(lambda s: "/" + s)

_foto_eintrag = st.builds(
    FotoEintrag,
    image_id=st.integers(min_value=1, max_value=10_000_000),
    file_path=_file_paths,
)


class TestPropertyUnverarbeiteteFilterung:
    """Property 2: Unverarbeitete-Fotos-Filterung

    Für alle Foto-Listen und Tracking-Einträge: Filterung gibt genau die
    Fotos ohne passenden Tracking-Eintrag für den aktuellen Modellnamen zurück.

    **Validates: Requirements 1.2, 1.3**
    """

    @given(
        fotos=st.lists(_foto_eintrag, min_size=0, max_size=30).filter(
            lambda lst: len({f.file_path for f in lst}) == len(lst)
        ),
        model_name=_model_names,
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_filterung_gibt_komplement_zurueck(self, fotos, model_name, data):
        """The result of unverarbeitete_filtern is exactly the complement of
        the processed subset with respect to the input list."""

        # Pick a random subset of fotos to mark as processed
        if fotos:
            processed_indices = data.draw(
                st.lists(
                    st.integers(min_value=0, max_value=len(fotos) - 1),
                    unique=True,
                    max_size=len(fotos),
                )
            )
        else:
            processed_indices = []

        processed_fotos = [fotos[i] for i in processed_indices]
        expected_unprocessed = [f for f in fotos if f not in processed_fotos]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "prop2.db")
            tracker = VerarbeitungsTracker(db_path)
            try:
                # Save the processed subset
                for foto in processed_fotos:
                    tracker.verarbeitung_speichern(foto.file_path, model_name, "1.0")

                result = tracker.unverarbeitete_filtern(fotos, model_name)

                # 1) Result is a subset of the input list
                assert all(f in fotos for f in result)

                # 2) No photo in the result has a matching tracking entry
                for f in result:
                    assert not tracker.ist_verarbeitet(f.file_path, model_name)

                # 3) Result is exactly the complement
                assert result == expected_unprocessed
            finally:
                tracker.close()


class TestPropertyTrackingRoundTripModellspezifitaet:
    """Property 5: Tracking Round-Trip mit Modellspezifität

    Für alle gültigen Dateipfade und Paare von unterschiedlichen Modellnamen:
    - Nach Speichern mit Modell A: ist_verarbeitet(foto, A) == True, ist_verarbeitet(foto, B) == False
    - Nach zusätzlichem Speichern mit Modell B: ist_verarbeitet gibt True für beide Modelle zurück

    **Validates: Requirements 4.1, 4.3, 4.4**
    """

    @given(
        file_path=_file_paths,
        model_a=_model_names,
        model_b=_model_names,
    )
    @settings(max_examples=100)
    def test_round_trip_mit_modellspezifitaet(self, file_path, model_a, model_b):
        """After saving with model A, only model A is tracked.
        After additionally saving with model B, both are tracked."""
        from hypothesis import assume

        assume(model_a != model_b)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "prop5.db")
            tracker = VerarbeitungsTracker(db_path)
            try:
                # Before any save: neither model is tracked
                assert tracker.ist_verarbeitet(file_path, model_a) is False
                assert tracker.ist_verarbeitet(file_path, model_b) is False

                # Save with model A
                tracker.verarbeitung_speichern(file_path, model_a, "1.0")

                # Model A is tracked, model B is NOT
                assert tracker.ist_verarbeitet(file_path, model_a) is True
                assert tracker.ist_verarbeitet(file_path, model_b) is False

                # Additionally save with model B
                tracker.verarbeitung_speichern(file_path, model_b, "2.0")

                # Both models are now tracked
                assert tracker.ist_verarbeitet(file_path, model_a) is True
                assert tracker.ist_verarbeitet(file_path, model_b) is True
            finally:
                tracker.close()
