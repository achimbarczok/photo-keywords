"""Tests für die Datenklassen in models.py."""

import dataclasses

from photo_keywords.models import (
    BatchErgebnis,
    BenchmarkErgebnis,
    BenchmarkZusammenfassung,
    Config,
    FotoEintrag,
    VerarbeitungsEintrag,
)


class TestConfig:
    def test_erstellen(self):
        config = Config(
            catalog_path="/pfad/katalog.lrcat",
            ollama_endpoint="http://localhost:11434",
            model_name="llava",
            batch_size=50,
            prompt_template="Describe this image.",
            tracking_db_path="./tracking.db",
            log_file_path="./log.txt",
            exiftool_path=None,
            benchmark_models=["llava", "bakllava"],
            benchmark_output_csv="./benchmark.csv",
        )
        assert config.catalog_path == "/pfad/katalog.lrcat"
        assert config.model_name == "llava"
        assert config.batch_size == 50
        assert config.exiftool_path is None
        assert config.benchmark_models == ["llava", "bakllava"]

    def test_exiftool_path_mit_wert(self):
        config = Config(
            catalog_path="k.lrcat",
            ollama_endpoint="http://localhost:11434",
            model_name="llava",
            batch_size=10,
            prompt_template="prompt",
            tracking_db_path="t.db",
            log_file_path="l.log",
            exiftool_path="/usr/bin/exiftool",
            benchmark_models=[],
            benchmark_output_csv="out.csv",
        )
        assert config.exiftool_path == "/usr/bin/exiftool"

    def test_ist_dataclass(self):
        assert dataclasses.is_dataclass(Config)


class TestFotoEintrag:
    def test_erstellen(self):
        foto = FotoEintrag(image_id=42, file_path="/fotos/bild.jpg")
        assert foto.image_id == 42
        assert foto.file_path == "/fotos/bild.jpg"

    def test_ist_dataclass(self):
        assert dataclasses.is_dataclass(FotoEintrag)


class TestVerarbeitungsEintrag:
    def test_erstellen(self):
        eintrag = VerarbeitungsEintrag(
            file_path="/fotos/bild.jpg",
            model_name="llava",
            model_version="1.0",
            timestamp="2024-01-15T10:30:00Z",
        )
        assert eintrag.file_path == "/fotos/bild.jpg"
        assert eintrag.model_name == "llava"
        assert eintrag.model_version == "1.0"
        assert eintrag.timestamp == "2024-01-15T10:30:00Z"

    def test_ist_dataclass(self):
        assert dataclasses.is_dataclass(VerarbeitungsEintrag)


class TestBatchErgebnis:
    def test_erstellen(self):
        ergebnis = BatchErgebnis(
            verarbeitet=10,
            fehler=2,
            dauer_sekunden=45.5,
            fehler_details=["Fehler bei bild1.jpg", "Fehler bei bild2.jpg"],
        )
        assert ergebnis.verarbeitet == 10
        assert ergebnis.fehler == 2
        assert ergebnis.dauer_sekunden == 45.5
        assert len(ergebnis.fehler_details) == 2

    def test_ist_dataclass(self):
        assert dataclasses.is_dataclass(BatchErgebnis)


class TestBenchmarkErgebnis:
    def test_erstellen_ohne_fehler(self):
        ergebnis = BenchmarkErgebnis(
            model_name="llava",
            image_name="sunset.jpg",
            keywords=["sunset", "beach", "ocean"],
            response_time_ms=1234.5,
        )
        assert ergebnis.model_name == "llava"
        assert ergebnis.image_name == "sunset.jpg"
        assert ergebnis.keywords == ["sunset", "beach", "ocean"]
        assert ergebnis.response_time_ms == 1234.5
        assert ergebnis.error is None

    def test_erstellen_mit_fehler(self):
        ergebnis = BenchmarkErgebnis(
            model_name="llava",
            image_name="broken.jpg",
            keywords=[],
            response_time_ms=0.0,
            error="Modell nicht verfügbar",
        )
        assert ergebnis.error == "Modell nicht verfügbar"

    def test_ist_dataclass(self):
        assert dataclasses.is_dataclass(BenchmarkErgebnis)


class TestBenchmarkZusammenfassung:
    def test_erstellen(self):
        zusammenfassung = BenchmarkZusammenfassung(
            model_name="llava",
            bilder_verarbeitet=10,
            durchschnitt_ms=1500.0,
            fehler=1,
        )
        assert zusammenfassung.model_name == "llava"
        assert zusammenfassung.bilder_verarbeitet == 10
        assert zusammenfassung.durchschnitt_ms == 1500.0
        assert zusammenfassung.fehler == 1

    def test_ist_dataclass(self):
        assert dataclasses.is_dataclass(BenchmarkZusammenfassung)
