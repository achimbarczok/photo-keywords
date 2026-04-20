"""Property-Tests für BenchmarkRunner mit Klassifikation."""

from __future__ import annotations

import csv
import io
import os
import tempfile

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lightroom_ollama_keywords.benchmark_runner import BenchmarkRunner
from lightroom_ollama_keywords.models import (
    BenchmarkErgebnis,
    BenchmarkZusammenfassung,
    Config,
    FotoKategorie,
)


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

_foto_kategorie_strategy = st.sampled_from([k.value for k in FotoKategorie])

_benchmark_ergebnis_with_classification_strategy = st.builds(
    BenchmarkErgebnis,
    model_name=_safe_text,
    image_name=_safe_text.map(lambda s: s + ".jpg"),
    keywords=_keyword_strategy,
    response_time_ms=st.floats(min_value=0.1, max_value=100_000.0, allow_nan=False, allow_infinity=False),
    error=st.none(),
    foto_kategorie=_foto_kategorie_strategy,
    prompt_typ=_safe_text,
    klassifikations_zeit_ms=st.floats(min_value=0.1, max_value=50_000.0, allow_nan=False, allow_infinity=False),
)


# ---------------------------------------------------------------------------
# Property 6: Erweiterte Benchmark-CSV Round-Trip (Task 7.4)
# ---------------------------------------------------------------------------

class TestPropertyErweiterteBenchmarkCsvRoundTrip:
    """Property 6: Erweiterte Benchmark-CSV Round-Trip

    Für alle Listen von BenchmarkErgebnis-Objekten mit Klassifikationsfeldern:
    Schreiben als CSV und Einlesen ergibt äquivalente Daten inkl.
    Klassifikationsspalten.

    **Validates: Requirements 7.2**
    """

    @given(ergebnisse=st.lists(
        _benchmark_ergebnis_with_classification_strategy, min_size=0, max_size=20
    ))
    @settings(max_examples=100)
    def test_csv_round_trip_mit_klassifikation(self, ergebnisse: list[BenchmarkErgebnis]):
        config = _make_config()
        runner = BenchmarkRunner(config)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as tmp:
            csv_path = tmp.name

        try:
            runner._ergebnisse_als_csv_schreiben(ergebnisse, csv_path, "test prompt")

            with open(csv_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()

            filtered_lines = [
                line for line in all_lines
                if not line.startswith("#") and line.strip() != ""
            ]

            reader = csv.DictReader(io.StringIO("".join(filtered_lines)))
            rows = list(reader)

            assert len(rows) == len(ergebnisse)

            sortierte = sorted(
                ergebnisse, key=lambda e: (e.image_name, e.model_name)
            )

            for original, row in zip(sortierte, rows):
                assert row["model"] == original.model_name
                assert row["image"] == original.image_name

                if original.keywords:
                    assert row["keywords"] == ";".join(sorted(original.keywords, key=str.casefold))
                else:
                    assert row["keywords"] == ""

                assert float(row["response_time_ms"]) == pytest.approx(
                    original.response_time_ms, rel=1e-6
                )

                # Classification columns
                if original.foto_kategorie is not None:
                    assert "foto_kategorie" in row
                    assert "prompt_typ" in row
                    assert "klassifikations_zeit_ms" in row

                    assert row["foto_kategorie"] == original.foto_kategorie
                    assert row["prompt_typ"] == (original.prompt_typ or "")
                    assert float(row["klassifikations_zeit_ms"]) == pytest.approx(
                        original.klassifikations_zeit_ms, rel=1e-6  # type: ignore[arg-type]
                    )
        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# Property 7: Benchmark-Zusammenfassung mit Klassifikationszeit (Task 7.5)
# ---------------------------------------------------------------------------

_model_name_strategy = st.sampled_from(["moondream", "llava", "gemma3", "minicpm-v"])

_benchmark_ergebnis_with_classification_and_optional_error = st.builds(
    BenchmarkErgebnis,
    model_name=_model_name_strategy,
    image_name=_safe_text.map(lambda s: s + ".jpg"),
    keywords=_keyword_strategy,
    response_time_ms=st.floats(
        min_value=0.1, max_value=100_000.0, allow_nan=False, allow_infinity=False
    ),
    error=st.one_of(st.none(), _safe_text),
    foto_kategorie=_foto_kategorie_strategy,
    prompt_typ=_safe_text,
    klassifikations_zeit_ms=st.floats(
        min_value=0.1, max_value=50_000.0, allow_nan=False, allow_infinity=False
    ),
)


class TestPropertyBenchmarkZusammenfassungKlassifikationszeit:
    """Property 7: Benchmark-Zusammenfassung mit Klassifikationszeit

    Für alle Listen von BenchmarkErgebnis-Objekten mit Klassifikationszeiten:
    durchschnitt_klassifikations_ms entspricht dem arithmetischen Mittel der
    erfolgreichen Klassifikationszeiten pro Modell.

    **Validates: Requirements 7.3**
    """

    @given(
        ergebnisse=st.lists(
            _benchmark_ergebnis_with_classification_and_optional_error,
            min_size=1,
            max_size=30,
        )
    )
    @settings(max_examples=100)
    def test_durchschnitt_klassifikations_ms(
        self, ergebnisse: list[BenchmarkErgebnis]
    ):
        config = _make_config()
        runner = BenchmarkRunner(config)

        zusammenfassungen = runner._zusammenfassung_berechnen(ergebnisse)

        # Collect expected per-model data
        expected_models: dict[str, list[BenchmarkErgebnis]] = {}
        for e in ergebnisse:
            expected_models.setdefault(e.model_name, []).append(e)

        for z in zusammenfassungen:
            model_results = expected_models[z.model_name]
            erfolge = [r for r in model_results if r.error is None]
            erfolge_mit_klassifikation = [
                r for r in erfolge if r.klassifikations_zeit_ms is not None
            ]

            if erfolge_mit_klassifikation:
                expected_avg = (
                    sum(r.klassifikations_zeit_ms for r in erfolge_mit_klassifikation)  # type: ignore[misc]
                    / len(erfolge_mit_klassifikation)
                )
                assert z.durchschnitt_klassifikations_ms is not None
                assert z.durchschnitt_klassifikations_ms == pytest.approx(
                    expected_avg, rel=1e-6
                )
            else:
                assert z.durchschnitt_klassifikations_ms is None
