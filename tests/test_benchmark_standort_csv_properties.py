"""Property-basierte Tests für Benchmark-CSV Standort Round-Trip."""

from __future__ import annotations

import csv
import io
import os
import tempfile

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from photo_keywords.benchmark_runner import BenchmarkRunner
from photo_keywords.models import BenchmarkErgebnis, Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> Config:
    """Creates a Config with sensible defaults for benchmark testing."""
    defaults = dict(
        catalog_path="dummy.lrcat",
        ollama_endpoint="http://localhost:11434",
        model_name="llava",
        batch_size=50,
        prompt_template="Describe this image with keywords.",
        tracking_db_path="./tracking.db",
        log_file_path="./test.log",
        exiftool_path=None,
        benchmark_models=["moondream", "llava:7b"],
        benchmark_output_csv="./benchmark.csv",
    )
    defaults.update(overrides)
    return Config(**defaults)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="_-",
    ),
    min_size=1,
    max_size=20,
)

_keyword_strategy = st.lists(
    _safe_text.filter(lambda s: ";" not in s and "\n" not in s and "\r" not in s),
    min_size=0,
    max_size=5,
)

# Standort strings like "Berlin, DE" or "München, Bayern, DE"
_standort_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters=" ,-",
    ),
    min_size=3,
    max_size=40,
).filter(lambda s: s.strip() != "" and "\n" not in s and "\r" not in s)

_optional_standort = st.one_of(st.none(), _standort_text)

_benchmark_ergebnis_with_standort = st.builds(
    BenchmarkErgebnis,
    model_name=_safe_text,
    image_name=_safe_text.map(lambda s: s + ".jpg"),
    keywords=_keyword_strategy,
    response_time_ms=st.floats(
        min_value=0.1, max_value=100_000.0, allow_nan=False, allow_infinity=False
    ),
    error=st.none(),
    standort=_optional_standort,
)


# ---------------------------------------------------------------------------
# Property 9: Benchmark-CSV Standort Round-Trip
# ---------------------------------------------------------------------------


class TestProperty9BenchmarkCsvStandortRoundTrip:
    """**Validates: Requirements 6.5**

    Property 9: Benchmark-CSV Standort Round-Trip

    Für alle Listen von BenchmarkErgebnis-Objekten mit optionalem
    `standort`-Feld soll das Schreiben als CSV und anschließende Einlesen
    die Standort-Werte korrekt wiedergeben. Einträge mit Standort sollen
    den Standort-String in der CSV-Spalte enthalten, Einträge ohne Standort
    sollen einen leeren Wert haben.
    """

    @given(
        ergebnisse=st.lists(
            _benchmark_ergebnis_with_standort, min_size=0, max_size=20
        )
    )
    @settings(max_examples=100)
    def test_standort_csv_round_trip(
        self, ergebnisse: list[BenchmarkErgebnis]
    ) -> None:
        config = _make_config()
        runner = BenchmarkRunner(config)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as tmp:
            csv_path = tmp.name

        try:
            runner._ergebnisse_als_csv_schreiben(
                ergebnisse, csv_path, "test prompt"
            )

            # Read back, skipping comment lines and blank lines
            with open(csv_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()

            filtered_lines = [
                line
                for line in all_lines
                if not line.startswith("#") and line.strip() != ""
            ]

            reader = csv.DictReader(io.StringIO("".join(filtered_lines)))
            rows = list(reader)

            assert len(rows) == len(ergebnisse)

            # Rows are sorted by (image_name, model_name)
            sortierte = sorted(
                ergebnisse, key=lambda e: (e.image_name, e.model_name)
            )

            for original, row in zip(sortierte, rows):
                if original.standort is not None:
                    # Entries with standort have the correct string
                    assert row["standort"] == original.standort
                else:
                    # Entries without standort have empty string
                    assert row["standort"] == ""
        finally:
            os.unlink(csv_path)
