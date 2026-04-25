"""GpsReport – Erstellt einen Bericht über Fotos ohne GPS-Daten."""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from datetime import datetime

from photo_keywords.config_loader import ConfigLoader
from photo_keywords.gps_leser import GpsLeser
from photo_keywords.katalog_leser import KatalogLeser
from photo_keywords.models import Config, FotoEintrag

logger = logging.getLogger(__name__)

_YYMMDD_PATTERN = re.compile(r"^(\d{6})")


class GpsReport:
    """Erstellt einen Bericht über Fotos mit und ohne GPS-Daten."""

    def __init__(self, config: Config) -> None:
        self._config = config

    def bericht_erstellen(
        self,
        tag: str | None = None,
        monat: str | None = None,
    ) -> None:
        """Erstellt und gibt den GPS-Bericht aus.

        Args:
            tag: Optionaler Filter im Format YYYY-MM-DD.
            monat: Optionaler Filter im Format YYYY-MM.
        """
        katalog = KatalogLeser(self._config.catalog_path)
        try:
            fotos = katalog.alle_fotos_lesen()
        finally:
            katalog.close()

        gps_leser = GpsLeser()
        gesamt_fotos = len(fotos)

        # Fotos nach Datum gruppieren und GPS-Status prüfen
        tage_mit_gps: dict[str, list[str]] = defaultdict(list)
        tage_ohne_gps: dict[str, list[str]] = defaultdict(list)

        print(f"Prüfe {gesamt_fotos} Fotos auf GPS-Daten...")
        for i, foto in enumerate(fotos, start=1):
            if i % 500 == 0 or i == gesamt_fotos:
                print(f"  {i}/{gesamt_fotos}...", end="\r")
            datum = self._datum_aus_dateiname(foto.file_path)
            try:
                hat_gps = gps_leser.gps_aus_exif(foto.file_path) is not None
            except Exception:
                hat_gps = False

            if hat_gps:
                tage_mit_gps[datum].append(foto.file_path)
            else:
                tage_ohne_gps[datum].append(foto.file_path)

        # Alle Tage sammeln
        alle_tage = sorted(set(list(tage_mit_gps.keys()) + list(tage_ohne_gps.keys())))

        # Filter anwenden
        if tag is not None:
            alle_tage = [t for t in alle_tage if t == tag]
        elif monat is not None:
            alle_tage = [t for t in alle_tage if t.startswith(monat)]

        # Bericht ausgeben
        gesamt_ohne = 0
        gesamt_mit = 0

        print("\n=== Fotos ohne GPS-Daten ===\n")

        for datum in alle_tage:
            ohne = tage_ohne_gps.get(datum, [])
            mit = tage_mit_gps.get(datum, [])
            anzahl_ohne = len(ohne)
            anzahl_mit = len(mit)
            gesamt_ohne += anzahl_ohne
            gesamt_mit += anzahl_mit

            if anzahl_ohne > 0:
                print(f"{datum} ({anzahl_ohne} ohne GPS, {anzahl_mit} mit GPS)")
                for pfad in sorted(ohne):
                    print(f"  {pfad}")
                print()

        gesamt = gesamt_ohne + gesamt_mit
        print(f"Gesamt: {gesamt_ohne} ohne GPS, {gesamt_mit} mit GPS (von {gesamt} Fotos)")

    @staticmethod
    def _datum_aus_dateiname(file_path: str) -> str:
        """Extrahiert das Datum aus dem Dateinamen (YYMMDD-Muster).

        Versucht die ersten 6 Ziffern des Dateinamens als YYMMDD zu parsen.
        Bei Fehler wird das Datei-Änderungsdatum verwendet.

        Returns:
            Datum als String im Format YYYY-MM-DD.
        """
        basename = os.path.basename(file_path)
        match = _YYMMDD_PATTERN.match(basename)

        if match:
            yymmdd = match.group(1)
            try:
                dt = datetime.strptime(yymmdd, "%y%m%d")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Fallback: Datei-Änderungsdatum
        try:
            mtime = os.path.getmtime(file_path)
            dt = datetime.fromtimestamp(mtime)
            return dt.strftime("%Y-%m-%d")
        except OSError:
            return "unbekannt"
