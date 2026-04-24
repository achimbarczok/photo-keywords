"""Integrationstest: Benchmark mit Standort-CSV (Task 9.3).

BenchmarkRunner erzeugt CSV mit Standort-Spalte. GPS wird aus EXIF gelesen
(kein Katalog), Standort aufgelöst und als Spalte in die CSV geschrieben.
Standort-Kontext wird an analyse_bild() übergeben.

Mocks auf Modul-Ebene:
- photo_keywords.benchmark_runner.GpsLeser
- photo_keywords.benchmark_runner.StandortResolver
- photo_keywords.benchmark_runner.OllamaClient

Requirements: 6.1, 6.3, 6.5
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from photo_keywords.benchmark_runner import BenchmarkRunner
from photo_keywords.models import Config, StandortDaten


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> Config:
    """Creates a Config with sensible defaults for benchmark testing."""
    defaults = dict(
        catalog_path="dummy.lrcat",
        ollama_endpoint="http://localhost:11434",
        model_name="llava",
        batch_size=50,
        prompt_template="Describe this image with keywords.",
        tracking_db_path="./tracking.db",
        log_file_path="./test.log",
        exiftool_path=None,
        benchmark_models=["moondream"],
        benchmark_output_csv="./benchmark.csv",
    )
    defaults.update(overrides)
    return Config(**defaults)


def _create_test_images(directory: str, names: list[str]) -> list[str]:
    """Creates tiny dummy image files in the given directory."""
    paths = []
    for name in names:
        path = os.path.join(directory, name)
        with open(path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0")  # minimal JPEG header bytes
        paths.append(path)
    return paths


def _read_csv_rows(csv_path: str) -> list[dict[str, str]]:
    """Read CSV rows, skipping comment lines and blank lines."""
    with open(csv_path, "r", encoding="utf-8") as f:
        all_lines = f.readlines()

    filtered = [
        line for line in all_lines
        if not line.startswith("#") and line.strip() != ""
    ]
    reader = csv.DictReader(io.StringIO("".join(filtered)))
    return list(reader)


# ---------------------------------------------------------------------------
# Integration Test: Benchmark mit Standort-CSV
# ---------------------------------------------------------------------------

class TestBenchmarkMitStandortCsv:
    """Integration test: BenchmarkRunner produces CSV with standort column.

    Mocks GpsLeser, StandortResolver, and OllamaClient at the benchmark_runner
    module level so the runner's internal instantiation picks up the mocks.

    Validates: Requirements 6.1, 6.3, 6.5
    """

    def test_csv_has_standort_column_with_gps_and_without(self):
        """Images with GPS get standort string; images without GPS get empty standort.

        Validates: Req 6.1 (GPS aus EXIF), 6.3 (Standort-Kontext in Prompt), 6.5 (CSV-Spalte)
        """
        config = _make_config(benchmark_models=["moondream"])

        berlin_standort = StandortDaten(
            stadt="Berlin", region="Berlin", land="DE",
            breitengrad=52.52, laengengrad=13.405,
        )

        # --- Mock GpsLeser ---
        mock_gps_leser_instance = MagicMock()

        def gps_aus_exif_side_effect(image_path: str):
            if "berlin" in os.path.basename(image_path).lower():
                return (52.52, 13.405)
            return None  # no GPS for other images

        mock_gps_leser_instance.gps_aus_exif.side_effect = gps_aus_exif_side_effect
        MockGpsLeser = MagicMock(return_value=mock_gps_leser_instance)

        # --- Mock StandortResolver ---
        mock_resolver_instance = MagicMock()

        def standort_aufloesen_side_effect(breitengrad, laengengrad):
            if abs(breitengrad - 52.52) < 0.1:
                return berlin_standort
            return None

        mock_resolver_instance.standort_aufloesen.side_effect = standort_aufloesen_side_effect
        MockStandortResolver = MagicMock(return_value=mock_resolver_instance)

        # --- Mock OllamaClient ---
        class MockOllamaClient:
            def __init__(self, endpoint, model_name, prompt_template, **kwargs):
                self.model_name = model_name
                self.prompt_template = prompt_template
                self.calls = []

            def analyse_bild(self, image_path, standort_daten=None):
                self.calls.append((image_path, standort_daten))
                return ["keyword1", "keyword2"]

        # Track the OllamaClient instances created
        created_clients: list[MockOllamaClient] = []
        original_mock_client = MockOllamaClient

        def track_client(*args, **kwargs):
            client = original_mock_client(*args, **kwargs)
            created_clients.append(client)
            return client

        with tempfile.TemporaryDirectory() as img_dir, \
             tempfile.TemporaryDirectory() as csv_dir:
            csv_path = os.path.join(csv_dir, "benchmark.csv")
            _create_test_images(img_dir, ["berlin.jpg", "no_gps.jpg"])

            with patch("photo_keywords.benchmark_runner.GpsLeser", MockGpsLeser), \
                 patch("photo_keywords.benchmark_runner.StandortResolver", MockStandortResolver), \
                 patch("photo_keywords.benchmark_runner.OllamaClient", track_client):
                runner = BenchmarkRunner(config)
                runner.benchmark_ausfuehren(img_dir, csv_path)

            # Find the actual CSV file (timestamped)
            csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
            assert len(csv_files) == 1
            actual_csv = os.path.join(csv_dir, csv_files[0])

            rows = _read_csv_rows(actual_csv)

        # --- Verify CSV has standort column (Req 6.5) ---
        assert len(rows) == 2
        for row in rows:
            assert "standort" in row

        # Image with GPS has standort string
        berlin_row = next(r for r in rows if "berlin" in r["image"].lower())
        assert berlin_row["standort"] == "Berlin, DE"

        # Image without GPS has empty standort
        no_gps_row = next(r for r in rows if "no_gps" in r["image"].lower())
        assert no_gps_row["standort"] == ""

        # --- Verify GPS was read from EXIF for each image (Req 6.1) ---
        assert mock_gps_leser_instance.gps_aus_exif.call_count == 2

        # --- Verify standort_daten was passed to analyse_bild (Req 6.3) ---
        assert len(created_clients) == 1  # one model
        client = created_clients[0]
        assert len(client.calls) == 2

        # Berlin image: standort_daten should be the StandortDaten instance
        berlin_call = next(c for c in client.calls if "berlin" in c[0].lower())
        assert isinstance(berlin_call[1], StandortDaten)
        assert berlin_call[1].stadt == "Berlin"
        assert berlin_call[1].land == "DE"

        # No-GPS image: standort_daten should be None
        no_gps_call = next(c for c in client.calls if "no_gps" in c[0].lower())
        assert no_gps_call[1] is None

    def test_csv_standort_with_region(self):
        """Standort with distinct region shows 'stadt, region, land' format."""
        config = _make_config(benchmark_models=["moondream"])

        muenchen_standort = StandortDaten(
            stadt="München", region="Bayern", land="DE",
            breitengrad=48.14, laengengrad=11.58,
        )

        mock_gps = MagicMock()
        mock_gps.return_value.gps_aus_exif.return_value = (48.14, 11.58)

        mock_resolver = MagicMock()
        mock_resolver.return_value.standort_aufloesen.return_value = muenchen_standort

        class MockClient:
            def __init__(self, endpoint, model_name, prompt_template, **kwargs):
                pass

            def analyse_bild(self, image_path, standort_daten=None):
                return ["Alpen"]

        with tempfile.TemporaryDirectory() as img_dir, \
             tempfile.TemporaryDirectory() as csv_dir:
            csv_path = os.path.join(csv_dir, "bench.csv")
            _create_test_images(img_dir, ["muenchen.jpg"])

            with patch("photo_keywords.benchmark_runner.GpsLeser", mock_gps), \
                 patch("photo_keywords.benchmark_runner.StandortResolver", mock_resolver), \
                 patch("photo_keywords.benchmark_runner.OllamaClient", MockClient):
                runner = BenchmarkRunner(config)
                runner.benchmark_ausfuehren(img_dir, csv_path)

            csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
            assert len(csv_files) == 1
            rows = _read_csv_rows(os.path.join(csv_dir, csv_files[0]))

        assert len(rows) == 1
        assert rows[0]["standort"] == "München, Bayern, DE"

    def test_multiple_models_all_get_standort(self):
        """Multiple benchmark models all produce standort in CSV rows."""
        config = _make_config(benchmark_models=["moondream", "llava:7b"])

        standort = StandortDaten(
            stadt="Berlin", region="Berlin", land="DE",
            breitengrad=52.52, laengengrad=13.405,
        )

        mock_gps = MagicMock()
        mock_gps.return_value.gps_aus_exif.return_value = (52.52, 13.405)

        mock_resolver = MagicMock()
        mock_resolver.return_value.standort_aufloesen.return_value = standort

        class MockClient:
            def __init__(self, endpoint, model_name, prompt_template, **kwargs):
                pass

            def analyse_bild(self, image_path, standort_daten=None):
                return ["keyword"]

        with tempfile.TemporaryDirectory() as img_dir, \
             tempfile.TemporaryDirectory() as csv_dir:
            csv_path = os.path.join(csv_dir, "bench.csv")
            _create_test_images(img_dir, ["foto.jpg"])

            with patch("photo_keywords.benchmark_runner.GpsLeser", mock_gps), \
                 patch("photo_keywords.benchmark_runner.StandortResolver", mock_resolver), \
                 patch("photo_keywords.benchmark_runner.OllamaClient", MockClient):
                runner = BenchmarkRunner(config)
                runner.benchmark_ausfuehren(img_dir, csv_path)

            csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
            assert len(csv_files) == 1
            rows = _read_csv_rows(os.path.join(csv_dir, csv_files[0]))

        # 1 image × 2 models = 2 rows, both with standort
        assert len(rows) == 2
        for row in rows:
            assert row["standort"] == "Berlin, DE"
