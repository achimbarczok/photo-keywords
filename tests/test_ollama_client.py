"""Property-basierte Tests für OllamaClient."""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from lightroom_ollama_keywords.ollama_client import OllamaClient


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate individual keyword segments: printable text that may include
# leading/trailing whitespace and may be empty.
_segment = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z", "S")),
    min_size=0,
    max_size=30,
)

# A comma-separated string built from a list of segments.
_comma_separated = st.lists(_segment, min_size=0, max_size=30).map(",".join)


# ---------------------------------------------------------------------------
# Property 3: Antwort-Parsing
# ---------------------------------------------------------------------------


class TestAntwortParsing:
    """**Validates: Requirements 2.3**

    Property 3: Für alle Komma-getrennten Strings soll das Parsen eine Liste
    von Stichwörtern zurückgeben, in der jedes Stichwort keine führenden oder
    nachfolgenden Whitespace-Zeichen enthält und keine leeren Strings enthalten
    sind.
    """

    def _make_client(self) -> OllamaClient:
        return OllamaClient(
            endpoint="http://dummy:11434",
            model_name="dummy-model",
            prompt_template="dummy prompt",
        )

    @given(text=_comma_separated)
    @settings(max_examples=100)
    def test_no_leading_or_trailing_whitespace(self, text: str) -> None:
        """Every keyword in the parsed result has no leading/trailing whitespace."""
        client = self._make_client()
        result = client._antwort_parsen(text)

        for keyword in result:
            assert keyword == keyword.strip(), (
                f"Keyword {keyword!r} has leading/trailing whitespace"
            )

    @given(text=_comma_separated)
    @settings(max_examples=100)
    def test_no_empty_strings(self, text: str) -> None:
        """No empty strings appear in the parsed result."""
        client = self._make_client()
        result = client._antwort_parsen(text)

        for keyword in result:
            assert keyword != "", "Empty string found in parsed result"

    @given(text=_comma_separated)
    @settings(max_examples=100)
    def test_no_duplicates(self, text: str) -> None:
        """No duplicate keywords appear in the parsed result."""
        client = self._make_client()
        result = client._antwort_parsen(text)

        assert len(result) == len(set(result)), (
            f"Duplicates found in result: {result}"
        )


# ---------------------------------------------------------------------------
# Unit-Tests für OllamaClient (Task 7.3)
# ---------------------------------------------------------------------------

import pytest
import requests
from unittest.mock import patch, MagicMock

from lightroom_ollama_keywords.errors import (
    ImageReadError,
    OllamaApiError,
    OllamaConnectionError,
)


class TestOllamaConnectionError:
    """Test: OllamaConnectionError bei nicht erreichbarer API.

    Anforderung 2.4
    """

    def test_connection_error_contains_endpoint(self) -> None:
        endpoint = "http://192.0.2.1:11434"
        client = OllamaClient(
            endpoint=endpoint,
            model_name="llava",
            prompt_template="describe",
        )

        with patch("lightroom_ollama_keywords.ollama_client.requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("Connection refused")

            with patch.object(client, "_bild_zu_base64", return_value="ZmFrZQ=="):
                with pytest.raises(OllamaConnectionError, match=endpoint):
                    client.analyse_bild("dummy.jpg")


class TestOllamaApiError:
    """Test: OllamaApiError bei API-Fehler.

    Anforderung 2.5
    """

    def test_api_error_on_non_200_status(self) -> None:
        client = OllamaClient(
            endpoint="http://localhost:11434",
            model_name="llava",
            prompt_template="describe",
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("lightroom_ollama_keywords.ollama_client.requests.post", return_value=mock_response):
            with patch.object(client, "_bild_zu_base64", return_value="ZmFrZQ=="):
                with pytest.raises(OllamaApiError):
                    client.analyse_bild("dummy.jpg")


class TestImageReadError:
    """Test: ImageReadError bei nicht lesbarer Bilddatei.

    Anforderung 2.6
    """

    def test_image_read_error_contains_file_path(self) -> None:
        nonexistent = "/does/not/exist/photo.jpg"
        client = OllamaClient(
            endpoint="http://localhost:11434",
            model_name="llava",
            prompt_template="describe",
        )

        with pytest.raises(ImageReadError, match=nonexistent):
            client.analyse_bild(nonexistent)
