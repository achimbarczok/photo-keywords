"""Property-basierte Tests für OllamaClient Validierung und Retry-Mechanismus."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from photo_keywords.models import ValidierungsConfig
from photo_keywords.ollama_client import OllamaClient


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate max_retries values (reasonable range)
_max_retries = st.integers(min_value=0, max_value=5)

# Generate sequences of invalid responses (sentences that will fail validation)
_invalid_response = st.just(
    "Ich kann dieses Bild nicht analysieren da es zu dunkel ist und keine Details erkennbar sind"
)


# ---------------------------------------------------------------------------
# Property 6: Retry-Anzahl ist begrenzt
# ---------------------------------------------------------------------------


class TestRetryCountBounded:
    """**Validates: Requirements 2.2**

    Property 6: Für alle konfigurierten Max_Retries-Werte und für alle
    Sequenzen von ungültigen Antworten soll die Gesamtanzahl der API-Aufrufe
    in analyse_bild() höchstens 1 + max_retries betragen.
    """

    @given(max_retries=_max_retries)
    @settings(max_examples=100)
    def test_api_calls_bounded_by_max_retries(self, max_retries: int) -> None:
        """Total API calls must be <= 1 + max_retries when all responses are invalid."""
        config = ValidierungsConfig(max_retries=max_retries)
        client = OllamaClient(
            endpoint="http://dummy:11434",
            model_name="dummy-model",
            prompt_template="dummy prompt",
            validierungs_config=config,
        )

        # All responses are invalid sentences (high word count)
        invalid_text = (
            "Ich kann dieses Bild nicht analysieren da es zu dunkel ist"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": invalid_text}

        call_count = 0

        def counting_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_response

        with patch(
            "photo_keywords.ollama_client.requests.post",
            side_effect=counting_post,
        ):
            with patch.object(client, "_bild_zu_base64", return_value="ZmFrZQ=="):
                client.analyse_bild("test_image.jpg")

        assert call_count <= 1 + max_retries, (
            f"Expected at most {1 + max_retries} API calls, got {call_count}"
        )
        # Should be exactly 1 + max_retries when all responses are invalid
        assert call_count == 1 + max_retries, (
            f"Expected exactly {1 + max_retries} API calls for all-invalid responses, "
            f"got {call_count}"
        )
