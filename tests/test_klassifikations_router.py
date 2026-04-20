"""Unit-Tests für KlassifikationsRouter."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch, call

import pytest

from lightroom_ollama_keywords.errors import (
    KlassifikationsError,
    OllamaApiError,
    OllamaConnectionError,
)
from lightroom_ollama_keywords.klassifikations_router import KlassifikationsRouter
from lightroom_ollama_keywords.models import (
    FotoKategorie,
    KategorieConfig,
    KlassifikationsConfig,
    KlassifikationsErgebnis,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config() -> KlassifikationsConfig:
    """Erstellt eine Standard-KlassifikationsConfig für Tests."""
    return KlassifikationsConfig(
        modell="gemma4:e2b",
        prompt="Klassifiziere dieses Foto",
        kategorien={
            FotoKategorie.LANDSCHAFT: KategorieConfig(
                prompt="Landschafts-Prompt"
            ),
            FotoKategorie.PORTRAET: KategorieConfig(
                prompt="Porträt-Prompt"
            ),
            FotoKategorie.ARCHITEKTUR: KategorieConfig(
                prompt="Architektur-Prompt"
            ),
            FotoKategorie.DOKUMENT: KategorieConfig(
                prompt="Dokument-Prompt",
                modell="gemma4:e4b",
            ),
            FotoKategorie.ESSEN: KategorieConfig(
                prompt="Essen-Prompt"
            ),
            FotoKategorie.TIERE: KategorieConfig(
                prompt="Tiere-Prompt"
            ),
            FotoKategorie.GARTEN: KategorieConfig(
                prompt="Garten-Prompt"
            ),
            FotoKategorie.SONSTIGES: KategorieConfig(
                prompt="Sonstiges-Prompt"
            ),
        },
    )


FALLBACK_PROMPT = "Allgemeiner Fallback-Prompt"
STANDARD_MODELL = "gemma4:e4b-standard"
ENDPOINT = "http://localhost:11434"


def _make_router(config: KlassifikationsConfig | None = None) -> KlassifikationsRouter:
    return KlassifikationsRouter(
        endpoint=ENDPOINT,
        klassifikations_config=config or _make_config(),
        standard_modell=STANDARD_MODELL,
        fallback_prompt=FALLBACK_PROMPT,
    )


# ---------------------------------------------------------------------------
# Test: Klassifikation wird vor Stichwort-Generierung aufgerufen (Req 1.1)
# ---------------------------------------------------------------------------


class TestKlassifikationVorStichwoertern:
    """Anforderung 1.1: Klassifikation wird zuerst aufgerufen, dann Stichwort-Generierung."""

    @patch("lightroom_ollama_keywords.klassifikations_router.OllamaClient")
    def test_classification_called_before_keywords(self, MockOllamaClient: MagicMock) -> None:
        call_order: list[str] = []

        def make_client(endpoint, model_name, prompt_template, **kwargs):
            client = MagicMock()
            if model_name == "gemma4:e2b":
                # Classification client
                def classify_side_effect(path, standort_daten=None):
                    call_order.append("classification")
                    return ["Landschaft"]
                client.analyse_bild.side_effect = classify_side_effect
            else:
                # Keyword client
                def keyword_side_effect(path, standort_daten=None):
                    call_order.append("keywords")
                    return ["Berge", "Himmel"]
                client.analyse_bild.side_effect = keyword_side_effect
            return client

        MockOllamaClient.side_effect = make_client

        router = _make_router()
        result = router.bild_analysieren("/test/foto.jpg")

        assert call_order == ["classification", "keywords"], (
            f"Expected classification before keywords, got {call_order}"
        )


# ---------------------------------------------------------------------------
# Test: KlassifikationsErgebnis enthält alle Felder (Req 1.3)
# ---------------------------------------------------------------------------


class TestKlassifikationsErgebnisFelder:
    """Anforderung 1.3: KlassifikationsErgebnis enthält alle Felder."""

    @patch("lightroom_ollama_keywords.klassifikations_router.OllamaClient")
    def test_result_contains_all_fields(self, MockOllamaClient: MagicMock) -> None:
        def make_client(endpoint, model_name, prompt_template, **kwargs):
            client = MagicMock()
            if model_name == "gemma4:e2b":
                client.analyse_bild.return_value = ["Landschaft"]
            else:
                client.analyse_bild.return_value = ["Berge", "Himmel", "Wolken"]
            return client

        MockOllamaClient.side_effect = make_client

        router = _make_router()
        result = router.bild_analysieren("/test/foto.jpg")

        assert isinstance(result, KlassifikationsErgebnis)
        assert result.kategorie == FotoKategorie.LANDSCHAFT
        assert result.keywords == ["Berge", "Himmel", "Wolken"]
        assert isinstance(result.klassifikations_zeit_ms, float)
        assert isinstance(result.keyword_zeit_ms, float)
        assert result.verwendeter_prompt_typ == "Landschaft"
        assert isinstance(result.verwendetes_modell, str)


# ---------------------------------------------------------------------------
# Test: Fallback bei OllamaApiError (Req 5.1)
# ---------------------------------------------------------------------------


class TestFallbackBeiApiError:
    """Anforderung 5.1: Fallback-Prompt bei OllamaApiError."""

    @patch("lightroom_ollama_keywords.klassifikations_router.OllamaClient")
    def test_fallback_on_api_error(self, MockOllamaClient: MagicMock) -> None:
        call_count = 0

        def make_client(endpoint, model_name, prompt_template, **kwargs):
            nonlocal call_count
            call_count += 1
            client = MagicMock()
            if call_count == 1:
                # First call is the classification client (created in __init__)
                client.analyse_bild.side_effect = OllamaApiError("API Error 500")
            else:
                # Second call is the keyword client (created in bild_analysieren)
                client.analyse_bild.return_value = ["Fallback", "Keywords"]
            return client

        MockOllamaClient.side_effect = make_client

        router = _make_router()
        result = router.bild_analysieren("/test/foto.jpg")

        assert result.kategorie == FotoKategorie.SONSTIGES
        assert result.verwendeter_prompt_typ == "Fallback"
        assert result.verwendetes_modell == STANDARD_MODELL


# ---------------------------------------------------------------------------
# Test: Fallback bei Timeout 10s (Req 5.3)
# ---------------------------------------------------------------------------


class TestFallbackBeiTimeout:
    """Anforderung 5.3: Fallback-Prompt bei Timeout."""

    @patch("lightroom_ollama_keywords.klassifikations_router.OllamaClient")
    def test_fallback_on_timeout(self, MockOllamaClient: MagicMock) -> None:
        call_count = 0

        def make_client(endpoint, model_name, prompt_template, **kwargs):
            nonlocal call_count
            call_count += 1
            client = MagicMock()
            if call_count == 1:
                client.analyse_bild.side_effect = TimeoutError("Timeout after 10s")
            else:
                client.analyse_bild.return_value = ["Fallback", "Keywords"]
            return client

        MockOllamaClient.side_effect = make_client

        router = _make_router()
        result = router.bild_analysieren("/test/foto.jpg")

        assert result.kategorie == FotoKategorie.SONSTIGES
        assert result.verwendeter_prompt_typ == "Fallback"
        assert result.verwendetes_modell == STANDARD_MODELL


# ---------------------------------------------------------------------------
# Test: Fehler-Logging mit Foto-Pfad und Details (Req 5.4)
# ---------------------------------------------------------------------------


class TestFehlerLogging:
    """Anforderung 5.4: Fehler-Logging mit Foto-Pfad und Details."""

    @patch("lightroom_ollama_keywords.klassifikations_router.OllamaClient")
    def test_error_logged_with_path_and_details(self, MockOllamaClient: MagicMock, caplog) -> None:
        call_count = 0

        def make_client(endpoint, model_name, prompt_template, **kwargs):
            nonlocal call_count
            call_count += 1
            client = MagicMock()
            if call_count == 1:
                client.analyse_bild.side_effect = OllamaApiError("Server Error 500")
            else:
                client.analyse_bild.return_value = ["Fallback"]
            return client

        MockOllamaClient.side_effect = make_client

        router = _make_router()
        foto_pfad = "/pfad/zum/bild.jpg"

        with caplog.at_level(logging.WARNING, logger="lightroom_ollama_keywords.klassifikations_router"):
            result = router.bild_analysieren(foto_pfad)

        # Check that the log contains the photo path and error details
        assert any(foto_pfad in record.message for record in caplog.records), (
            f"Expected photo path {foto_pfad!r} in log records"
        )
        assert any("Server Error 500" in record.message for record in caplog.records), (
            "Expected error details in log records"
        )


# ---------------------------------------------------------------------------
# Test: Kategorie "Sonstiges" verwendet Fallback-Prompt (Req 2.9)
# ---------------------------------------------------------------------------


class TestSonstigesVerwendetFallback:
    """Anforderung 2.9: Kategorie 'Sonstiges' verwendet den konfigurierten Sonstiges-Prompt."""

    @patch("lightroom_ollama_keywords.klassifikations_router.OllamaClient")
    def test_sonstiges_uses_sonstiges_config_prompt(self, MockOllamaClient: MagicMock) -> None:
        """When classification returns 'Sonstiges', the Sonstiges config prompt is used."""
        prompts_used: list[str] = []

        def make_client(endpoint, model_name, prompt_template, **kwargs):
            client = MagicMock()
            prompts_used.append(prompt_template)
            if model_name == "gemma4:e2b":
                client.analyse_bild.return_value = ["Sonstiges"]
            else:
                client.analyse_bild.return_value = ["Allgemein"]
            return client

        MockOllamaClient.side_effect = make_client

        router = _make_router()
        result = router.bild_analysieren("/test/foto.jpg")

        assert result.kategorie == FotoKategorie.SONSTIGES
        # The keyword client should have been created with the Sonstiges config prompt
        # prompts_used[0] = classification prompt (from __init__)
        # prompts_used[1] = keyword prompt (from bild_analysieren)
        assert prompts_used[-1] == "Sonstiges-Prompt", (
            f"Expected 'Sonstiges-Prompt', got {prompts_used[-1]!r}"
        )
        assert result.verwendeter_prompt_typ == "Sonstiges"

    @patch("lightroom_ollama_keywords.klassifikations_router.OllamaClient")
    def test_sonstiges_without_config_uses_fallback(self, MockOllamaClient: MagicMock) -> None:
        """When Sonstiges has no config entry, fallback prompt is used."""
        config = KlassifikationsConfig(
            modell="gemma4:e2b",
            prompt="Klassifiziere",
            kategorien={},  # No category configs at all
        )

        prompts_used: list[str] = []

        def make_client(endpoint, model_name, prompt_template, **kwargs):
            client = MagicMock()
            prompts_used.append(prompt_template)
            if model_name == "gemma4:e2b":
                client.analyse_bild.return_value = ["Sonstiges"]
            else:
                client.analyse_bild.return_value = ["Allgemein"]
            return client

        MockOllamaClient.side_effect = make_client

        router = _make_router(config)
        result = router.bild_analysieren("/test/foto.jpg")

        assert result.kategorie == FotoKategorie.SONSTIGES
        # Without config, fallback prompt should be used
        assert prompts_used[-1] == FALLBACK_PROMPT
