"""BatchProcessor – Orchestriert die Batch-Verarbeitung von Fotos."""

from __future__ import annotations

import logging
import sqlite3
import time
from collections import Counter
from typing import TYPE_CHECKING

from lightroom_ollama_keywords.models import BatchErgebnis, FotoEintrag, StandortDaten

if TYPE_CHECKING:
    from lightroom_ollama_keywords.gps_leser import GpsLeser
    from lightroom_ollama_keywords.klassifikations_router import KlassifikationsRouter
    from lightroom_ollama_keywords.ollama_client import OllamaClient
    from lightroom_ollama_keywords.standort_resolver import StandortResolver
    from lightroom_ollama_keywords.stichwort_schreiber import StichwortSchreiber
    from lightroom_ollama_keywords.verarbeitungs_tracker import VerarbeitungsTracker

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Verarbeitet einen Batch von Fotos: Analyse, Stichwörter schreiben, Tracking."""

    def __init__(
        self,
        ollama: OllamaClient,
        schreiber: StichwortSchreiber,
        tracker: VerarbeitungsTracker,
        model_name: str,
        model_version: str,
        klassifikations_router: KlassifikationsRouter | None = None,
        gps_leser: GpsLeser | None = None,
        standort_resolver: StandortResolver | None = None,
        katalog_conn: sqlite3.Connection | None = None,
    ) -> None:
        self._ollama = ollama
        self._schreiber = schreiber
        self._tracker = tracker
        self._model_name = model_name
        self._model_version = model_version
        self._klassifikations_router = klassifikations_router
        self._gps_leser = gps_leser
        self._standort_resolver = standort_resolver
        self._katalog_conn = katalog_conn

    def batch_verarbeiten(self, fotos: list[FotoEintrag]) -> BatchErgebnis:
        """Verarbeitet einen Batch von Fotos.

        Für jedes Foto:
        1. Fortschritt auf Konsole ausgeben
        2. GPS ermitteln → Standort auflösen (wenn gps_leser und standort_resolver vorhanden)
        3. Bild über KlassifikationsRouter (wenn vorhanden) oder OllamaClient analysieren
        4. Standort-Stichwörter + KI-Stichwörter zusammenführen
        5. Zusammengeführte Stichwörter über StichwortSchreiber schreiben
        6. Verarbeitung im Tracker protokollieren
        7. Bei Fehler: protokollieren und mit nächstem Foto fortfahren

        Am Ende: Zusammenfassung (inkl. Kategorie-Statistik) und Lightroom-Hinweis ausgeben.
        """
        gesamt = len(fotos)
        verarbeitet = 0
        fehler = 0
        fehler_details: list[str] = []
        kategorie_zaehler: Counter[str] = Counter()

        from datetime import datetime, timedelta

        start = time.monotonic()
        start_zeit = datetime.now()
        print(f"Gestartet: {start_zeit.strftime('%H:%M:%S')}")

        for index, foto in enumerate(fotos, start=1):
            verbleibend = gesamt - index

            # Zeitschätzung berechnen
            vergangen = time.monotonic() - start
            if index > 1:
                durchschnitt_pro_foto = vergangen / (index - 1)
                rest_sekunden = durchschnitt_pro_foto * verbleibend
                rest_td = timedelta(seconds=int(rest_sekunden))
                fertig_um = datetime.now() + timedelta(seconds=rest_sekunden)
                zeit_info = f"~{rest_td} verbleibend, fertig ~{fertig_um.strftime('%H:%M')}"
            else:
                zeit_info = "berechne..."

            print(f"[{index}/{gesamt}] Verarbeite: {foto.file_path}")
            print(f"  noch {verbleibend}, {zeit_info}")
            logger.info("Verarbeite Foto %d/%d: %s", index, gesamt, foto.file_path)

            try:
                # GPS ermitteln und Standort auflösen
                standort_daten = self._standort_ermitteln(foto)

                if standort_daten is not None:
                    print(f"  Standort: {standort_daten.stadt}, {standort_daten.land}")
                elif self._gps_leser is not None:
                    print(f"  Standort: kein GPS")

                if self._klassifikations_router is not None:
                    ergebnis = self._klassifikations_router.bild_analysieren(
                        foto.file_path, standort_daten
                    )
                    keywords = ergebnis.keywords
                    kategorie_name = ergebnis.kategorie.value
                    kategorie_zaehler[kategorie_name] += 1
                    # Kategorie als Stichwort hinzufügen
                    if kategorie_name not in keywords:
                        keywords = [kategorie_name] + keywords
                    print(f"  Kategorie: {kategorie_name}, Modell: {ergebnis.verwendetes_modell}")
                else:
                    keywords = self._ollama.analyse_bild(
                        foto.file_path, standort_daten
                    )

                # Standort-Stichwörter + KI-Stichwörter zusammenführen
                alle_keywords = self._keywords_zusammenfuehren(keywords, standort_daten)

                self._schreiber.stichwörter_schreiben(foto.file_path, alle_keywords)
                self._tracker.verarbeitung_speichern(
                    foto.file_path, self._model_name, self._model_version
                )
                verarbeitet += 1
                logger.info("Erfolgreich: %s -> %s", foto.file_path, alle_keywords)
            except Exception as exc:
                fehler += 1
                detail = f"{foto.file_path}: {exc}"
                fehler_details.append(detail)
                logger.error("Fehler bei %s: %s", foto.file_path, exc)
                self._tracker.fehler_speichern(
                    foto.file_path, self._model_name, str(exc)
                )

        dauer = time.monotonic() - start
        ende_zeit = datetime.now()

        # Zusammenfassung ausgeben
        stunden = dauer / 3600
        print(f"\n--- Zusammenfassung ---")
        print(f"Gestartet: {start_zeit.strftime('%H:%M:%S')}")
        print(f"Beendet:   {ende_zeit.strftime('%H:%M:%S')}")
        if dauer >= 3600:
            print(f"Dauer: {dauer:.1f}s ({stunden:.1f}h)")
        elif dauer >= 60:
            print(f"Dauer: {dauer:.1f}s ({dauer / 60:.1f}min)")
        else:
            print(f"Dauer: {dauer:.1f}s")
        print(f"Verarbeitet: {verarbeitet}")
        print(f"Fehler: {fehler}")

        if kategorie_zaehler:
            print("Fotos pro Kategorie:")
            for kategorie, anzahl in sorted(kategorie_zaehler.items()):
                print(f"  {kategorie}: {anzahl}")

        if fehler_details:
            print("Fehlerdetails:")
            for detail in fehler_details:
                print(f"  - {detail}")

        print("\nBitte in Lightroom 'Metadaten aus Datei lesen' ausführen")

        return BatchErgebnis(
            verarbeitet=verarbeitet,
            fehler=fehler,
            dauer_sekunden=dauer,
            fehler_details=fehler_details,
        )

    # ------------------------------------------------------------------
    # Standort-Verarbeitung
    # ------------------------------------------------------------------

    def _standort_ermitteln(self, foto: FotoEintrag) -> StandortDaten | None:
        """Ermittelt Standortdaten für ein Foto (GPS → Reverse-Geocoding).

        Returns None wenn gps_leser oder standort_resolver nicht konfiguriert,
        oder wenn kein GPS gefunden wird.
        """
        if self._gps_leser is None or self._standort_resolver is None:
            return None

        try:
            gps = self._gps_leser.gps_ermitteln(
                foto.file_path, self._katalog_conn, foto.image_id
            )
        except Exception:
            logger.warning("GPS-Ermittlung fehlgeschlagen für %s", foto.file_path)
            return None

        if gps is None:
            return None

        try:
            return self._standort_resolver.standort_aufloesen(gps[0], gps[1])
        except Exception:
            logger.warning(
                "Standort-Auflösung fehlgeschlagen für %s (%s)",
                foto.file_path,
                gps,
            )
            return None

    @staticmethod
    def _keywords_zusammenfuehren(
        ki_keywords: list[str], standort_daten: StandortDaten | None
    ) -> list[str]:
        """Führt KI-Keywords und Standort-Stichwörter zusammen.

        1. Standort-Stichwörter aus standort_daten.als_stichwort_liste()
        2. Leere Strings herausfiltern
        3. Mit KI-Keywords vereinigen (ohne Duplikate, Reihenfolge: Standort zuerst)
        """
        if standort_daten is None:
            seen: set[str] = set()
            ergebnis: list[str] = []
            for kw in ki_keywords:
                if kw and kw not in seen:
                    seen.add(kw)
                    ergebnis.append(kw)
            return ergebnis

        standort_keywords = [kw for kw in standort_daten.als_stichwort_liste() if kw]

        seen: set[str] = set()
        ergebnis: list[str] = []

        # Standort-Stichwörter zuerst
        for kw in standort_keywords:
            if kw and kw not in seen:
                seen.add(kw)
                ergebnis.append(kw)

        # KI-Keywords danach
        for kw in ki_keywords:
            if kw and kw not in seen:
                seen.add(kw)
                ergebnis.append(kw)

        return ergebnis
