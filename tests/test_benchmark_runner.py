"""Tests für BenchmarkRunner – Property-Tests und Unit-Tests."""

from __future__ import annotations

import csv
import io
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from photo_keywords.benchmark_runner import BenchmarkRunner
from photo_keywords.errors import BenchmarkError
from photo_keywords.models import (
    BenchmarkErgebnis,
    BenchmarkZusammenfassung,
    Config,
)


# ---------------------------------------------------------------------------
# Helpers / Fixtures
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


def _create_test_images(directory: str, names: list[str] | None = None) -> list[str]:
    """Creates tiny dummy image files in the given directory."""
    if names is None:
        names = ["test1.jpg", "test2.png"]
    paths = []
    for name in names:
        path = os.path.join(directory, name)
        with open(path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0")  # minimal JPEG header bytes
        paths.append(path)
    return paths


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

_benchmark_ergebnis_strategy = st.builds(
    BenchmarkErgebnis,
    model_name=_safe_text,
    image_name=_safe_text.map(lambda s: s + ".jpg"),
    keywords=_keyword_strategy,
    response_time_ms=st.floats(min_value=0.1, max_value=100_000.0, allow_nan=False, allow_infinity=False),
    error=st.none(),
)


# ---------------------------------------------------------------------------
# Property 9: Benchmark-CSV Round-Trip (Task 11.2)
# ---------------------------------------------------------------------------

class TestPropertyBenchmarkCsvRoundTrip:
    """Property 9: Benchmark-CSV Round-Trip

    Für alle Listen von BenchmarkErgebnis-Objekten: Schreiben als CSV und
    Einlesen ergibt äquivalente Liste.

    **Validates: Requirement 9.4**
    """

    @given(ergebnisse=st.lists(_benchmark_ergebnis_strategy, min_size=0, max_size=20))
    @settings(max_examples=100)
    def test_csv_round_trip(self, ergebnisse: list[BenchmarkErgebnis]):
        config = _make_config()
        runner = BenchmarkRunner(config)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as tmp:
            csv_path = tmp.name

        try:
            # Write (with prompt argument)
            runner._ergebnisse_als_csv_schreiben(ergebnisse, csv_path, "test prompt")

            # Read back, skipping comment lines and blank lines
            with open(csv_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()

            filtered_lines = [
                line for line in all_lines
                if not line.startswith("#") and line.strip() != ""
            ]

            reader = csv.DictReader(io.StringIO("".join(filtered_lines)))
            rows = list(reader)

            assert len(rows) == len(ergebnisse)

            # Rows are sorted by (image_name, model_name), so sort original too
            sortierte = sorted(
                ergebnisse, key=lambda e: (e.image_name, e.model_name)
            )

            for original, row in zip(sortierte, rows):
                assert row["model"] == original.model_name
                assert row["image"] == original.image_name

                # Keywords round-trip: semicolon-separated (alphabetically sorted in CSV)
                if original.keywords:
                    assert row["keywords"] == ";".join(sorted(original.keywords, key=str.casefold))
                else:
                    assert row["keywords"] == ""

                assert float(row["response_time_ms"]) == pytest.approx(
                    original.response_time_ms, rel=1e-6
                )
        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# Property 10: Benchmark verwendet einheitlichen Prompt (Task 11.3)
# ---------------------------------------------------------------------------

class TestPropertyBenchmarkEinheitlicherPrompt:
    """Property 10: Benchmark verwendet einheitlichen Prompt

    Für alle Modellnamen und Testbilder: BenchmarkRunner sendet denselben
    Prompt an alle Modelle. Mock-OllamaClient verwenden.

    **Validates: Requirement 9.3**
    """

    @given(
        model_names=st.lists(
            _safe_text, min_size=1, max_size=5, unique=True
        ),
        prompt=_safe_text.filter(lambda s: len(s) > 0),
    )
    @settings(max_examples=100)
    def test_einheitlicher_prompt(self, model_names: list[str], prompt: str):
        config = _make_config(
            benchmark_models=model_names,
            prompt_template=prompt,
        )
        runner = BenchmarkRunner(config)

        # Collect prompts that each OllamaClient was created with
        recorded_prompts: list[str] = []

        class MockOllamaClient:
            def __init__(self, endpoint, model_name, prompt_template, **kwargs):
                recorded_prompts.append(prompt_template)
                self.prompt_template = prompt_template

            def analyse_bild(self, image_path, standort_daten=None):
                return ["keyword1", "keyword2"]

        with tempfile.TemporaryDirectory() as img_dir, \
             tempfile.TemporaryDirectory() as csv_dir:
            csv_path = os.path.join(csv_dir, "benchmark.csv")
            _create_test_images(img_dir, ["test.jpg"])

            with patch(
                "photo_keywords.benchmark_runner.OllamaClient",
                MockOllamaClient,
            ):
                runner.benchmark_ausfuehren(img_dir, csv_path)

            # All recorded prompts must be the same configured prompt
            assert len(recorded_prompts) == len(model_names)
            for recorded in recorded_prompts:
                assert recorded == prompt


# ---------------------------------------------------------------------------
# Property 11: Benchmark-Zusammenfassung Konsistenz (Task 11.4)
# ---------------------------------------------------------------------------

# Strategy for ergebnisse with a known model set
_model_name_strategy = st.sampled_from(["moondream", "llava", "gemma3", "minicpm-v"])

_benchmark_ergebnis_with_optional_error = st.builds(
    BenchmarkErgebnis,
    model_name=_model_name_strategy,
    image_name=_safe_text.map(lambda s: s + ".jpg"),
    keywords=_keyword_strategy,
    response_time_ms=st.floats(
        min_value=0.1, max_value=100_000.0, allow_nan=False, allow_infinity=False
    ),
    error=st.one_of(st.none(), _safe_text),
)


class TestPropertyBenchmarkZusammenfassungKonsistenz:
    """Property 11: Benchmark-Zusammenfassung Konsistenz

    Für alle BenchmarkErgebnis-Listen:
    - bilder_verarbeitet + fehler = Gesamtanzahl pro Modell
    - durchschnitt_ms = arithmetisches Mittel der erfolgreichen Bilder
    - jedes Modell genau einmal in der Zusammenfassung

    **Validates: Requirement 9.8**
    """

    @given(
        ergebnisse=st.lists(
            _benchmark_ergebnis_with_optional_error, min_size=1, max_size=30
        )
    )
    @settings(max_examples=100)
    def test_zusammenfassung_konsistenz(
        self, ergebnisse: list[BenchmarkErgebnis]
    ):
        config = _make_config()
        runner = BenchmarkRunner(config)

        zusammenfassungen = runner._zusammenfassung_berechnen(ergebnisse)

        # Collect expected per-model data
        expected_models: dict[str, list[BenchmarkErgebnis]] = {}
        for e in ergebnisse:
            expected_models.setdefault(e.model_name, []).append(e)

        # Each model appears exactly once
        zf_models = [z.model_name for z in zusammenfassungen]
        assert len(zf_models) == len(set(zf_models))
        assert set(zf_models) == set(expected_models.keys())

        for z in zusammenfassungen:
            model_results = expected_models[z.model_name]
            erfolge = [r for r in model_results if r.error is None]
            fehler_count = len(model_results) - len(erfolge)

            # bilder_verarbeitet + fehler = total
            assert z.bilder_verarbeitet + z.fehler == len(model_results)
            assert z.bilder_verarbeitet == len(erfolge)
            assert z.fehler == fehler_count

            # durchschnitt_ms = arithmetic mean of successful results
            if erfolge:
                expected_avg = sum(r.response_time_ms for r in erfolge) / len(erfolge)
                assert z.durchschnitt_ms == pytest.approx(expected_avg, rel=1e-6)
            else:
                assert z.durchschnitt_ms == 0.0


# ---------------------------------------------------------------------------
# Property 3: Zeitgestempelter Dateiname
# Feature: benchmark-prompt-tracking, Property 3: Zeitgestempelter Dateiname
# ---------------------------------------------------------------------------

# Strategies for Property 3
_csv_basename_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="_-./",
    ),
    min_size=1,
    max_size=30,
).filter(lambda s: not s.endswith("/") and not s.endswith("."))

_zeitstempel_strategy = st.builds(
    lambda y, mo, d, h, mi, s: f"{y:04d}{mo:02d}{d:02d}_{h:02d}{mi:02d}{s:02d}",
    y=st.integers(min_value=2000, max_value=2099),
    mo=st.integers(min_value=1, max_value=12),
    d=st.integers(min_value=1, max_value=28),
    h=st.integers(min_value=0, max_value=23),
    mi=st.integers(min_value=0, max_value=59),
    s=st.integers(min_value=0, max_value=59),
)


class TestPropertyZeitgestempelterDateiname:
    """Property 3: Zeitgestempelter Dateiname

    Für alle CSV-Basispfade (mit .csv-Endung) und gültige Zeitstempel-Strings
    im Format YYYYMMDD_HHMMSS: Der erzeugte Dateiname entspricht dem Muster
    {basisname}_{YYYYMMDD_HHMMSS}.csv.

    Feature: benchmark-prompt-tracking, Property 3: Zeitgestempelter Dateiname

    **Validates: Requirements 2.1, 2.2**
    """

    @given(
        basename=_csv_basename_strategy,
        zeitstempel=_zeitstempel_strategy,
    )
    @settings(max_examples=100)
    def test_zeitgestempelter_pfad(self, basename: str, zeitstempel: str):
        base_path = basename + ".csv"
        config = _make_config()
        runner = BenchmarkRunner(config)

        result = runner._zeitgestempelter_pfad(base_path, zeitstempel)

        # 1. The result ends with .csv
        assert result.endswith(".csv")

        # 2. The result contains the timestamp before .csv
        basis_result, ext_result = os.path.splitext(result)
        assert ext_result == ".csv"
        assert basis_result.endswith(zeitstempel)

        # 3. The result starts with the original basename (without .csv)
        original_basis, _ = os.path.splitext(base_path)
        assert basis_result.startswith(original_basis)

        # 4. The full pattern is {basename}_{zeitstempel}.csv
        expected = f"{original_basis}_{zeitstempel}.csv"
        assert result == expected


# ---------------------------------------------------------------------------
# Property 1: Prompt-Kommentarzeile
# Feature: benchmark-prompt-tracking, Property 1: Prompt-Kommentarzeile
# ---------------------------------------------------------------------------


class TestPropertyPromptKommentarzeile:
    """Property 1: Prompt-Kommentarzeile

    Für alle Prompt-Strings (einschließlich solcher mit Zeilenumbrüchen):
    Die erste Zeile der CSV-Datei beginnt mit ``# prompt: ``, Zeilenumbrüche
    werden durch Leerzeichen ersetzt, und es gibt genau eine Kommentarzeile.

    Feature: benchmark-prompt-tracking, Property 1: Prompt-Kommentarzeile

    **Validates: Requirements 1.1, 1.2, 1.3**
    """

    @given(prompt=st.text(min_size=0, max_size=200))
    @settings(max_examples=100)
    def test_prompt_kommentarzeile(self, prompt: str):
        config = _make_config()
        runner = BenchmarkRunner(config)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as tmp:
            csv_path = tmp.name

        try:
            runner._ergebnisse_als_csv_schreiben([], csv_path, prompt)

            with open(csv_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # First line starts with '# prompt: '
            assert len(lines) >= 1
            first_line = lines[0]
            assert first_line.startswith("# prompt: ")

            # Extract prompt text (strip the prefix and trailing newline)
            prompt_text = first_line[len("# prompt: "):].rstrip("\n")

            # No newline or carriage return characters in the prompt text
            assert "\n" not in prompt_text
            assert "\r" not in prompt_text

            # Prompt text matches the original with newlines replaced by spaces
            expected_prompt = prompt.replace("\n", " ").replace("\r", " ")
            assert prompt_text == expected_prompt

            # Exactly one comment line (starting with '#')
            comment_lines = [l for l in lines if l.startswith("#")]
            assert len(comment_lines) == 1
        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# Property 2: CSV-Daten-Round-Trip mit Prompt-Kommentar
# Feature: benchmark-prompt-tracking, Property 2: CSV-Daten-Round-Trip mit Prompt-Kommentar
# ---------------------------------------------------------------------------


class TestPropertyCsvRoundTripMitPrompt:
    """Property 2: CSV-Daten-Round-Trip mit Prompt-Kommentar

    Für alle Listen von BenchmarkErgebnis-Objekten und alle Prompt-Strings:
    Schreiben als CSV und Einlesen (wobei Kommentarzeilen und Leerzeilen
    übersprungen werden) ergibt übereinstimmende Datenzeilen-Anzahl und
    Feldwerte.

    Feature: benchmark-prompt-tracking, Property 2: CSV-Daten-Round-Trip mit Prompt-Kommentar

    **Validates: Requirements 1.4, 3.4**
    """

    @given(
        ergebnisse=st.lists(_benchmark_ergebnis_strategy, min_size=0, max_size=20),
        prompt=st.text(min_size=0, max_size=100),
    )
    @settings(max_examples=100)
    def test_csv_round_trip_mit_prompt(
        self, ergebnisse: list[BenchmarkErgebnis], prompt: str
    ):
        config = _make_config()
        runner = BenchmarkRunner(config)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as tmp:
            csv_path = tmp.name

        try:
            # Write CSV with prompt comment
            runner._ergebnisse_als_csv_schreiben(ergebnisse, csv_path, prompt)

            # Read back, skipping comment lines and blank lines
            with open(csv_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()

            filtered_lines = [
                line for line in all_lines
                if not line.startswith("#") and line.strip() != ""
            ]

            # Parse filtered lines as CSV
            reader = csv.DictReader(io.StringIO("".join(filtered_lines)))
            rows = list(reader)

            # Number of data rows must equal number of ergebnisse
            assert len(rows) == len(ergebnisse)

            # Rows are sorted by (image_name, model_name), so sort original too
            sortierte = sorted(
                ergebnisse, key=lambda e: (e.image_name, e.model_name)
            )

            for original, row in zip(sortierte, rows):
                assert row["model"] == original.model_name
                assert row["image"] == original.image_name

                # Keywords: semicolon-separated (alphabetically sorted in CSV)
                if original.keywords:
                    assert row["keywords"] == ";".join(sorted(original.keywords, key=str.casefold))
                else:
                    assert row["keywords"] == ""

                assert float(row["response_time_ms"]) == pytest.approx(
                    original.response_time_ms, rel=1e-6
                )
        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# Property 4: Sortierung nach Bild und Modell
# Feature: benchmark-prompt-tracking, Property 4: Sortierung nach Bild und Modell
# ---------------------------------------------------------------------------


class TestPropertySortierungNachBildUndModell:
    """Property 4: Sortierung nach Bild und Modell

    Für alle nicht-leeren Listen von BenchmarkErgebnis-Objekten: Die Datenzeilen
    in der erzeugten CSV-Datei sind nach (image_name, model_name) aufsteigend
    sortiert.

    Feature: benchmark-prompt-tracking, Property 4: Sortierung nach Bild und Modell

    **Validates: Requirements 3.1, 3.2**
    """

    @given(
        ergebnisse=st.lists(_benchmark_ergebnis_strategy, min_size=1, max_size=20),
    )
    @settings(max_examples=100)
    def test_sortierung_nach_bild_und_modell(
        self, ergebnisse: list[BenchmarkErgebnis]
    ):
        config = _make_config()
        runner = BenchmarkRunner(config)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as tmp:
            csv_path = tmp.name

        try:
            runner._ergebnisse_als_csv_schreiben(ergebnisse, csv_path, "test prompt")

            # Read back, skipping comment lines and blank lines
            with open(csv_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()

            filtered_lines = [
                line for line in all_lines
                if not line.startswith("#") and line.strip() != ""
            ]

            reader = csv.DictReader(io.StringIO("".join(filtered_lines)))
            rows = list(reader)

            # Extract (image, model) tuples from data rows
            tuples = [(row["image"], row["model"]) for row in rows]

            # Assert tuples are in sorted ascending order
            assert tuples == sorted(tuples)
        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# Property 5: Leerzeilen zwischen Bildgruppen
# Feature: benchmark-prompt-tracking, Property 5: Leerzeilen zwischen Bildgruppen
# ---------------------------------------------------------------------------


class TestPropertyLeerzeileZwischenBildgruppen:
    """Property 5: Leerzeilen zwischen Bildgruppen

    Für alle Listen von BenchmarkErgebnis-Objekten mit mindestens zwei
    verschiedenen Bildnamen: In der erzeugten CSV-Datei steht genau eine
    Leerzeile zwischen jeder Bildgruppe, und innerhalb einer Bildgruppe
    kommen keine Leerzeilen vor.

    Feature: benchmark-prompt-tracking, Property 5: Leerzeilen zwischen Bildgruppen

    **Validates: Requirements 3.3**
    """

    @given(
        ergebnisse=st.lists(_benchmark_ergebnis_strategy, min_size=2, max_size=20),
    )
    @settings(max_examples=100)
    def test_leerzeile_zwischen_bildgruppen(
        self, ergebnisse: list[BenchmarkErgebnis]
    ):
        assume(len(set(e.image_name for e in ergebnisse)) >= 2)

        config = _make_config()
        runner = BenchmarkRunner(config)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as tmp:
            csv_path = tmp.name

        try:
            runner._ergebnisse_als_csv_schreiben(ergebnisse, csv_path, "test prompt")

            with open(csv_path, "r", encoding="utf-8") as f:
                raw_lines = f.readlines()

            # Skip the comment line (first line starting with '#')
            remaining = raw_lines
            assert len(remaining) >= 1 and remaining[0].startswith("#")
            remaining = remaining[1:]

            # Skip the header line (next non-blank line)
            assert len(remaining) >= 1 and remaining[0].strip() != ""
            remaining = remaining[1:]

            # Analyze data lines and blank lines
            # Collect (is_blank, image_name_or_none) for each line
            blank_line_count = 0
            prev_image = None
            for line in remaining:
                if line.strip() == "":
                    blank_line_count += 1
                    # Blank line must not appear within a group or at boundaries
                    # We check this by verifying the next data line has a different image
                    continue

                # Parse the CSV data line to get the image column
                reader = csv.reader(io.StringIO(line))
                row = next(reader)
                current_image = row[1]  # image column

                if prev_image is not None and current_image != prev_image:
                    # Group transition: there should have been exactly one blank line
                    # (we verify total count below)
                    pass
                prev_image = current_image

            # Count distinct images from the sorted output
            distinct_images = len(set(e.image_name for e in ergebnisse))

            # Total blank lines should equal (distinct_images - 1)
            assert blank_line_count == distinct_images - 1

            # Verify blank lines appear ONLY between groups, not within
            # Walk through remaining lines again with stricter checks
            prev_image = None
            expecting_blank_or_new_group = False
            for line in remaining:
                if line.strip() == "":
                    # A blank line: the previous line must have been a data line,
                    # and the next data line must have a different image
                    assert prev_image is not None, "Blank line before first data row"
                    expecting_blank_or_new_group = True
                    continue

                reader = csv.reader(io.StringIO(line))
                row = next(reader)
                current_image = row[1]

                if prev_image is not None and current_image == prev_image:
                    # Same group: there must not have been a blank line
                    assert not expecting_blank_or_new_group, (
                        "Blank line within same image group"
                    )

                if expecting_blank_or_new_group:
                    # After a blank line, the image must have changed
                    assert current_image != prev_image, (
                        "Blank line within same image group"
                    )
                    expecting_blank_or_new_group = False

                prev_image = current_image

            # No trailing blank line (expecting_blank_or_new_group should be False)
            assert not expecting_blank_or_new_group, "Trailing blank line after last group"

        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# Unit-Tests für BenchmarkRunner (Task 11.5)
# ---------------------------------------------------------------------------

class TestBenchmarkRunnerFehlendesVerzeichnis:
    """Test: BenchmarkError bei nicht existierendem Bildverzeichnis mit Pfad.

    Requirements: 9.5
    """

    def test_benchmark_error_bei_fehlendem_verzeichnis(self):
        config = _make_config()
        runner = BenchmarkRunner(config)

        missing_dir = "/nicht/existierendes/verzeichnis"
        with pytest.raises(BenchmarkError, match=missing_dir):
            runner._bilder_einlesen(missing_dir)

    def test_benchmark_error_bei_leerem_verzeichnis(self):
        config = _make_config()
        runner = BenchmarkRunner(config)

        with tempfile.TemporaryDirectory() as empty_dir:
            with pytest.raises(BenchmarkError, match=empty_dir.replace("\\", "\\\\")):
                runner._bilder_einlesen(empty_dir)


class TestBenchmarkRunnerFehlerEinzelnesModell:
    """Test: Fehler bei einzelnem Modell stoppt nicht den Benchmark.

    Requirements: 9.7
    """

    def test_fehler_bei_modell_stoppt_nicht_benchmark(self):
        config = _make_config(benchmark_models=["good_model", "bad_model"])
        runner = BenchmarkRunner(config)

        call_count = 0

        class MockClient:
            def __init__(self, endpoint, model_name, prompt_template, **kwargs):
                self.model_name = model_name

            def analyse_bild(self, image_path, standort_daten=None):
                nonlocal call_count
                call_count += 1
                if self.model_name == "bad_model":
                    raise RuntimeError("Modell nicht verfügbar")
                return ["keyword1"]

        with tempfile.TemporaryDirectory() as img_dir, \
             tempfile.TemporaryDirectory() as csv_dir:
            csv_path = os.path.join(csv_dir, "bench.csv")
            _create_test_images(img_dir, ["img1.jpg"])

            with patch(
                "photo_keywords.benchmark_runner.OllamaClient",
                MockClient,
            ):
                result = runner.benchmark_ausfuehren(img_dir, csv_path)

            # Both models were attempted
            assert call_count == 2

            # We should have summaries for both models
            assert len(result) == 2

            good = next(z for z in result if z.model_name == "good_model")
            bad = next(z for z in result if z.model_name == "bad_model")

            assert good.bilder_verarbeitet == 1
            assert good.fehler == 0
            assert bad.bilder_verarbeitet == 0
            assert bad.fehler == 1


class TestBenchmarkRunnerZusammenfassungAusgabe:
    """Test: Zusammenfassung auf Konsole mit Statistiken pro Modell.

    Requirements: 9.8, 2.4
    """

    def test_zusammenfassung_auf_konsole(self, capsys):
        config = _make_config(benchmark_models=["moondream", "llava:7b"])
        runner = BenchmarkRunner(config)

        class MockClient:
            def __init__(self, endpoint, model_name, prompt_template, **kwargs):
                self.model_name = model_name

            def analyse_bild(self, image_path, standort_daten=None):
                return ["keyword1", "keyword2"]

        with tempfile.TemporaryDirectory() as img_dir, \
             tempfile.TemporaryDirectory() as csv_dir:
            csv_path = os.path.join(csv_dir, "bench.csv")
            _create_test_images(img_dir, ["img1.jpg", "img2.jpg"])

            with patch(
                "photo_keywords.benchmark_runner.OllamaClient",
                MockClient,
            ):
                runner.benchmark_ausfuehren(img_dir, csv_path)

            captured = capsys.readouterr()
            assert "Benchmark-Zusammenfassung" in captured.out
            assert "moondream" in captured.out
            assert "llava:7b" in captured.out
            assert "Verarbeitet:" in captured.out
            assert "Durchschnitt:" in captured.out
            assert "Fehler:" in captured.out
            assert "Benchmark-Ergebnisse:" in captured.out


# ---------------------------------------------------------------------------
# Unit-Tests für erweiterten BenchmarkRunner mit Klassifikation (Task 7.6)
# ---------------------------------------------------------------------------


class TestBenchmarkErgebnisKlassifikationsfelder:
    """Test: BenchmarkErgebnis enthält foto_kategorie und prompt_typ.

    Requirements: 7.1
    """

    def test_benchmark_ergebnis_mit_klassifikation(self):
        """BenchmarkErgebnis with classification fields populated."""
        ergebnis = BenchmarkErgebnis(
            model_name="llava",
            image_name="sunset.jpg",
            keywords=["Sonnenuntergang", "Meer"],
            response_time_ms=3200.0,
            foto_kategorie="Landschaft",
            prompt_typ="Landschaft",
            klassifikations_zeit_ms=1850.0,
        )
        assert ergebnis.foto_kategorie == "Landschaft"
        assert ergebnis.prompt_typ == "Landschaft"
        assert ergebnis.klassifikations_zeit_ms == 1850.0

    def test_benchmark_ergebnis_ohne_klassifikation(self):
        """BenchmarkErgebnis without classification fields defaults to None."""
        ergebnis = BenchmarkErgebnis(
            model_name="llava",
            image_name="sunset.jpg",
            keywords=["Sonnenuntergang"],
            response_time_ms=3200.0,
        )
        assert ergebnis.foto_kategorie is None
        assert ergebnis.prompt_typ is None
        assert ergebnis.klassifikations_zeit_ms is None


class TestBenchmarkCsvKlassifikationsSpalten:
    """Test: CSV enthält erweiterte Spalten wenn Klassifikation vorhanden.

    Requirements: 7.2
    """

    def test_csv_mit_klassifikationsspalten(self):
        """CSV output includes classification columns when data is present."""
        config = _make_config()
        runner = BenchmarkRunner(config)

        ergebnisse = [
            BenchmarkErgebnis(
                model_name="llava",
                image_name="sunset.jpg",
                keywords=["Sonnenuntergang"],
                response_time_ms=3200.0,
                foto_kategorie="Landschaft",
                prompt_typ="Landschaft",
                klassifikations_zeit_ms=1850.0,
            ),
        ]

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

            assert len(rows) == 1
            assert "foto_kategorie" in rows[0]
            assert "prompt_typ" in rows[0]
            assert "klassifikations_zeit_ms" in rows[0]
            assert rows[0]["foto_kategorie"] == "Landschaft"
            assert rows[0]["prompt_typ"] == "Landschaft"
            assert float(rows[0]["klassifikations_zeit_ms"]) == pytest.approx(1850.0)
        finally:
            os.unlink(csv_path)

    def test_csv_ohne_klassifikationsspalten(self):
        """CSV output omits classification columns when no data is present."""
        config = _make_config()
        runner = BenchmarkRunner(config)

        ergebnisse = [
            BenchmarkErgebnis(
                model_name="llava",
                image_name="sunset.jpg",
                keywords=["Sonnenuntergang"],
                response_time_ms=3200.0,
            ),
        ]

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

            assert len(rows) == 1
            assert "foto_kategorie" not in rows[0]
            assert "prompt_typ" not in rows[0]
            assert "klassifikations_zeit_ms" not in rows[0]
        finally:
            os.unlink(csv_path)


class TestBenchmarkZusammenfassungKlassifikationszeit:
    """Test: Zusammenfassung enthält Klassifikationszeit.

    Requirements: 7.3
    """

    def test_zusammenfassung_mit_klassifikationszeit(self):
        """Summary includes average classification time when data is present."""
        config = _make_config()
        runner = BenchmarkRunner(config)

        ergebnisse = [
            BenchmarkErgebnis(
                model_name="llava",
                image_name="img1.jpg",
                keywords=["kw1"],
                response_time_ms=3000.0,
                klassifikations_zeit_ms=1000.0,
            ),
            BenchmarkErgebnis(
                model_name="llava",
                image_name="img2.jpg",
                keywords=["kw2"],
                response_time_ms=4000.0,
                klassifikations_zeit_ms=2000.0,
            ),
        ]

        zusammenfassungen = runner._zusammenfassung_berechnen(ergebnisse)
        assert len(zusammenfassungen) == 1
        z = zusammenfassungen[0]
        assert z.durchschnitt_klassifikations_ms is not None
        assert z.durchschnitt_klassifikations_ms == pytest.approx(1500.0)

    def test_zusammenfassung_ohne_klassifikationszeit(self):
        """Summary has None classification time when no data is present."""
        config = _make_config()
        runner = BenchmarkRunner(config)

        ergebnisse = [
            BenchmarkErgebnis(
                model_name="llava",
                image_name="img1.jpg",
                keywords=["kw1"],
                response_time_ms=3000.0,
            ),
        ]

        zusammenfassungen = runner._zusammenfassung_berechnen(ergebnisse)
        assert len(zusammenfassungen) == 1
        assert zusammenfassungen[0].durchschnitt_klassifikations_ms is None

    def test_zusammenfassung_ausgabe_mit_klassifikationszeit(self, capsys):
        """Console output includes classification time when present."""
        config = _make_config()
        runner = BenchmarkRunner(config)

        zusammenfassungen = [
            BenchmarkZusammenfassung(
                model_name="llava",
                bilder_verarbeitet=2,
                durchschnitt_ms=3500.0,
                fehler=0,
                durchschnitt_klassifikations_ms=1500.0,
            ),
        ]

        runner._zusammenfassung_ausgeben(zusammenfassungen)
        captured = capsys.readouterr()
        assert "Klassifikation: 1500.0 ms" in captured.out

    def test_zusammenfassung_ausgabe_ohne_klassifikationszeit(self, capsys):
        """Console output omits classification time when not present."""
        config = _make_config()
        runner = BenchmarkRunner(config)

        zusammenfassungen = [
            BenchmarkZusammenfassung(
                model_name="llava",
                bilder_verarbeitet=2,
                durchschnitt_ms=3500.0,
                fehler=0,
            ),
        ]

        runner._zusammenfassung_ausgeben(zusammenfassungen)
        captured = capsys.readouterr()
        assert "Klassifikation" not in captured.out
