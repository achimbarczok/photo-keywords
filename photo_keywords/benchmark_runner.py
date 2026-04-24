"""BenchmarkRunner – Orchestriert den Benchmark-Modus für Modellvergleiche."""

from __future__ import annotations

import csv
import logging
import os
import time
from datetime import datetime

from photo_keywords.errors import BenchmarkError
from photo_keywords.gps_leser import GpsLeser
from photo_keywords.klassifikations_router import KlassifikationsRouter
from photo_keywords.models import (
    BenchmarkErgebnis,
    BenchmarkZusammenfassung,
    Config,
    StandortDaten,
)
from photo_keywords.ollama_client import OllamaClient
from photo_keywords.standort_resolver import StandortResolver

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".raw", ".dng"}


class BenchmarkRunner:
    """Führt Benchmarks über mehrere Ollama-Modelle durch."""

    def __init__(self, config: Config) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def benchmark_ausfuehren(
        self, image_dir: str, output_csv: str
    ) -> list[BenchmarkZusammenfassung]:
        """Führt den Benchmark durch.

        1. Bilddateien einlesen
        2. Pro Modell einen OllamaClient erstellen (gleicher Prompt)
        3. Pro Bild Antwortzeit messen
        4. Ergebnisse als CSV schreiben
        5. Zusammenfassung berechnen und ausgeben

        Raises:
            BenchmarkError: Bildverzeichnis nicht gefunden oder leer.
        """
        zeitstempel = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_csv = self._zeitgestempelter_pfad(output_csv, zeitstempel)
        bilder = self._bilder_einlesen(image_dir)
        ergebnisse: list[BenchmarkErgebnis] = []

        # Standort-Verarbeitung: GPS nur aus EXIF (kein Katalog im Benchmark)
        gps_leser = GpsLeser()
        standort_resolver = StandortResolver()

        # Pre-resolve standort for each image (shared across models)
        standort_map: dict[str, StandortDaten | None] = {}
        for image_path in bilder:
            standort_map[image_path] = self._standort_ermitteln(
                image_path, gps_leser, standort_resolver
            )

        # Create KlassifikationsRouter if classification is configured
        # Note: Router is created per benchmark model so that the standard_modell
        # matches the current benchmark model — avoids unnecessary model switches.

        for model_name in self.config.benchmark_models:
            klassifikations_router: KlassifikationsRouter | None = None
            if self.config.klassifikation is not None:
                klassifikations_router = KlassifikationsRouter(
                    endpoint=self.config.ollama_endpoint,
                    klassifikations_config=self.config.klassifikation,
                    standard_modell=model_name,
                    fallback_prompt=self.config.prompt_template,
                    validierungs_config=self.config.validierung,
                )

            client = OllamaClient(
                endpoint=self.config.ollama_endpoint,
                model_name=model_name,
                prompt_template=self.config.prompt_template,
                validierungs_config=self.config.validierung,
            )
            for image_path in bilder:
                image_name = os.path.basename(image_path)
                standort_daten = standort_map.get(image_path)
                standort_str = self._standort_als_string(standort_daten)
                try:
                    if klassifikations_router is not None:
                        start = time.perf_counter()
                        klass_ergebnis = klassifikations_router.bild_analysieren(
                            image_path, standort_daten
                        )
                        elapsed_ms = (time.perf_counter() - start) * 1000.0
                        ergebnisse.append(
                            BenchmarkErgebnis(
                                model_name=model_name,
                                image_name=image_name,
                                keywords=klass_ergebnis.keywords,
                                response_time_ms=elapsed_ms,
                                standort=standort_str,
                                foto_kategorie=klass_ergebnis.kategorie.value,
                                prompt_typ=klass_ergebnis.verwendeter_prompt_typ,
                                klassifikations_zeit_ms=klass_ergebnis.klassifikations_zeit_ms,
                            )
                        )
                        print(
                            f"  ✓ {model_name} | {image_name} | "
                            f"{len(klass_ergebnis.keywords)} Keywords | "
                            f"{elapsed_ms:.0f} ms | "
                            f"Kategorie: {klass_ergebnis.kategorie.value}"
                        )
                    else:
                        start = time.perf_counter()
                        keywords = client.analyse_bild(image_path, standort_daten)
                        elapsed_ms = (time.perf_counter() - start) * 1000.0
                        ergebnisse.append(
                            BenchmarkErgebnis(
                                model_name=model_name,
                                image_name=image_name,
                                keywords=keywords,
                                response_time_ms=elapsed_ms,
                                standort=standort_str,
                            )
                        )
                        print(
                            f"  ✓ {model_name} | {image_name} | "
                            f"{len(keywords)} Keywords | {elapsed_ms:.0f} ms"
                        )
                except Exception as exc:
                    logger.error(
                        "Benchmark-Fehler für Modell %s, Bild %s: %s",
                        model_name,
                        image_name,
                        exc,
                    )
                    ergebnisse.append(
                        BenchmarkErgebnis(
                            model_name=model_name,
                            image_name=image_name,
                            keywords=[],
                            response_time_ms=0.0,
                            standort=standort_str,
                            error=str(exc),
                        )
                    )
                    print(f"  ✗ {model_name} | {image_name} | FEHLER")

        self._ergebnisse_als_csv_schreiben(ergebnisse, output_csv, self.config.prompt_template)
        print(f"Benchmark-Ergebnisse: {output_csv}")
        zusammenfassungen = self._zusammenfassung_berechnen(ergebnisse)
        self._zusammenfassung_ausgeben(zusammenfassungen)
        return zusammenfassungen

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bilder_einlesen(self, image_dir: str) -> list[str]:
        """Liest alle Bilddateien aus dem Verzeichnis.

        Raises:
            BenchmarkError: Verzeichnis existiert nicht oder ist leer.
        """
        if not os.path.isdir(image_dir):
            raise BenchmarkError(
                f"Bildverzeichnis nicht gefunden: {image_dir}"
            )

        bilder: list[str] = []
        for entry in sorted(os.listdir(image_dir)):
            ext = os.path.splitext(entry)[1].lower()
            if ext in _IMAGE_EXTENSIONS:
                bilder.append(os.path.join(image_dir, entry))

        if not bilder:
            raise BenchmarkError(
                f"Keine Bilddateien im Verzeichnis gefunden: {image_dir}"
            )

        return bilder

    def _zeitgestempelter_pfad(self, output_csv: str, zeitstempel: str) -> str:
        """Erzeugt einen zeitgestempelten Dateinamen.

        Beispiel: './benchmark_results.csv' + '20250715_143022'
               -> './benchmark_results_20250715_143022.csv'
        """
        basis, ext = os.path.splitext(output_csv)
        return f"{basis}_{zeitstempel}{ext}"

    @staticmethod
    def _standort_ermitteln(
        image_path: str,
        gps_leser: GpsLeser,
        standort_resolver: StandortResolver,
    ) -> StandortDaten | None:
        """Ermittelt StandortDaten für ein Bild (nur EXIF-GPS, kein Katalog).

        Fehler werden protokolliert, aber nicht propagiert.
        """
        try:
            gps = gps_leser.gps_aus_exif(image_path)
        except Exception:
            logger.warning("GPS-Lesung fehlgeschlagen für %s", image_path)
            return None

        if gps is None:
            return None

        try:
            return standort_resolver.standort_aufloesen(gps[0], gps[1])
        except Exception:
            logger.warning(
                "Standort-Auflösung fehlgeschlagen für %s", image_path
            )
            return None

    @staticmethod
    def _standort_als_string(standort_daten: StandortDaten | None) -> str | None:
        """Formatiert StandortDaten als String für BenchmarkErgebnis.

        Format: "{stadt}, {land}" oder "{stadt}, {region}, {land}" wenn region != stadt.
        """
        if standort_daten is None:
            return None
        if standort_daten.region and standort_daten.region != standort_daten.stadt:
            return f"{standort_daten.stadt}, {standort_daten.region}, {standort_daten.land}"
        return f"{standort_daten.stadt}, {standort_daten.land}"

    def _ergebnisse_als_csv_schreiben(
        self, ergebnisse: list[BenchmarkErgebnis], output_path: str, prompt: str
    ) -> None:
        """Schreibt Benchmark-Ergebnisse als CSV.

        1. Kommentarzeile mit Prompt (Zeilenumbrüche durch Leerzeichen ersetzt)
        2. CSV-Header
        3. Ergebnisse als Datenzeilen

        Spalten: model, image, keywords, response_time_ms, standort
        Zusätzliche Spalten wenn Klassifikation vorhanden:
            foto_kategorie, prompt_typ, klassifikations_zeit_ms
        Keywords werden semikolon-getrennt gespeichert.
        """
        prompt_einzeilig = prompt.replace("\n", " ").replace("\r", " ")
        sortierte = sorted(ergebnisse, key=lambda e: (e.image_name, e.model_name))

        # Determine if classification columns should be included
        hat_klassifikation = any(e.foto_kategorie is not None for e in ergebnisse)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            f.write(f"# prompt: {prompt_einzeilig}\n")
            writer = csv.writer(f)

            header = ["model", "image", "keywords", "response_time_ms", "standort"]
            if hat_klassifikation:
                header.extend(["foto_kategorie", "prompt_typ", "klassifikations_zeit_ms"])
            writer.writerow(header)

            letztes_bild = None
            for e in sortierte:
                if letztes_bild is not None and e.image_name != letztes_bild:
                    f.write("\n")
                row = [
                    e.model_name,
                    e.image_name,
                    ";".join(sorted(e.keywords, key=str.casefold)),
                    e.response_time_ms,
                    e.standort or "",
                ]
                if hat_klassifikation:
                    row.extend([
                        e.foto_kategorie or "",
                        e.prompt_typ or "",
                        e.klassifikations_zeit_ms if e.klassifikations_zeit_ms is not None else "",
                    ])
                writer.writerow(row)
                letztes_bild = e.image_name

    def _zusammenfassung_berechnen(
        self, ergebnisse: list[BenchmarkErgebnis]
    ) -> list[BenchmarkZusammenfassung]:
        """Berechnet pro Modell: Anzahl verarbeiteter Bilder, Durchschnittszeit, Fehleranzahl, Klassifikationszeit."""
        modell_ergebnisse: dict[str, list[BenchmarkErgebnis]] = {}
        for e in ergebnisse:
            modell_ergebnisse.setdefault(e.model_name, []).append(e)

        zusammenfassungen: list[BenchmarkZusammenfassung] = []
        for model_name, model_results in modell_ergebnisse.items():
            erfolge = [r for r in model_results if r.error is None]
            fehler = len(model_results) - len(erfolge)
            durchschnitt = (
                sum(r.response_time_ms for r in erfolge) / len(erfolge)
                if erfolge
                else 0.0
            )

            # Calculate average classification time for successful results
            durchschnitt_klassifikations_ms: float | None = None
            erfolge_mit_klassifikation = [
                r for r in erfolge if r.klassifikations_zeit_ms is not None
            ]
            if erfolge_mit_klassifikation:
                durchschnitt_klassifikations_ms = (
                    sum(r.klassifikations_zeit_ms for r in erfolge_mit_klassifikation)  # type: ignore[misc]
                    / len(erfolge_mit_klassifikation)
                )

            zusammenfassungen.append(
                BenchmarkZusammenfassung(
                    model_name=model_name,
                    bilder_verarbeitet=len(erfolge),
                    durchschnitt_ms=durchschnitt,
                    fehler=fehler,
                    durchschnitt_klassifikations_ms=durchschnitt_klassifikations_ms,
                )
            )

        return zusammenfassungen

    def _zusammenfassung_ausgeben(
        self, zusammenfassungen: list[BenchmarkZusammenfassung]
    ) -> None:
        """Gibt die Zusammenfassung formatiert auf der Konsole aus."""
        print("\n=== Benchmark-Zusammenfassung ===")
        for z in zusammenfassungen:
            line = (
                f"Modell: {z.model_name} | "
                f"Verarbeitet: {z.bilder_verarbeitet} | "
                f"Durchschnitt: {z.durchschnitt_ms:.1f} ms | "
                f"Fehler: {z.fehler}"
            )
            if z.durchschnitt_klassifikations_ms is not None:
                line += f" | Klassifikation: {z.durchschnitt_klassifikations_ms:.1f} ms"
            print(line)
        print("=================================\n")
