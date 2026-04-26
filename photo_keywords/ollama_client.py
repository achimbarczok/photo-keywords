"""OllamaClient – Kommunikation mit der lokalen Ollama REST API."""

from __future__ import annotations

import base64
import logging

import requests

from photo_keywords.antwort_validator import AntwortValidator
from photo_keywords.errors import (
    ImageReadError,
    OllamaApiError,
    OllamaConnectionError,
)
from photo_keywords.models import StandortDaten, ValidierungsConfig

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client für die Ollama REST API zur Bildanalyse."""

    def __init__(
        self,
        endpoint: str,
        model_name: str,
        prompt_template: str,
        validierungs_config: ValidierungsConfig | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.model_name = model_name
        self.prompt_template = prompt_template
        self._validierungs_config = validierungs_config or ValidierungsConfig()
        self._validator = AntwortValidator(self._validierungs_config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse_bild(
        self, image_path: str, standort_daten: StandortDaten | None = None
    ) -> list[str]:
        """Sendet ein Bild an Ollama, validiert die Antwort und wiederholt bei Bedarf.

        1. Bild senden mit original prompt_template (ggf. mit Standort-Prefix)
        2. Antwort parsen
        3. Validieren
        4. Bei ungültiger Antwort: bis max_retries mit retry_prompt wiederholen
        5. Letzte Antwort zurückgeben (auch wenn nach max_retries noch ungültig)

        Args:
            image_path: Pfad zur Bilddatei.
            standort_daten: Optionale Standortdaten für Kontext-Prefix im Prompt.

        Raises:
            ImageReadError: Bilddatei nicht lesbar.
            OllamaConnectionError: API nicht erreichbar.
            OllamaApiError: API hat einen Fehler zurückgegeben.
        """
        image_b64 = self._bild_zu_base64(image_path)

        # Build prompt with optional location prefix
        if standort_daten is not None:
            prompt = self._standort_prompt_prefix(standort_daten) + "\n" + self.prompt_template
        else:
            prompt = self.prompt_template

        # Initial request with original prompt
        keywords = self._api_anfrage(image_b64, prompt)

        # Validate and retry if needed
        ergebnis = self._validator.validieren(keywords)
        if ergebnis.gueltig:
            return keywords

        max_retries = self._validierungs_config.max_retries
        retry_prompt = self._validierungs_config.retry_prompt

        for retry_nr in range(1, max_retries + 1):
            logger.info(
                "Retry %d/%d für %s: %s",
                retry_nr,
                max_retries,
                image_path,
                ergebnis.grund,
            )

            keywords = self._api_anfrage(image_b64, retry_prompt)
            ergebnis = self._validator.validieren(keywords)

            if ergebnis.gueltig:
                logger.info(
                    "Retry %d erfolgreich für %s",
                    retry_nr,
                    image_path,
                )
                return keywords

        logger.warning(
            "Alle %d Retries erschöpft für %s — verwende letzte Antwort",
            max_retries,
            image_path,
        )
        return keywords

    def modell_version_abfragen(self) -> str:
        """Fragt die Modellversion über POST /api/show ab."""
        url = f"{self.endpoint}/api/show"
        payload = {"name": self.model_name}

        try:
            resp = requests.post(url, json=payload, timeout=30)
        except requests.ConnectionError as exc:
            raise OllamaConnectionError(
                f"Ollama-API nicht erreichbar unter {self.endpoint}"
            ) from exc
        except requests.RequestException as exc:
            raise OllamaConnectionError(
                f"Ollama-API nicht erreichbar unter {self.endpoint}"
            ) from exc

        if resp.status_code != 200:
            raise OllamaApiError(
                f"Ollama-API Fehler (Status {resp.status_code}): {resp.text}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise OllamaApiError(
                f"Ungültige JSON-Antwort von Ollama-API: {resp.text}"
            ) from exc

        return str(data.get("modelinfo", {}).get("general.parameter_count", data.get("model_info", {}).get("general.parameter_count", str(data))))

    @staticmethod
    def _standort_prompt_prefix(standort_daten: StandortDaten) -> str:
        """Erzeugt den Standort-Kontext-Prefix für den Prompt.

        Format: "Dieses Foto wurde in {stadt}, {land} aufgenommen."
        Wenn region != stadt: "Dieses Foto wurde in {stadt}, {region}, {land} aufgenommen."
        """
        if standort_daten.region and standort_daten.region != standort_daten.stadt:
            return f"Dieses Foto wurde in {standort_daten.stadt}, {standort_daten.region}, {standort_daten.land} aufgenommen."
        return f"Dieses Foto wurde in {standort_daten.stadt}, {standort_daten.land} aufgenommen."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _api_anfrage(self, image_b64: str, prompt: str) -> list[str]:
        """Sendet eine Anfrage an die Ollama API und gibt geparste Keywords zurück.

        Raises:
            OllamaConnectionError: API nicht erreichbar.
            OllamaApiError: API hat einen Fehler zurückgegeben.
        """
        url = f"{self.endpoint}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "images": [image_b64],
            "options": {
                "num_predict": 512,
                "num_ctx": 4096,
            },
            "think": False,
        }

        try:
            resp = requests.post(url, json=payload, timeout=120)
        except requests.ConnectionError as exc:
            raise OllamaConnectionError(
                f"Ollama-API nicht erreichbar unter {self.endpoint}"
            ) from exc
        except requests.RequestException as exc:
            raise OllamaConnectionError(
                f"Ollama-API nicht erreichbar unter {self.endpoint}"
            ) from exc

        if resp.status_code != 200:
            raise OllamaApiError(
                f"Ollama-API Fehler (Status {resp.status_code}): {resp.text}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise OllamaApiError(
                f"Ungültige JSON-Antwort von Ollama-API: {resp.text}"
            ) from exc

        response_text = data.get("response", "")
        return self._antwort_parsen(response_text)

    # Formate, die Ollama nicht direkt lesen kann → temporäre JPEG-Konvertierung
    _KONVERTIERUNGS_FORMATE = {
        ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf",
        ".tiff", ".tif", ".bmp", ".webp",
    }

    def _bild_zu_base64(self, image_path: str) -> str:
        """Liest eine Bilddatei und gibt den base64-kodierten Inhalt zurück.

        Für RAW- und TIFF-Formate wird das Bild temporär nach JPEG konvertiert.

        Raises:
            ImageReadError: Datei nicht lesbar oder nicht konvertierbar.
        """
        import os

        ext = os.path.splitext(image_path)[1].lower()

        if ext in self._KONVERTIERUNGS_FORMATE:
            return self._konvertieren_und_base64(image_path)

        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        except (OSError, IOError) as exc:
            raise ImageReadError(
                f"Bilddatei nicht lesbar: {image_path}"
            ) from exc

    def _konvertieren_und_base64(self, image_path: str) -> str:
        """Konvertiert ein Bild nach JPEG im Speicher und gibt base64 zurück.

        Verwendet Pillow (PIL) für die Konvertierung. Bei RAW-Formaten
        wird rawpy verwendet, falls verfügbar.

        Raises:
            ImageReadError: Konvertierung fehlgeschlagen.
        """
        import io

        try:
            from PIL import Image

            img = Image.open(image_path)
            img = img.convert("RGB")

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            buffer.seek(0)

            logger.debug("Konvertiert nach JPEG: %s", image_path)
            return base64.b64encode(buffer.read()).decode("ascii")
        except Exception as exc:
            raise ImageReadError(
                f"Bildkonvertierung fehlgeschlagen für '{image_path}': {exc}"
            ) from exc

    def _antwort_parsen(self, response_text: str) -> list[str]:
        """Parst eine komma-getrennte Antwort in eine bereinigte Stichwort-Liste.

        - Whitespace wird getrimmt
        - Leere Einträge werden entfernt
        - Duplikate werden entfernt (Reihenfolge bleibt erhalten)
        """
        parts = response_text.split(",")
        seen: set[str] = set()
        result: list[str] = []
        for part in parts:
            keyword = part.strip().strip('"').strip("'").strip().replace('"', '').replace("'", "")
            if keyword and keyword not in seen:
                seen.add(keyword)
                result.append(keyword)
        return result
