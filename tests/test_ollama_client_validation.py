"""Unit-Tests für OllamaClient Validierung und Retry-Mechanismus."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from lightroom_ollama_keywords.models import ValidierungsConfig
from lightroom_ollama_keywords.ollama_client import OllamaClient


def _make_mock_response(response_text: str) -> MagicMock:
    """Creates a mock requests.Response with the given response text."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"response": response_text}
    return mock


def _make_client(
    validierungs_config: ValidierungsConfig | None = None,
) -> OllamaClient:
    return OllamaClient(
        endpoint="http://localhost:11434",
        model_name="llava",
        prompt_template="Beschreibe das Bild mit Stichwörtern",
        validierungs_config=validierungs_config,
    )


class TestValidatorCalledInAnalyseBild:
    """Validator wird in analyse_bild() aufgerufen (Req 1.1)."""

    def test_validator_is_called(self) -> None:
        client = _make_client()
        valid_response = _make_mock_response("Natur, Wald, Baum")

        with patch(
            "lightroom_ollama_keywords.ollama_client.requests.post",
            return_value=valid_response,
        ):
            with patch.object(client, "_bild_zu_base64", return_value="ZmFrZQ=="):
                with patch.object(
                    client._validator, "validieren", wraps=client._validator.validieren
                ) as mock_val:
                    client.analyse_bild("test.jpg")
                    mock_val.assert_called()


class TestRetryUsesRetryPrompt:
    """Retry verwendet retry_prompt statt Original-Prompt (Req 2.1, 2.4)."""

    def test_retry_sends_retry_prompt(self) -> None:
        config = ValidierungsConfig(max_retries=1)
        client = _make_client(validierungs_config=config)

        # First response invalid (sentence), second valid
        invalid_resp = _make_mock_response(
            "Ich kann dieses Bild nicht analysieren da es zu dunkel ist"
        )
        valid_resp = _make_mock_response("Natur, Wald, Baum")

        prompts_used: list[str] = []

        def capture_post(url, json=None, **kwargs):
            prompts_used.append(json["prompt"])
            if len(prompts_used) == 1:
                return invalid_resp
            return valid_resp

        with patch(
            "lightroom_ollama_keywords.ollama_client.requests.post",
            side_effect=capture_post,
        ):
            with patch.object(client, "_bild_zu_base64", return_value="ZmFrZQ=="):
                client.analyse_bild("test.jpg")

        assert len(prompts_used) == 2
        assert prompts_used[0] == client.prompt_template
        assert prompts_used[1] == config.retry_prompt


class TestLastResponseReturnedWhenRetriesExhausted:
    """Letzte Antwort bei erschöpften Retries zurückgegeben (Req 2.3)."""

    def test_returns_last_response(self) -> None:
        config = ValidierungsConfig(max_retries=2)
        client = _make_client(validierungs_config=config)

        # All responses are invalid sentences
        responses = [
            _make_mock_response("Dieses Bild zeigt eine dunkle Szene ohne erkennbare Details"),
            _make_mock_response("Ich sehe hier ein Foto das sehr unscharf ist"),
            _make_mock_response("Das letzte Bild ist ebenfalls nicht gut erkennbar leider"),
        ]
        call_idx = 0

        def sequential_post(*args, **kwargs):
            nonlocal call_idx
            resp = responses[call_idx]
            call_idx += 1
            return resp

        with patch(
            "lightroom_ollama_keywords.ollama_client.requests.post",
            side_effect=sequential_post,
        ):
            with patch.object(client, "_bild_zu_base64", return_value="ZmFrZQ=="):
                result = client.analyse_bild("test.jpg")

        # Should return the last parsed response
        assert "Das letzte Bild ist ebenfalls nicht gut erkennbar leider" in result


class TestCustomRetryPrompt:
    """Custom retry_prompt wird verwendet (Req 2.5)."""

    def test_custom_retry_prompt_is_used(self) -> None:
        custom_prompt = "Nur Stichwörter bitte!"
        config = ValidierungsConfig(max_retries=1, retry_prompt=custom_prompt)
        client = _make_client(validierungs_config=config)

        invalid_resp = _make_mock_response(
            "Ich kann dieses Bild leider nicht beschreiben weil es zu dunkel ist"
        )
        valid_resp = _make_mock_response("Natur, Wald")

        prompts_used: list[str] = []

        def capture_post(url, json=None, **kwargs):
            prompts_used.append(json["prompt"])
            if len(prompts_used) == 1:
                return invalid_resp
            return valid_resp

        with patch(
            "lightroom_ollama_keywords.ollama_client.requests.post",
            side_effect=capture_post,
        ):
            with patch.object(client, "_bild_zu_base64", return_value="ZmFrZQ=="):
                client.analyse_bild("test.jpg")

        assert prompts_used[1] == custom_prompt


class TestRetryLogging:
    """Retry-Logging enthält Bildpfad, Retry-Nr, Grund (Req 3.1)."""

    def test_retry_log_contains_details(self, caplog: pytest.LogCaptureFixture) -> None:
        config = ValidierungsConfig(max_retries=1)
        client = _make_client(validierungs_config=config)

        invalid_resp = _make_mock_response(
            "Dieses Bild zeigt eine Landschaft mit Bergen und Seen im Hintergrund"
        )
        valid_resp = _make_mock_response("Berg, See, Landschaft")

        call_idx = 0

        def sequential_post(*args, **kwargs):
            nonlocal call_idx
            resp = invalid_resp if call_idx == 0 else valid_resp
            call_idx += 1
            return resp

        with patch(
            "lightroom_ollama_keywords.ollama_client.requests.post",
            side_effect=sequential_post,
        ):
            with patch.object(client, "_bild_zu_base64", return_value="ZmFrZQ=="):
                with caplog.at_level(logging.INFO):
                    client.analyse_bild("/pfad/zum/bild.jpg")

        # Check that retry log contains image path, retry number, and reason
        retry_logs = [r for r in caplog.records if "Retry" in r.message and "INFO" == r.levelname]
        assert len(retry_logs) >= 1
        retry_msg = retry_logs[0].message
        assert "/pfad/zum/bild.jpg" in retry_msg
        assert "1/" in retry_msg
        # Reason should mention word count or similar
        assert "Wortanzahl" in retry_msg or "Ablehnungsphrase" in retry_msg or "Einzeleintrag" in retry_msg


class TestWarningOnExhaustedRetries:
    """WARNING-Log bei erschöpften Retries (Req 3.2)."""

    def test_warning_logged_when_retries_exhausted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = ValidierungsConfig(max_retries=2)
        client = _make_client(validierungs_config=config)

        # All responses invalid
        invalid_resp = _make_mock_response(
            "Ich kann dieses Bild nicht analysieren da es zu dunkel ist und keine Details erkennbar sind"
        )

        with patch(
            "lightroom_ollama_keywords.ollama_client.requests.post",
            return_value=invalid_resp,
        ):
            with patch.object(client, "_bild_zu_base64", return_value="ZmFrZQ=="):
                with caplog.at_level(logging.WARNING):
                    client.analyse_bild("/pfad/zum/bild.jpg")

        warning_logs = [
            r for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert len(warning_logs) >= 1
        warning_msg = warning_logs[0].message
        assert "/pfad/zum/bild.jpg" in warning_msg
        assert "2" in warning_msg  # max_retries count


class TestSuccessLogOnRetry:
    """INFO-Log bei erfolgreichem Retry (Req 3.3)."""

    def test_success_logged_on_successful_retry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = ValidierungsConfig(max_retries=2)
        client = _make_client(validierungs_config=config)

        invalid_resp = _make_mock_response(
            "Dieses Bild zeigt eine Landschaft mit Bergen und Seen im Hintergrund"
        )
        valid_resp = _make_mock_response("Berg, See, Landschaft")

        call_idx = 0

        def sequential_post(*args, **kwargs):
            nonlocal call_idx
            resp = invalid_resp if call_idx == 0 else valid_resp
            call_idx += 1
            return resp

        with patch(
            "lightroom_ollama_keywords.ollama_client.requests.post",
            side_effect=sequential_post,
        ):
            with patch.object(client, "_bild_zu_base64", return_value="ZmFrZQ=="):
                with caplog.at_level(logging.INFO):
                    client.analyse_bild("/pfad/zum/bild.jpg")

        success_logs = [
            r
            for r in caplog.records
            if "erfolgreich" in r.message and r.levelno == logging.INFO
        ]
        assert len(success_logs) >= 1
        assert "/pfad/zum/bild.jpg" in success_logs[0].message
