"""Integrationstests für den Lightroom Ollama Keyword Generator.

- 14.1: Ollama-Kommunikation (Mock-HTTP-Server)
- 14.2: End-to-End Batch (Katalog → Filter → Analyse → Schreiben → Tracken)
- 14.3: Benchmark End-to-End (mehrere Modelle, CSV-Validierung)
"""

from __future__ import annotations

import base64
import csv
import glob
import io
import json
import os
import sqlite3
import struct
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock

import pytest

from lightroom_ollama_keywords.batch_processor import BatchProcessor
from lightroom_ollama_keywords.benchmark_runner import BenchmarkRunner
from lightroom_ollama_keywords.katalog_leser import KatalogLeser
from lightroom_ollama_keywords.models import Config, FotoEintrag
from lightroom_ollama_keywords.ollama_client import OllamaClient
from lightroom_ollama_keywords.verarbeitungs_tracker import VerarbeitungsTracker


# ---------------------------------------------------------------------------
# Mock Ollama HTTP Server
# ---------------------------------------------------------------------------

class MockOllamaHandler(BaseHTTPRequestHandler):
    """Mock handler that mimics the Ollama REST API."""

    # Class-level storage for captured requests and configurable responses
    captured_requests: list[dict] = []
    response_keywords: str = "landscape, nature, sunset"

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        if self.path == "/api/generate":
            # Store the request for later assertions
            MockOllamaHandler.captured_requests.append(data)

            response = {
                "model": data.get("model", "unknown"),
                "created_at": "2024-01-01T00:00:00Z",
                "response": MockOllamaHandler.response_keywords,
                "done": True,
            }
            self._send_json(200, response)

        elif self.path == "/api/show":
            response = {
                "model_info": {
                    "general.parameter_count": "7000000000",
                },
            }
            self._send_json(200, response)

        else:
            self.send_error(404)

    def _send_json(self, status: int, data: dict) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        """Suppress request logging during tests."""
        pass


@pytest.fixture
def mock_ollama_server():
    """Start a mock Ollama HTTP server on a random port."""
    MockOllamaHandler.captured_requests = []
    MockOllamaHandler.response_keywords = "landscape, nature, sunset"

    server = HTTPServer(("127.0.0.1", 0), MockOllamaHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------------------------------------------------------------------------
# Helpers: Minimal JPEG and test catalog
# ---------------------------------------------------------------------------

def _create_minimal_jpeg(path: str) -> None:
    """Create a minimal valid JPEG file (smallest possible)."""
    # Minimal JPEG: SOI + APP0 (JFIF) + SOF0 + SOS + EOI
    # This is a 1x1 pixel white JPEG
    jpeg_bytes = bytes([
        0xFF, 0xD8,  # SOI
        0xFF, 0xE0,  # APP0
        0x00, 0x10,  # Length
        0x4A, 0x46, 0x49, 0x46, 0x00,  # JFIF\0
        0x01, 0x01,  # Version
        0x00,        # Units
        0x00, 0x01,  # X density
        0x00, 0x01,  # Y density
        0x00, 0x00,  # Thumbnail
        0xFF, 0xDB,  # DQT
        0x00, 0x43,  # Length
        0x00,        # Table ID
    ] + [0x01] * 64 + [  # Quantization table
        0xFF, 0xC0,  # SOF0
        0x00, 0x0B,  # Length
        0x08,        # Precision
        0x00, 0x01,  # Height
        0x00, 0x01,  # Width
        0x01,        # Components
        0x01, 0x11, 0x00,  # Component 1
        0xFF, 0xC4,  # DHT
        0x00, 0x1F,  # Length
        0x00,        # Table class/ID
        0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01,
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
        0x08, 0x09, 0x0A, 0x0B,
        0xFF, 0xDA,  # SOS
        0x00, 0x08,  # Length
        0x01,        # Components
        0x01, 0x00,  # Component 1
        0x00, 0x3F, 0x00,  # Spectral selection
        0x7B, 0x40,  # Compressed data
        0xFF, 0xD9,  # EOI
    ])
    with open(path, "wb") as f:
        f.write(jpeg_bytes)


def _create_lightroom_catalog(db_path: str, fotos: list[dict]) -> None:
    """Create a minimal Lightroom catalog SQLite DB with the required schema.

    Each foto dict should have: root_path, folder_path, base_name, extension
    """
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE AgLibraryRootFolder (
            id_local INTEGER PRIMARY KEY,
            absolutePath TEXT NOT NULL
        );
        CREATE TABLE AgLibraryFolder (
            id_local INTEGER PRIMARY KEY,
            pathFromRoot TEXT NOT NULL,
            rootFolder INTEGER NOT NULL
        );
        CREATE TABLE AgLibraryFile (
            id_local INTEGER PRIMARY KEY,
            baseName TEXT NOT NULL,
            extension TEXT NOT NULL,
            folder INTEGER NOT NULL
        );
        CREATE TABLE Adobe_images (
            id_local INTEGER PRIMARY KEY,
            rootFile INTEGER NOT NULL
        );
    """)

    for i, foto in enumerate(fotos, start=1):
        root_id = i
        folder_id = i
        file_id = i
        image_id = i

        conn.execute(
            "INSERT INTO AgLibraryRootFolder (id_local, absolutePath) VALUES (?, ?)",
            (root_id, foto["root_path"]),
        )
        conn.execute(
            "INSERT INTO AgLibraryFolder (id_local, pathFromRoot, rootFolder) VALUES (?, ?, ?)",
            (folder_id, foto["folder_path"], root_id),
        )
        conn.execute(
            "INSERT INTO AgLibraryFile (id_local, baseName, extension, folder) VALUES (?, ?, ?, ?)",
            (file_id, foto["base_name"], foto["extension"], folder_id),
        )
        conn.execute(
            "INSERT INTO Adobe_images (id_local, rootFile) VALUES (?, ?)",
            (image_id, file_id),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# 14.1 Integrationstest: Ollama-Kommunikation
# Validates: Requirements 2.1, 2.2
# ---------------------------------------------------------------------------

class TestOllamaKommunikation:
    """Integration test: OllamaClient communicates correctly with a mock HTTP server."""

    def test_request_response_cycle(self, mock_ollama_server, tmp_path):
        """OllamaClient sends correct POST /api/generate and parses the response."""
        # Create a small test image
        image_path = str(tmp_path / "test.jpg")
        _create_minimal_jpeg(image_path)

        client = OllamaClient(
            endpoint=mock_ollama_server,
            model_name="llava",
            prompt_template="Describe this image with keywords.",
        )

        keywords = client.analyse_bild(image_path)

        # Verify the response was parsed correctly
        assert keywords == ["landscape", "nature", "sunset"]

        # Verify the request was correct
        assert len(MockOllamaHandler.captured_requests) == 1
        req = MockOllamaHandler.captured_requests[0]
        assert req["model"] == "llava"
        assert req["prompt"] == "Describe this image with keywords."
        assert req["stream"] is False
        assert len(req["images"]) == 1

        # Verify the image was sent as valid base64
        decoded = base64.b64decode(req["images"][0])
        assert decoded[:2] == b"\xff\xd8"  # JPEG magic bytes

    def test_modell_version_abfragen(self, mock_ollama_server):
        """OllamaClient can query model version via /api/show."""
        client = OllamaClient(
            endpoint=mock_ollama_server,
            model_name="llava",
            prompt_template="test",
        )

        version = client.modell_version_abfragen()
        assert version == "7000000000"


# ---------------------------------------------------------------------------
# 14.2 Integrationstest: End-to-End Batch
# Validates: Requirements 1.1, 1.2, 2.1, 3.1, 4.1, 5.1
# ---------------------------------------------------------------------------

class TestEndToEndBatch:
    """Integration test: Full pipeline from catalog read to tracking."""

    def test_full_batch_run(self, mock_ollama_server, tmp_path):
        """Full run: Read catalog → filter → analyze → write keywords → track."""
        # 1. Create test images
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        image_names = ["foto1.jpg", "foto2.jpg", "foto3.jpg"]
        for name in image_names:
            _create_minimal_jpeg(str(images_dir / name))

        # 2. Create a test Lightroom catalog
        catalog_path = str(tmp_path / "test_catalog.lrcat")
        fotos_data = []
        for name in image_names:
            base, ext = os.path.splitext(name)
            fotos_data.append({
                "root_path": str(images_dir) + "/",
                "folder_path": "",
                "base_name": base,
                "extension": ext.lstrip("."),
            })
        _create_lightroom_catalog(catalog_path, fotos_data)

        # 3. Read catalog
        katalog = KatalogLeser(catalog_path)
        fotos = katalog.alle_fotos_lesen()
        katalog.close()

        assert len(fotos) == 3
        for foto in fotos:
            assert os.path.basename(foto.file_path) in image_names

        # 4. Create tracker and filter (all should be unprocessed)
        tracker_path = str(tmp_path / "tracking.db")
        tracker = VerarbeitungsTracker(tracker_path)
        unverarbeitet = tracker.unverarbeitete_filtern(fotos, "llava")
        assert len(unverarbeitet) == 3

        # 5. Create OllamaClient pointing to mock server
        ollama = OllamaClient(
            endpoint=mock_ollama_server,
            model_name="llava",
            prompt_template="Describe this image.",
        )

        # 6. Mock the StichwortSchreiber (ExifTool may not be available)
        mock_schreiber = MagicMock()
        mock_schreiber.stichwörter_schreiben = MagicMock()

        # 7. Run batch processing
        batch_size = 3
        batch = unverarbeitet[:batch_size]
        processor = BatchProcessor(
            ollama=ollama,
            schreiber=mock_schreiber,
            tracker=tracker,
            model_name="llava",
            model_version="1.0",
        )
        ergebnis = processor.batch_verarbeiten(batch)

        # 8. Verify results
        assert ergebnis.verarbeitet == 3
        assert ergebnis.fehler == 0

        # 9. Verify StichwortSchreiber was called for each photo
        assert mock_schreiber.stichwörter_schreiben.call_count == 3

        # 10. Verify tracking: all photos should now be marked as processed
        for foto in fotos:
            assert tracker.ist_verarbeitet(foto.file_path, "llava")

        # 11. Re-filter: no unprocessed photos should remain
        noch_unverarbeitet = tracker.unverarbeitete_filtern(fotos, "llava")
        assert len(noch_unverarbeitet) == 0

        # 12. Different model should still show all as unprocessed
        andere_modell = tracker.unverarbeitete_filtern(fotos, "bakllava")
        assert len(andere_modell) == 3

        tracker.close()

    def test_batch_respects_batch_size(self, mock_ollama_server, tmp_path):
        """Batch processing respects the configured batch_size limit."""
        # Create 5 test images
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        image_names = [f"foto{i}.jpg" for i in range(5)]
        for name in image_names:
            _create_minimal_jpeg(str(images_dir / name))

        # Create catalog with 5 photos
        catalog_path = str(tmp_path / "test_catalog.lrcat")
        fotos_data = []
        for name in image_names:
            base, ext = os.path.splitext(name)
            fotos_data.append({
                "root_path": str(images_dir) + "/",
                "folder_path": "",
                "base_name": base,
                "extension": ext.lstrip("."),
            })
        _create_lightroom_catalog(catalog_path, fotos_data)

        katalog = KatalogLeser(catalog_path)
        fotos = katalog.alle_fotos_lesen()
        katalog.close()

        tracker_path = str(tmp_path / "tracking.db")
        tracker = VerarbeitungsTracker(tracker_path)
        unverarbeitet = tracker.unverarbeitete_filtern(fotos, "llava")

        # Limit batch to 2
        batch_size = 2
        batch = unverarbeitet[:batch_size]

        ollama = OllamaClient(
            endpoint=mock_ollama_server,
            model_name="llava",
            prompt_template="Describe.",
        )
        mock_schreiber = MagicMock()

        processor = BatchProcessor(
            ollama=ollama,
            schreiber=mock_schreiber,
            tracker=tracker,
            model_name="llava",
            model_version="1.0",
        )
        ergebnis = processor.batch_verarbeiten(batch)

        assert ergebnis.verarbeitet == 2
        # 3 should still be unprocessed
        noch_unverarbeitet = tracker.unverarbeitete_filtern(fotos, "llava")
        assert len(noch_unverarbeitet) == 3

        tracker.close()


# ---------------------------------------------------------------------------
# 14.3 Integrationstest: Benchmark End-to-End
# Validates: Requirements 9.1, 9.2, 9.4
# ---------------------------------------------------------------------------

class TestBenchmarkEndToEnd:
    """Integration test: Full benchmark run with mock Ollama and CSV validation."""

    def test_benchmark_full_run(self, mock_ollama_server, tmp_path):
        """Benchmark: multiple models, test images, CSV output validated."""
        # Create test images directory
        images_dir = tmp_path / "benchmark_images"
        images_dir.mkdir()
        image_names = ["img1.jpg", "img2.jpg"]
        for name in image_names:
            _create_minimal_jpeg(str(images_dir / name))

        output_csv = str(tmp_path / "benchmark_results.csv")

        config = Config(
            catalog_path="unused",
            ollama_endpoint=mock_ollama_server,
            model_name="llava",
            batch_size=50,
            prompt_template="Describe this image with keywords.",
            tracking_db_path="unused",
            log_file_path=str(tmp_path / "test.log"),
            exiftool_path=None,
            benchmark_models=["model-a", "model-b"],
            benchmark_output_csv=output_csv,
        )

        runner = BenchmarkRunner(config)
        zusammenfassungen = runner.benchmark_ausfuehren(
            str(images_dir), output_csv
        )

        # Verify summaries
        assert len(zusammenfassungen) == 2
        model_names = {z.model_name for z in zusammenfassungen}
        assert model_names == {"model-a", "model-b"}

        for z in zusammenfassungen:
            assert z.bilder_verarbeitet == 2
            assert z.fehler == 0
            assert z.durchschnitt_ms > 0

        # Verify CSV output — file now has a timestamped name
        pattern = str(tmp_path / "benchmark_results_*.csv")
        matched_files = glob.glob(pattern)
        assert len(matched_files) == 1, f"Expected 1 timestamped CSV, found {matched_files}"
        actual_csv = matched_files[0]

        with open(actual_csv, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        # Filter out comment lines and blank lines, then parse with csv
        data_lines = [l for l in raw_lines if l.strip() and not l.startswith("#")]
        reader = csv.DictReader(io.StringIO("".join(data_lines)))
        data_rows = list(reader)

        # 2 models × 2 images = 4 data rows
        assert len(data_rows) == 4

        models_in_csv = {row["model"] for row in data_rows}
        assert models_in_csv == {"model-a", "model-b"}

        images_in_csv = {row["image"] for row in data_rows}
        assert images_in_csv == {"img1.jpg", "img2.jpg"}

        # Keywords should be semicolon-separated
        for row in data_rows:
            keywords = row["keywords"].split(";")
            assert len(keywords) == 3  # landscape, nature, sunset
            assert "landscape" in keywords

            # Response time should be a positive number
            response_time = float(row["response_time_ms"])
            assert response_time > 0

    def test_benchmark_requests_use_correct_models(self, mock_ollama_server, tmp_path):
        """Each model in the benchmark sends requests with its own model name."""
        images_dir = tmp_path / "benchmark_images"
        images_dir.mkdir()
        _create_minimal_jpeg(str(images_dir / "test.jpg"))

        output_csv = str(tmp_path / "results.csv")

        config = Config(
            catalog_path="unused",
            ollama_endpoint=mock_ollama_server,
            model_name="llava",
            batch_size=50,
            prompt_template="Test prompt.",
            tracking_db_path="unused",
            log_file_path=str(tmp_path / "test.log"),
            exiftool_path=None,
            benchmark_models=["alpha", "beta", "gamma"],
            benchmark_output_csv=output_csv,
        )

        MockOllamaHandler.captured_requests = []

        runner = BenchmarkRunner(config)
        runner.benchmark_ausfuehren(str(images_dir), output_csv)

        # 3 models × 1 image = 3 requests
        assert len(MockOllamaHandler.captured_requests) == 3

        requested_models = [r["model"] for r in MockOllamaHandler.captured_requests]
        assert "alpha" in requested_models
        assert "beta" in requested_models
        assert "gamma" in requested_models

        # All requests should use the same prompt
        prompts = {r["prompt"] for r in MockOllamaHandler.captured_requests}
        assert prompts == {"Test prompt."}
