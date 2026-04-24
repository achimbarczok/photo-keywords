"""Fehlerklassen-Hierarchie für den Lightroom Ollama Keyword Generator."""


class KeywordGeneratorError(Exception):
    """Basisklasse für alle Fehler."""


class ConfigError(KeywordGeneratorError):
    """Fehler beim Laden/Validieren der Konfiguration."""


class KatalogError(KeywordGeneratorError):
    """Fehler beim Zugriff auf den Lightroom-Katalog."""


class TrackerError(KeywordGeneratorError):
    """Fehler beim Zugriff auf die Tracking-Datenbank."""


class OllamaConnectionError(KeywordGeneratorError):
    """Ollama-API nicht erreichbar."""


class OllamaApiError(KeywordGeneratorError):
    """Ollama-API hat einen Fehler zurückgegeben."""


class ImageReadError(KeywordGeneratorError):
    """Bilddatei kann nicht gelesen werden."""


class MetadataWriteError(KeywordGeneratorError):
    """Fehler beim Schreiben der Metadaten."""


class BenchmarkError(KeywordGeneratorError):
    """Fehler im Benchmark-Modus (z.B. Bildverzeichnis nicht gefunden)."""


class KlassifikationsError(KeywordGeneratorError):
    """Fehler bei der Foto-Klassifikation."""


class GpsLeseError(KeywordGeneratorError):
    """Fehler beim Lesen von GPS-Daten."""
