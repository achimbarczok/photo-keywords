"""Integrationstests für Klassifikation + Routing.

- Klassifikation + Stichwörter End-to-End mit Mock-Ollama
- Benchmark mit aktivierter Klassifikation, CSV-Validierung
- Benchmark ohne Klassifikation: Rückwärtskompatibilität

Requirements: 6.1, 7.1, 4.3
"""

from __future__ import annotations

import csv
import glob
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock

import pytest

from lightroom_ollama_keywords.batch_processor import BatchProcessor
from lightroom_ollama_keywords.benchmark_runner import BenchmarkRunner
from lightroom_ollama_keywords.klassifikations_router import KlassifikationsRouter
from lightroom_ollama_keywords.models import (
    Config,
    FotoEintrag,
    FotoKategorie,
    KategorieConfig,
    KlassifikationsConfig,
)
from lightroom_ollama_keywords.ollama_client import OllamaClient


# ---------------------------------------------------------------------------
# Mock Ollama HTTP Server with classification support
# ---------------------------------------------------------------------------

class ClassificationMockHandler(BaseHTTPRequestHandler):
    """Mock handler that returns classification or keyword responses based on prompt content."""

    captured_requests: list[dict] = []
    # Map: if prompt contains "Klassifiziere" → return category, else → return keywords
    classification_response: str = "Landschaft"
    keyword_response: str = "Sonnenuntergang, Meer, Horizont"

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        if self.path == "/api/generate":
            ClassificationMockHandler.captured_requests.append(data)

            prompt = data.get("prompt", "")
            if "Klassifiziere" in prompt or "Kategorien:" in prompt:
                response_text = ClassificationMockHandler.classification_response
            else:
                response_text = ClassificationMockHandler.keyword_response

            response = {
                "model": data.get("model", "unknown"),
                "created_at": "2024-01-01T00:00:00Z",
                "response": response_text,
                "done": True,
            }
            self._send_json(200, response)

        elif self.path == "/api/show":
            response = {
                "model_info": {"general.parameter_count": "7000000000"},
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
        pass


@pytest.fixture
def mock_classification_server():
    """Start a mock Ollama HTTP server that supports classification responses."""
    ClassificationMockHandler.captured_requests = []
    ClassificationMockHandler.classification_response = "Landschaft"
    ClassificationMockHandler.keyword_response = "Sonnenuntergang, Meer, Horizont"

    server = HTTPServer(("127.0.0.1", 0), ClassificationMockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_minimal_jpeg(path: str) -> None:
    """Create a minimal valid JPEG file."""
    jpeg_bytes = bytes([
        0xFF, 0xD8,  # SOI
        0xFF, 0xE0,  # APP0
        0x00, 0x10,  # Length
        0x4A, 0x46, 0x49, 0x46, 0x00,  # JFIF\0
        0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
        0xFF, 0xDB,  # DQT
        0x00, 0x43, 0x00,
    ] + [0x01] * 64 + [
        0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01,
        0x01, 0x01, 0x11, 0x00,
        0xFF, 0xC4, 0x00, 0x1F, 0x00,
        0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01,
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
        0x08, 0x09, 0x0A, 0x0B,
        0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,
        0x7B, 0x40,
        0xFF, 0xD9,
    ])
    with open(path, "wb") as f:
        f.write(jpeg_bytes)


def _make_klassifikations_config() -> KlassifikationsConfig:
    """Creates a KlassifikationsConfig with all 8 categories."""
    return KlassifikationsConfig(
        modell="gemma4:e2b",
        prompt=(
            "Klassifiziere dieses Foto in genau eine der folgenden Kategorien. "
            "Antworte NUR mit dem Kategorienamen. "
            "Kategorien: Landschaft, Porträt, Architektur, Dokument, Essen, Tiere, Garten, Sonstiges"
        ),
        kategorien={
            FotoKategorie.LANDSCHAFT: KategorieConfig(prompt="Landschafts-Prompt"),
            FotoKategorie.PORTRAET: KategorieConfig(prompt="Porträt-Prompt"),
            FotoKategorie.ARCHITEKTUR: KategorieConfig(prompt="Architektur-Prompt"),
            FotoKategorie.DOKUMENT: KategorieConfig(prompt="Dokument-Prompt", modell="gemma4:e4b"),
            FotoKategorie.ESSEN: KategorieConfig(prompt="Essen-Prompt"),
            FotoKategorie.TIERE: KategorieConfig(prompt="Tiere-Prompt"),
            FotoKategorie.GARTEN: KategorieConfig(prompt="Garten-Prompt"),
            FotoKategorie.SONSTIGES: KategorieConfig(prompt="Sonstiges-Prompt"),
        },
    )


def _make_config(endpoint: str, tmp_path, klassifikation=None, **overrides) -> Config:
    """Creates a Config with sensible defaults."""
    defaults = dict(
        catalog_path="unused",
        ollama_endpoint=endpoint,
        model_name="llava:7b",
        batch_size=50,
        prompt_template="Fallback-Prompt: Beschreibe dieses Bild.",
        tracking_db_path="./tracking.db",
        log_file_path=str(tmp_path / "test.log"),
        exiftool_path=None,
        benchmark_models=["model-a", "model-b"],
        benchmark_output_csv=str(tmp_path / "benchmark_results.csv"),
        klassifikation=klassifikation,
    )
    defaults.update(overrides)
    return Config(**defaults)


# ---------------------------------------------------------------------------
# Test 1: Klassifikation + Stichwörter End-to-End mit Mock-Ollama
# Requirements: 6.1
# ---------------------------------------------------------------------------

class TestKlassifikationEndToEnd:
    """Integration: Classification + keywords end-to-end with mock Ollama."""

    def test_batch_mit_klassifikation(self, mock_classification_server, tmp_path):
        """BatchProcessor uses KlassifikationsRouter for the full two-stage process."""
        # Create test images
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        for name in ["landscape.jpg", "portrait.jpg"]:
            _create_minimal_jpeg(str(images_dir / name))

        fotos = [
            FotoEintrag(1, str(images_dir / "landscape.jpg")),
            FotoEintrag(2, str(images_dir / "portrait.jpg")),
        ]

        klassifikations_config = _make_klassifikations_config()
        router = KlassifikationsRouter(
            endpoint=mock_classification_server,
            klassifikations_config=klassifikations_config,
            standard_modell="llava:7b",
            fallback_prompt="Fallback-Prompt",
        )

        ollama = OllamaClient(
            endpoint=mock_classification_server,
            model_name="llava:7b",
            prompt_template="Fallback-Prompt",
        )
        mock_schreiber = MagicMock()

        processor = BatchProcessor(
            ollama=ollama,
            schreiber=mock_schreiber,
            tracker=MagicMock(),
            model_name="llava:7b",
            model_version="1.0",
            klassifikations_router=router,
        )

        ergebnis = processor.batch_verarbeiten(fotos)

        # Both photos processed successfully
        assert ergebnis.verarbeitet == 2
        assert ergebnis.fehler == 0

        # StichwortSchreiber was called for each photo with keywords
        assert mock_schreiber.stichwörter_schreiben.call_count == 2
        for call in mock_schreiber.stichwörter_schreiben.call_args_list:
            keywords = call[0][1]
            assert len(keywords) > 0

        # Requests: 2 classification + 2 keyword = 4 total
        assert len(ClassificationMockHandler.captured_requests) == 4

        # First and third requests should be classification (contain "Klassifiziere")
        classification_requests = [
            r for r in ClassificationMockHandler.captured_requests
            if "Klassifiziere" in r.get("prompt", "") or "Kategorien:" in r.get("prompt", "")
        ]
        keyword_requests = [
            r for r in ClassificationMockHandler.captured_requests
            if "Klassifiziere" not in r.get("prompt", "") and "Kategorien:" not in r.get("prompt", "")
        ]
        assert len(classification_requests) == 2
        assert len(keyword_requests) == 2

    def test_batch_konsole_zeigt_kategorie(self, mock_classification_server, tmp_path, capsys):
        """Console output shows category and model for each photo."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _create_minimal_jpeg(str(images_dir / "test.jpg"))

        fotos = [FotoEintrag(1, str(images_dir / "test.jpg"))]

        klassifikations_config = _make_klassifikations_config()
        router = KlassifikationsRouter(
            endpoint=mock_classification_server,
            klassifikations_config=klassifikations_config,
            standard_modell="llava:7b",
            fallback_prompt="Fallback",
        )

        processor = BatchProcessor(
            ollama=OllamaClient(
                endpoint=mock_classification_server,
                model_name="llava:7b",
                prompt_template="Fallback",
            ),
            schreiber=MagicMock(),
            tracker=MagicMock(),
            model_name="llava:7b",
            model_version="1.0",
            klassifikations_router=router,
        )
        processor.batch_verarbeiten(fotos)

        captured = capsys.readouterr()
        assert "Kategorie: Landschaft" in captured.out


# ---------------------------------------------------------------------------
# Test 2: Benchmark mit aktivierter Klassifikation, CSV-Validierung
# Requirements: 7.1
# ---------------------------------------------------------------------------

class TestBenchmarkMitKlassifikation:
    """Integration: Benchmark with classification enabled, CSV validation."""

    def test_benchmark_mit_klassifikation_csv(self, mock_classification_server, tmp_path):
        """Benchmark with classification produces CSV with extended columns."""
        images_dir = tmp_path / "benchmark_images"
        images_dir.mkdir()
        for name in ["img1.jpg", "img2.jpg"]:
            _create_minimal_jpeg(str(images_dir / name))

        klassifikations_config = _make_klassifikations_config()
        config = _make_config(
            mock_classification_server,
            tmp_path,
            klassifikation=klassifikations_config,
            benchmark_models=["model-a"],
        )

        runner = BenchmarkRunner(config)
        zusammenfassungen = runner.benchmark_ausfuehren(
            str(images_dir), config.benchmark_output_csv
        )

        # Verify summaries
        assert len(zusammenfassungen) == 1
        z = zusammenfassungen[0]
        assert z.model_name == "model-a"
        assert z.bilder_verarbeitet == 2
        assert z.fehler == 0
        assert z.durchschnitt_klassifikations_ms is not None
        assert z.durchschnitt_klassifikations_ms > 0

        # Verify CSV output
        pattern = str(tmp_path / "benchmark_results_*.csv")
        matched_files = glob.glob(pattern)
        assert len(matched_files) == 1
        actual_csv = matched_files[0]

        with open(actual_csv, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        data_lines = [l for l in raw_lines if l.strip() and not l.startswith("#")]
        reader = csv.DictReader(io.StringIO("".join(data_lines)))
        rows = list(reader)

        # 1 model × 2 images = 2 data rows
        assert len(rows) == 2

        # Extended columns present
        for row in rows:
            assert "foto_kategorie" in row
            assert "prompt_typ" in row
            assert "klassifikations_zeit_ms" in row
            assert row["foto_kategorie"] == "Landschaft"
            assert row["prompt_typ"] == "Landschaft"
            assert float(row["klassifikations_zeit_ms"]) > 0
            assert float(row["response_time_ms"]) > 0

    def test_benchmark_zusammenfassung_mit_klassifikationszeit(
        self, mock_classification_server, tmp_path, capsys
    ):
        """Benchmark summary includes classification time when classification is active."""
        images_dir = tmp_path / "benchmark_images"
        images_dir.mkdir()
        _create_minimal_jpeg(str(images_dir / "img1.jpg"))

        klassifikations_config = _make_klassifikations_config()
        config = _make_config(
            mock_classification_server,
            tmp_path,
            klassifikation=klassifikations_config,
            benchmark_models=["model-a"],
        )

        runner = BenchmarkRunner(config)
        runner.benchmark_ausfuehren(str(images_dir), config.benchmark_output_csv)

        captured = capsys.readouterr()
        assert "Klassifikation:" in captured.out


# ---------------------------------------------------------------------------
# Test 3: Benchmark ohne Klassifikation — Rückwärtskompatibilität
# Requirements: 4.3
# ---------------------------------------------------------------------------

class TestBenchmarkOhneKlassifikation:
    """Integration: Benchmark without classification — backward compatibility."""

    def test_benchmark_ohne_klassifikation(self, mock_classification_server, tmp_path):
        """Benchmark without classification section works as before."""
        images_dir = tmp_path / "benchmark_images"
        images_dir.mkdir()
        for name in ["img1.jpg", "img2.jpg"]:
            _create_minimal_jpeg(str(images_dir / name))

        # No klassifikation → None
        config = _make_config(
            mock_classification_server,
            tmp_path,
            klassifikation=None,
            benchmark_models=["model-a", "model-b"],
        )

        runner = BenchmarkRunner(config)
        zusammenfassungen = runner.benchmark_ausfuehren(
            str(images_dir), config.benchmark_output_csv
        )

        # Verify summaries
        assert len(zusammenfassungen) == 2
        for z in zusammenfassungen:
            assert z.bilder_verarbeitet == 2
            assert z.fehler == 0
            assert z.durchschnitt_klassifikations_ms is None

        # Verify CSV output has NO classification columns
        pattern = str(tmp_path / "benchmark_results_*.csv")
        matched_files = glob.glob(pattern)
        assert len(matched_files) == 1
        actual_csv = matched_files[0]

        with open(actual_csv, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        data_lines = [l for l in raw_lines if l.strip() and not l.startswith("#")]
        reader = csv.DictReader(io.StringIO("".join(data_lines)))
        rows = list(reader)

        # 2 models × 2 images = 4 data rows
        assert len(rows) == 4

        # No classification columns
        for row in rows:
            assert "foto_kategorie" not in row
            assert "prompt_typ" not in row
            assert "klassifikations_zeit_ms" not in row

    def test_benchmark_ohne_klassifikation_konsole(
        self, mock_classification_server, tmp_path, capsys
    ):
        """Benchmark without classification does not show classification time in summary."""
        images_dir = tmp_path / "benchmark_images"
        images_dir.mkdir()
        _create_minimal_jpeg(str(images_dir / "img1.jpg"))

        config = _make_config(
            mock_classification_server,
            tmp_path,
            klassifikation=None,
            benchmark_models=["model-a"],
        )

        runner = BenchmarkRunner(config)
        runner.benchmark_ausfuehren(str(images_dir), config.benchmark_output_csv)

        captured = capsys.readouterr()
        assert "Klassifikation:" not in captured.out
