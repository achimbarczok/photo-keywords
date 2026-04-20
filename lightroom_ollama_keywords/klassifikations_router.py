"""KlassifikationsRouter – Zwei-Stufen-Prozess: Klassifikation → spezialisierte Stichwort-Generierung."""

from __future__ import annotations

import logging
import time

from lightroom_ollama_keywords.errors import (
    KlassifikationsError,
    OllamaApiError,
    OllamaConnectionError,
)
from lightroom_ollama_keywords.models import (
    FotoKategorie,
    KlassifikationsConfig,
    KlassifikationsErgebnis,
    StandortDaten,
    ValidierungsConfig,
)
from lightroom_ollama_keywords.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# Lookup-Dictionary für Normalisierung: lowercase → FotoKategorie
# Enthält sowohl deutsche (Enum-Werte) als auch englische Bezeichnungen,
# damit Modelle in beiden Sprachen antworten können.
_KATEGORIE_LOOKUP: dict[str, FotoKategorie] = {
    k.value.lower(): k for k in FotoKategorie
}
_KATEGORIE_LOOKUP.update({
    "landscape": FotoKategorie.LANDSCHAFT,
    "portrait": FotoKategorie.PORTRAET,
    "architecture": FotoKategorie.ARCHITEKTUR,
    "document": FotoKategorie.DOKUMENT,
    "food": FotoKategorie.ESSEN,
    "animals": FotoKategorie.TIERE,
    "animal": FotoKategorie.TIERE,
    "garden": FotoKategorie.GARTEN,
    "other": FotoKategorie.SONSTIGES,
    "misc": FotoKategorie.SONSTIGES,
    "miscellaneous": FotoKategorie.SONSTIGES,
    "wildlife": FotoKategorie.TIERE,
    "nature": FotoKategorie.LANDSCHAFT,
    "building": FotoKategorie.ARCHITEKTUR,
    "buildings": FotoKategorie.ARCHITEKTUR,
    "people": FotoKategorie.PORTRAET,
    "person": FotoKategorie.PORTRAET,
    "text": FotoKategorie.DOKUMENT,
    "pet": FotoKategorie.TIERE,
    "pets": FotoKategorie.TIERE,
    "plant": FotoKategorie.GARTEN,
    "plants": FotoKategorie.GARTEN,
    "flowers": FotoKategorie.GARTEN,
    "flower": FotoKategorie.GARTEN,
    "museum": FotoKategorie.MUSEUM,
    "exhibition": FotoKategorie.MUSEUM,
    "exhibit": FotoKategorie.MUSEUM,
    "gallery": FotoKategorie.MUSEUM,
    "artifact": FotoKategorie.MUSEUM,
    "fossil": FotoKategorie.MUSEUM,
    "event": FotoKategorie.VERANSTALTUNG,
    "concert": FotoKategorie.VERANSTALTUNG,
    "festival": FotoKategorie.VERANSTALTUNG,
    "party": FotoKategorie.VERANSTALTUNG,
    "celebration": FotoKategorie.VERANSTALTUNG,
    "ceremony": FotoKategorie.VERANSTALTUNG,
    "wedding": FotoKategorie.VERANSTALTUNG,
    "conference": FotoKategorie.VERANSTALTUNG,
})


class KlassifikationsRouter:
    """Orchestriert Klassifikation → spezialisierte Stichwort-Generierung."""

    def __init__(
        self,
        endpoint: str,
        klassifikations_config: KlassifikationsConfig,
        standard_modell: str,
        fallback_prompt: str,
        validierungs_config: ValidierungsConfig | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._config = klassifikations_config
        self._standard_modell = standard_modell
        self._fallback_prompt = fallback_prompt
        self._validierungs_config = validierungs_config

        # Interner OllamaClient für die Klassifikation
        self._klassifikations_client = OllamaClient(
            endpoint=endpoint,
            model_name=klassifikations_config.modell,
            prompt_template=klassifikations_config.prompt,
            validierungs_config=validierungs_config,
        )

        # Cache für Keyword-Clients: (modell, prompt) → OllamaClient
        # Vermeidet ständige Modellwechsel bei Ollama
        self._keyword_clients: dict[tuple[str, str], OllamaClient] = {}

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def kategorie_parsen(antwort: str) -> FotoKategorie:
        """Parst die Textantwort des Klassifikations-Modells in eine FotoKategorie.

        - Normalisiert: strip(), lower()
        - Matched gegen _KATEGORIE_LOOKUP
        - Bei keinem Match: FotoKategorie.SONSTIGES
        """
        normalised = antwort.strip().lower()
        return _KATEGORIE_LOOKUP.get(normalised, FotoKategorie.SONSTIGES)

    @staticmethod
    def kategorie_formatieren(kategorie: FotoKategorie) -> str:
        """Formatiert eine FotoKategorie zurück in den normalisierten Kategorienamen."""
        return kategorie.value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def bild_analysieren(
        self, image_path: str, standort_daten: StandortDaten | None = None
    ) -> KlassifikationsErgebnis:
        """Klassifiziert ein Bild und generiert spezialisierte Stichwörter.

        1. Bild an Klassifikations-Modell senden, Zeit messen
        2. Antwort in FotoKategorie parsen
        3. Passenden Prompt + Modell aus KategorieConfig laden
        4. Bild an Stichwort-Modell mit spezialisiertem Prompt senden, Zeit messen
        5. KlassifikationsErgebnis zurückgeben

        Bei Fehlern in Schritt 1-3: Fallback-Prompt verwenden.
        """
        kategorie: FotoKategorie
        prompt: str
        modell: str
        klassifikations_zeit_ms: float
        ist_fallback = False

        try:
            kategorie, klassifikations_zeit_ms = self._klassifizieren(
                image_path, standort_daten
            )
            prompt, modell = self._prompt_und_modell_fuer(kategorie)
        except (OllamaApiError, OllamaConnectionError, KlassifikationsError) as exc:
            logger.warning(
                "Klassifikation fehlgeschlagen für %s: %s — verwende Fallback",
                image_path,
                exc,
            )
            kategorie = FotoKategorie.SONSTIGES
            prompt = self._fallback_prompt
            modell = self._standard_modell
            klassifikations_zeit_ms = 0.0
            ist_fallback = True
        except TimeoutError as exc:
            logger.warning(
                "Klassifikation Timeout für %s: %s — verwende Fallback",
                image_path,
                exc,
            )
            kategorie = FotoKategorie.SONSTIGES
            prompt = self._fallback_prompt
            modell = self._standard_modell
            klassifikations_zeit_ms = 0.0
            ist_fallback = True

        # Schritt 4: Stichwort-Generierung mit spezialisiertem Prompt
        cache_key = (modell, prompt)
        if cache_key not in self._keyword_clients:
            self._keyword_clients[cache_key] = OllamaClient(
                endpoint=self._endpoint,
                model_name=modell,
                prompt_template=prompt,
                validierungs_config=self._validierungs_config,
            )
        keyword_client = self._keyword_clients[cache_key]

        start = time.perf_counter()
        keywords = keyword_client.analyse_bild(image_path, standort_daten)
        keyword_zeit_ms = (time.perf_counter() - start) * 1000

        # Determine prompt type: "Fallback" when we fell back due to errors,
        # otherwise the category name (including "Sonstiges" when it has its own config).
        verwendeter_prompt_typ = "Fallback" if ist_fallback else self.kategorie_formatieren(kategorie)

        return KlassifikationsErgebnis(
            kategorie=kategorie,
            keywords=keywords,
            klassifikations_zeit_ms=klassifikations_zeit_ms,
            keyword_zeit_ms=keyword_zeit_ms,
            verwendeter_prompt_typ=verwendeter_prompt_typ,
            verwendetes_modell=modell,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _klassifizieren(
        self, image_path: str, standort_daten: StandortDaten | None = None
    ) -> tuple[FotoKategorie, float]:
        """Sendet das Bild an das Klassifikations-Modell und gibt Kategorie + Zeit zurück."""
        start = time.perf_counter()
        antwort_keywords = self._klassifikations_client.analyse_bild(
            image_path, standort_daten
        )
        zeit_ms = (time.perf_counter() - start) * 1000

        # OllamaClient gibt eine Liste zurück; wir nehmen das erste Element als Kategorie-Text
        antwort_text = antwort_keywords[0] if antwort_keywords else ""
        kategorie = self.kategorie_parsen(antwort_text)
        return kategorie, zeit_ms

    def _prompt_und_modell_fuer(
        self, kategorie: FotoKategorie
    ) -> tuple[str, str]:
        """Gibt den passenden Prompt und das Modell für eine Kategorie zurück."""
        kat_config = self._config.kategorien.get(kategorie)

        if kat_config is None:
            # Keine Konfiguration für diese Kategorie → Fallback
            return self._fallback_prompt, self._standard_modell

        prompt = kat_config.prompt
        modell = kat_config.modell if kat_config.modell else self._standard_modell
        return prompt, modell
