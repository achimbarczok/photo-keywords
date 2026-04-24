"""Integrationstests für transparente Antwort-Validierung.

Prüft, dass der Retry-Mechanismus transparent durch BatchProcessor und
KlassifikationsRouter funktioniert, ohne dass diese Komponenten angepasst
werden müssen.

Requirements: 4.1, 4.2, 4.3
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock

import pytest

from photo_keywords.batch_processor import BatchProcessor
from photo_keywords.klassifikations_router import KlassifikationsRouter
from photo_keywords.models import (
    FotoEintrag,
    FotoKategorie,
    KategorieConfig,
    KlassifikationsConfig,
    ValidierungsConfig,
)
from photo_keywords.ollama_client import OllamaClient


# ---------------------------------------------------------------------------
# Mock Ollama HTTP Server with validation retry support
# ---------------------------------------------------------------------------


class ValidationMockHandler(BaseHTTPRequestHandler):
    """Mock handler that returns invalid responses first, then valid ones.

    Tracks per-image call counts so that the first call for keyword generation
    returns an invalid sentence and subsequent calls return valid keywords.
    Classification requests always return a valid category.
    """

    call_counts: dict[str, int] = {}
    total_generate_calls: int = 0

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        if self.path == "/api/generate":
            ValidationMockHandler.total_generate_calls += 1
            prompt = data.get("prompt", "")

            # Classification requests → always return valid category
            if "Klassifiziere" in prompt or "Kategorien:" in prompt:
                response_text = "Landschaft"
            else:
                # Keyword requests: first call → invalid, subsequent → valid
                # Use prompt as key to distinguish initial vs retry
                image_key = str(data.get("images", [""])[0])
                count = ValidationMockHandler.call_counts.get(image_key, 0)
                ValidationMockHandler.call_counts[image_key] = count + 1

                if count == 0:
                    # First keyword call: return an invalid sentence
                    response_text = (
                        "Ich kann dieses Bild nicht analysieren da es "
                        "sich um eine Fossilienpräparation handelt"
                    )
                else:
                    # Retry: return valid keywords
                    response_text = "Fossil, Präparat, Museum, Naturkunde"

            response = {
                "model": data.get("model", "unknown"),
                "created_at": "2024-01-01T00:00:00Z",
                "response": response_text,
                "done": True,
            }
            self._send_json(200, response)

        elif self.path == "/api/show":
            self._send_json(200, {
                "model_info": {"general.parameter_count": "7000000000"},
            })
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
def mock_validation_server():
    """Start a mock Ollama HTTP server that simulates invalid → valid responses."""
    ValidationMockHandler.call_counts = {}
    ValidationMockHandler.total_generate_calls = 0

    server = HTTPServer(("127.0.0.1", 0), ValidationMockHandler)
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


# ---------------------------------------------------------------------------
# Test 1: BatchProcessor — transparent validation with retry
# Requirements: 4.1, 4.3
# ---------------------------------------------------------------------------


class TestBatchProcessorTransparentValidation:
    """BatchProcessor works transparently with validation — no changes needed."""

    def test_invalid_then_valid_via_retry(self, mock_validation_server, tmp_path):
        """Invalid response triggers retry inside OllamaClient; BatchProcessor
        sees only the final valid keywords — completely transparent."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _create_minimal_jpeg(str(images_dir / "test.jpg"))

        fotos = [FotoEintrag(1, str(images_dir / "test.jpg"))]

        config = ValidierungsConfig(max_retries=2)
        ollama = OllamaClient(
            endpoint=mock_validation_server,
            model_name="llava:7b",
            prompt_template="Beschreibe das Bild mit Stichwörtern",
            validierungs_config=config,
        )

        mock_schreiber = MagicMock()
        mock_tracker = MagicMock()

        processor = BatchProcessor(
            ollama=ollama,
            schreiber=mock_schreiber,
            tracker=mock_tracker,
            model_name="llava:7b",
            model_version="1.0",
        )

        ergebnis = processor.batch_verarbeiten(fotos)

        # Photo processed successfully — retry was transparent
        assert ergebnis.verarbeitet == 1
        assert ergebnis.fehler == 0

        # StichwortSchreiber received valid keywords (from the retry)
        mock_schreiber.stichwörter_schreiben.assert_called_once()
        written_keywords = mock_schreiber.stichwörter_schreiben.call_args[0][1]
        assert "Fossil" in written_keywords
        assert "Museum" in written_keywords

        # OllamaClient made 2 API calls: initial (invalid) + 1 retry (valid)
        assert ValidationMockHandler.total_generate_calls == 2


# ---------------------------------------------------------------------------
# Test 2: KlassifikationsRouter — transparent validation with retry
# Requirements: 4.2, 4.3
# ---------------------------------------------------------------------------


class TestKlassifikationsRouterTransparentValidation:
    """KlassifikationsRouter works transparently with validation — no changes needed."""

    def test_invalid_then_valid_via_retry(self, mock_validation_server, tmp_path):
        """Invalid keyword response triggers retry inside OllamaClient;
        KlassifikationsRouter sees only the final valid keywords."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _create_minimal_jpeg(str(images_dir / "test.jpg"))

        config = ValidierungsConfig(max_retries=2)
        klassifikations_config = KlassifikationsConfig(
            modell="llava:7b",
            prompt=(
                "Klassifiziere dieses Foto. "
                "Kategorien: Landschaft, Porträt, Stadt, Innenraum, Dokument, "
                "Essen, Tiere, Garten, Sonstiges"
            ),
            kategorien={
                FotoKategorie.LANDSCHAFT: KategorieConfig(
                    prompt="Landschafts-Stichwörter bitte"
                ),
            },
        )

        router = KlassifikationsRouter(
            endpoint=mock_validation_server,
            klassifikations_config=klassifikations_config,
            standard_modell="llava:7b",
            fallback_prompt="Fallback-Prompt",
            validierungs_config=config,
        )

        ergebnis = router.bild_analysieren(str(images_dir / "test.jpg"))

        # Classification succeeded
        assert ergebnis.kategorie == FotoKategorie.LANDSCHAFT

        # Keywords are the valid ones from the retry
        assert "Fossil" in ergebnis.keywords
        assert "Museum" in ergebnis.keywords

        # 1 classification call + 2 keyword calls (initial invalid + retry valid)
        assert ValidationMockHandler.total_generate_calls == 3
