"""Tests für die Fehlerklassen-Hierarchie."""

import pytest

from lightroom_ollama_keywords.errors import (
    BenchmarkError,
    ConfigError,
    ImageReadError,
    KatalogError,
    KeywordGeneratorError,
    MetadataWriteError,
    OllamaApiError,
    OllamaConnectionError,
    TrackerError,
)


class TestErrorHierarchy:
    """Alle Fehlerklassen erben von KeywordGeneratorError."""

    @pytest.mark.parametrize(
        "error_class",
        [
            ConfigError,
            KatalogError,
            TrackerError,
            OllamaConnectionError,
            OllamaApiError,
            ImageReadError,
            MetadataWriteError,
            BenchmarkError,
        ],
    )
    def test_subclass_of_base(self, error_class):
        assert issubclass(error_class, KeywordGeneratorError)

    def test_base_is_exception(self):
        assert issubclass(KeywordGeneratorError, Exception)

    @pytest.mark.parametrize(
        "error_class",
        [
            KeywordGeneratorError,
            ConfigError,
            KatalogError,
            TrackerError,
            OllamaConnectionError,
            OllamaApiError,
            ImageReadError,
            MetadataWriteError,
            BenchmarkError,
        ],
    )
    def test_error_message_preserved(self, error_class):
        msg = "test error message"
        err = error_class(msg)
        assert str(err) == msg

    def test_catch_all_via_base(self):
        """Alle spezifischen Fehler lassen sich über die Basisklasse fangen."""
        with pytest.raises(KeywordGeneratorError):
            raise ConfigError("missing param")

        with pytest.raises(KeywordGeneratorError):
            raise OllamaConnectionError("unreachable")

        with pytest.raises(KeywordGeneratorError):
            raise BenchmarkError("no directory")
