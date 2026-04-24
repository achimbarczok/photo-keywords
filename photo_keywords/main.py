"""CLI-Einstiegspunkt für den Photo Keywords Generator."""

from __future__ import annotations

import argparse
import logging
import sys

from photo_keywords.batch_processor import BatchProcessor
from photo_keywords.benchmark_runner import BenchmarkRunner
from photo_keywords.config_loader import ConfigLoader
from photo_keywords.errors import KeywordGeneratorError
from photo_keywords.gps_leser import GpsLeser
from photo_keywords.katalog_leser import KatalogLeser
from photo_keywords.klassifikations_router import KlassifikationsRouter
from photo_keywords.ollama_client import OllamaClient
from photo_keywords.standort_resolver import StandortResolver
from photo_keywords.stichwort_schreiber import StichwortSchreiber
from photo_keywords.verarbeitungs_tracker import VerarbeitungsTracker

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parst die CLI-Argumente mit Subcommands."""
    parser = argparse.ArgumentParser(
        description="Photo Keywords Generator — "
        "Automatische Stichwort-Vergabe für Lightroom-Fotos über Ollama.",
    )

    subparsers = parser.add_subparsers(dest="command")

    # --- keywords subcommand ---
    kw_parser = subparsers.add_parser(
        "keywords",
        help="Stichwörter für Fotos generieren.",
    )
    kw_parser.add_argument(
        "--config",
        required=True,
        help="Pfad zur YAML-Konfigurationsdatei.",
    )
    kw_parser.add_argument(
        "--benchmark",
        default=None,
        help="Verzeichnis mit Testbildern für den Benchmark-Modus.",
    )
    kw_parser.add_argument(
        "--retry-errors",
        action="store_true",
        default=False,
        help="Zuvor fehlgeschlagene Fotos erneut verarbeiten.",
    )

    # --- gps-report subcommand ---
    gps_parser = subparsers.add_parser(
        "gps-report",
        help="GPS-Bericht für Fotos im Katalog erstellen.",
    )
    gps_parser.add_argument(
        "--config",
        required=True,
        help="Pfad zur YAML-Konfigurationsdatei.",
    )
    gps_parser.add_argument(
        "--day",
        default=None,
        help="Nur Fotos eines bestimmten Tages anzeigen (Format: YYYY-MM-DD).",
    )
    gps_parser.add_argument(
        "--month",
        default=None,
        help="Nur Fotos eines bestimmten Monats anzeigen (Format: YYYY-MM).",
    )

    # Default to 'keywords' if no subcommand given — backward compatibility
    effective_argv = argv if argv is not None else sys.argv[1:]
    if effective_argv and effective_argv[0] not in ("keywords", "gps-report"):
        effective_argv = ["keywords"] + list(effective_argv)
    elif not effective_argv:
        effective_argv = ["keywords"] + list(effective_argv)

    args = parser.parse_args(effective_argv)

    return args


def _setup_logging(log_file_path: str) -> None:
    """Richtet das Logging ein: Datei-Handler + Konsolen-Handler."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Datei-Handler — alle Details
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root_logger.addHandler(file_handler)

    # Konsolen-Handler — nur INFO+
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("[%(levelname)s] %(message)s")
    )
    root_logger.addHandler(console_handler)


def _run_normal(config_path: str, retry_errors: bool = False) -> None:
    """Normaler Modus: Fotos aus Katalog lesen, analysieren, Stichwörter schreiben."""
    loader = ConfigLoader()
    config = loader.load(config_path)

    _setup_logging(config.log_file_path)
    print(f"Logdatei: {config.log_file_path}")

    logger.info("=== Photo Keywords Generator gestartet ===")
    logger.info("Konfiguration geladen: %s", config_path)

    katalog: KatalogLeser | None = None
    tracker: VerarbeitungsTracker | None = None
    schreiber: StichwortSchreiber | None = None

    try:
        # Katalog lesen
        katalog = KatalogLeser(config.catalog_path)
        fotos = katalog.alle_fotos_lesen()
        logger.info("Fotos im Katalog: %d", len(fotos))

        # Tracker öffnen und filtern
        tracker = VerarbeitungsTracker(config.tracking_db_path)

        if retry_errors:
            anzahl = tracker.fehler_zuruecksetzen(config.model_name)
            if anzahl > 0:
                print(f"Fehler zurückgesetzt: {anzahl} Fotos werden erneut verarbeitet.")
                logger.info("Fehler zurückgesetzt: %d Einträge für Modell %s", anzahl, config.model_name)

        unverarbeitet = tracker.unverarbeitete_filtern(fotos, config.model_name)
        logger.info("Unverarbeitete Fotos: %d", len(unverarbeitet))

        if not unverarbeitet:
            print("Keine unverarbeiteten Fotos gefunden.")
            logger.info("Keine unverarbeiteten Fotos — Beende.")
            return

        # Batch erstellen (max batch_size)
        batch = unverarbeitet[: config.batch_size]
        logger.info("Batch-Größe: %d", len(batch))

        # Ollama-Client und Modellversion
        ollama = OllamaClient(
            endpoint=config.ollama_endpoint,
            model_name=config.model_name,
            prompt_template=config.prompt_template,
            validierungs_config=config.validierung,
        )
        model_version = ollama.modell_version_abfragen()
        logger.info("Modellversion: %s", model_version)

        # StichwortSchreiber
        schreiber = StichwortSchreiber(exiftool_path=config.exiftool_path)

        # KlassifikationsRouter (optional)
        klassifikations_router: KlassifikationsRouter | None = None
        if config.klassifikation is not None:
            klassifikations_router = KlassifikationsRouter(
                endpoint=config.ollama_endpoint,
                klassifikations_config=config.klassifikation,
                standard_modell=config.model_name,
                fallback_prompt=config.prompt_template,
                validierungs_config=config.validierung,
            )
            logger.info("Klassifikation aktiviert: Modell %s", config.klassifikation.modell)

        # Standort-Funktionalität (optional)
        gps_leser: GpsLeser | None = None
        standort_resolver: StandortResolver | None = None
        katalog_conn = None
        if config.standort.enabled:
            gps_leser = GpsLeser()
            standort_resolver = StandortResolver()
            katalog_conn = katalog._conn
            logger.info("Standort-Funktionalität aktiviert")

        # BatchProcessor
        processor = BatchProcessor(
            ollama=ollama,
            schreiber=schreiber,
            tracker=tracker,
            model_name=config.model_name,
            model_version=model_version,
            klassifikations_router=klassifikations_router,
            gps_leser=gps_leser,
            standort_resolver=standort_resolver,
            katalog_conn=katalog_conn,
        )
        ergebnis = processor.batch_verarbeiten(batch)

        logger.info(
            "Batch abgeschlossen: %d verarbeitet, %d Fehler, %.1fs",
            ergebnis.verarbeitet,
            ergebnis.fehler,
            ergebnis.dauer_sekunden,
        )
        logger.info("=== Verarbeitung beendet ===")

    finally:
        if schreiber is not None:
            schreiber.close()
        if tracker is not None:
            tracker.close()
        if katalog is not None:
            katalog.close()


def _run_benchmark(config_path: str, image_dir: str) -> None:
    """Benchmark-Modus: Testbilder an mehrere Modelle senden und vergleichen."""
    loader = ConfigLoader()
    config = loader.load(config_path)

    _setup_logging(config.log_file_path)
    print(f"Logdatei: {config.log_file_path}")

    logger.info("=== Benchmark-Modus gestartet ===")
    logger.info("Bildverzeichnis: %s", image_dir)

    runner = BenchmarkRunner(config)
    runner.benchmark_ausfuehren(image_dir, config.benchmark_output_csv)

    logger.info("=== Benchmark beendet ===")


def _run_gps_report(config_path: str, day: str | None = None, month: str | None = None) -> None:
    """GPS-Bericht: Fotos ohne GPS-Daten auflisten."""
    from photo_keywords.gps_report import GpsReport

    loader = ConfigLoader()
    config = loader.load(config_path)

    report = GpsReport(config)
    report.bericht_erstellen(tag=day, monat=month)


def main(argv: list[str] | None = None) -> None:
    """Haupteinstiegspunkt."""
    args = _parse_args(argv)

    try:
        if args.command == "gps-report":
            _run_gps_report(args.config, day=args.day, month=args.month)
        elif args.benchmark:
            _run_benchmark(args.config, args.benchmark)
        else:
            _run_normal(args.config, retry_errors=args.retry_errors)
    except KeywordGeneratorError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        logger.error("Fataler Fehler: %s", exc)
        sys.exit(1)
    except Exception as exc:
        print(f"Unerwarteter Fehler: {exc}", file=sys.stderr)
        logger.exception("Unerwarteter Fehler")
        sys.exit(1)


if __name__ == "__main__":
    main()
