"""StandortResolver – Offline-Reverse-Geocoding von GPS-Koordinaten."""

from __future__ import annotations

import logging

from lightroom_ollama_keywords.models import StandortDaten

logger = logging.getLogger(__name__)


class StandortResolver:
    """Löst GPS-Koordinaten in Ortsnamen auf (offline)."""

    def standort_aufloesen(
        self, breitengrad: float, laengengrad: float
    ) -> StandortDaten | None:
        """Löst GPS-Koordinaten in StandortDaten auf.

        1. Koordinaten validieren (-90..90, -180..180, nicht (0.0, 0.0))
        2. reverse_geocoder.search() aufrufen
        3. Ergebnis in StandortDaten umwandeln:
           - stadt = result['name']
           - region = result['admin1']
           - land = result['cc']

        Returns:
            StandortDaten oder None bei ungültigen Koordinaten.

        Raises:
            ImportError: Wenn reverse_geocoder nicht installiert ist.
        """
        try:
            import reverse_geocoder as rg  # noqa: F811
        except ImportError:
            raise ImportError(
                "Das Paket 'reverse_geocoder' ist nicht installiert. "
                "Bitte installieren mit: pip install reverse_geocoder"
            )

        if not self._koordinaten_gueltig(breitengrad, laengengrad):
            return None

        try:
            results = rg.search([(breitengrad, laengengrad)])
        except Exception:
            logger.warning(
                "Reverse-Geocoding fehlgeschlagen für (%s, %s)",
                breitengrad,
                laengengrad,
            )
            return None

        if not results:
            logger.warning(
                "Keine Ergebnisse für Koordinaten (%s, %s)",
                breitengrad,
                laengengrad,
            )
            return None

        result = results[0]

        try:
            return StandortDaten(
                stadt=result["name"],
                region=result["admin1"],
                land=result["cc"],
                breitengrad=breitengrad,
                laengengrad=laengengrad,
            )
        except (KeyError, ValueError) as exc:
            logger.warning(
                "StandortDaten-Erstellung fehlgeschlagen für (%s, %s): %s",
                breitengrad,
                laengengrad,
                exc,
            )
            return None

    @staticmethod
    def _koordinaten_gueltig(breitengrad: float, laengengrad: float) -> bool:
        """Prüft ob Koordinaten gültig sind.

        Gültig wenn:
        - breitengrad ∈ [-90, 90]
        - laengengrad ∈ [-180, 180]
        - nicht (0.0, 0.0) (Null Island)
        """
        if not (-90.0 <= breitengrad <= 90.0):
            return False
        if not (-180.0 <= laengengrad <= 180.0):
            return False
        if breitengrad == 0.0 and laengengrad == 0.0:
            return False
        return True
