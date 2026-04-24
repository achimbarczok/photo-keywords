"""Unit-Tests für main.py — CLI-Einstiegspunkt und Logging."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from photo_keywords.main import main, _parse_args
from photo_keywords.models import Config, BatchErgebnis


def _make_config(**overrides) -> Config:
    """Erzeugt ein Config-Objekt mit sinnvollen Standardwerten."""
    defaults = dict(
        catalog_path="/fake/catalog.lrcat",
        ollama_endpoint="http://localhost:11434",
        model_name="llava",
        batch_size=50,
        prompt_template="Describe this image.",
        tracking_db_path="/fake/tracking.db",
        log_file_path="/fake/keyword_generator.log",
        exiftool_path=None,
        benchmark_models=["moondream", "llava"],
        benchmark_output_csv="/fake/benchmark.csv",
    )
    defaults.update(overrides)
    return Config(**defaults)


# ------------------------------------------------------------------
# CLI-Argument-Parsing
# ------------------------------------------------------------------

class TestParseArgs:
    def test_config_only(self):
        args = _parse_args(["--config", "config.yaml"])
        assert args.config == "config.yaml"
        assert args.benchmark is None
        assert args.command == "keywords"

    def test_config_and_benchmark(self):
        args = _parse_args(["--config", "config.yaml", "--benchmark", "/imgs"])
        assert args.config == "config.yaml"
        assert args.benchmark == "/imgs"
        assert args.command == "keywords"

    def test_explicit_keywords_subcommand(self):
        args = _parse_args(["keywords", "--config", "config.yaml"])
        assert args.config == "config.yaml"
        assert args.command == "keywords"

    def test_gps_report_subcommand(self):
        args = _parse_args(["gps-report", "--config", "config.yaml"])
        assert args.config == "config.yaml"
        assert args.command == "gps-report"
        assert args.day is None
        assert args.month is None

    def test_gps_report_with_day(self):
        args = _parse_args(["gps-report", "--config", "config.yaml", "--day", "2024-08-26"])
        assert args.day == "2024-08-26"
        assert args.command == "gps-report"

    def test_gps_report_with_month(self):
        args = _parse_args(["gps-report", "--config", "config.yaml", "--month", "2024-08"])
        assert args.month == "2024-08"
        assert args.command == "gps-report"

    def test_missing_config_exits(self):
        with pytest.raises(SystemExit):
            _parse_args([])


# ------------------------------------------------------------------
# Requirement 8.4: Logdatei-Pfad wird auf Konsole ausgegeben
# ------------------------------------------------------------------

class TestLogFilePathPrinted:
    """Validates: Requirement 8.4 — Log file path is printed to console."""

    @patch("photo_keywords.main.StichwortSchreiber")
    @patch("photo_keywords.main.OllamaClient")
    @patch("photo_keywords.main.BatchProcessor")
    @patch("photo_keywords.main.VerarbeitungsTracker")
    @patch("photo_keywords.main.KatalogLeser")
    @patch("photo_keywords.main.ConfigLoader")
    def test_normal_mode_prints_log_path(
        self,
        mock_config_loader_cls,
        mock_katalog_cls,
        mock_tracker_cls,
        mock_batch_cls,
        mock_ollama_cls,
        mock_schreiber_cls,
        capsys,
        tmp_path,
    ):
        log_path = str(tmp_path / "test.log")
        config = _make_config(log_file_path=log_path)

        mock_config_loader_cls.return_value.load.return_value = config
        mock_katalog_cls.return_value.alle_fotos_lesen.return_value = []
        mock_tracker_cls.return_value.unverarbeitete_filtern.return_value = []

        main(["--config", "config.yaml"])

        captured = capsys.readouterr()
        assert f"Logdatei: {log_path}" in captured.out

    @patch("photo_keywords.main.BenchmarkRunner")
    @patch("photo_keywords.main.ConfigLoader")
    def test_benchmark_mode_prints_log_path(
        self,
        mock_config_loader_cls,
        mock_runner_cls,
        capsys,
        tmp_path,
    ):
        log_path = str(tmp_path / "bench.log")
        config = _make_config(log_file_path=log_path)

        mock_config_loader_cls.return_value.load.return_value = config
        mock_runner_cls.return_value.benchmark_ausfuehren.return_value = []

        main(["--config", "config.yaml", "--benchmark", "/imgs"])

        captured = capsys.readouterr()
        assert f"Logdatei: {log_path}" in captured.out


# ------------------------------------------------------------------
# Fatal error handling
# ------------------------------------------------------------------

class TestFatalErrorHandling:
    @patch("photo_keywords.main.ConfigLoader")
    def test_config_error_exits_with_message(
        self, mock_config_loader_cls, capsys
    ):
        from photo_keywords.errors import ConfigError

        mock_config_loader_cls.return_value.load.side_effect = ConfigError(
            "Pflichtparameter fehlt: catalog_path"
        )

        with pytest.raises(SystemExit) as exc_info:
            main(["--config", "missing.yaml"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Pflichtparameter fehlt: catalog_path" in captured.err


# ------------------------------------------------------------------
# Resource cleanup
# ------------------------------------------------------------------

class TestResourceCleanup:
    @patch("photo_keywords.main.StichwortSchreiber")
    @patch("photo_keywords.main.OllamaClient")
    @patch("photo_keywords.main.VerarbeitungsTracker")
    @patch("photo_keywords.main.KatalogLeser")
    @patch("photo_keywords.main.ConfigLoader")
    def test_resources_closed_on_error(
        self,
        mock_config_loader_cls,
        mock_katalog_cls,
        mock_tracker_cls,
        mock_ollama_cls,
        mock_schreiber_cls,
        tmp_path,
    ):
        log_path = str(tmp_path / "test.log")
        config = _make_config(log_file_path=log_path)

        mock_config_loader_cls.return_value.load.return_value = config

        mock_katalog = mock_katalog_cls.return_value
        mock_katalog.alle_fotos_lesen.return_value = []

        mock_tracker = mock_tracker_cls.return_value
        mock_tracker.unverarbeitete_filtern.return_value = []

        main(["--config", "config.yaml"])

        mock_katalog.close.assert_called_once()
        mock_tracker.close.assert_called_once()
