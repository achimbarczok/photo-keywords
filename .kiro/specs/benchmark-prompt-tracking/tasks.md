# Implementation Plan: Benchmark Prompt Tracking

## Overview

Drei gezielte Erweiterungen der bestehenden `BenchmarkRunner`-Klasse: Prompt-Kommentarzeile in CSV, zeitgestempelte Dateinamen und sortierte/gruppierte CSV-Ausgabe. Alle Änderungen betreffen `lightroom_ollama_keywords/benchmark_runner.py` und die zugehörigen Tests.

## Tasks

- [x] 1. Add `_zeitgestempelter_pfad` helper and update `benchmark_ausfuehren`
  - [x] 1.1 Add `datetime` import and implement `_zeitgestempelter_pfad` method in `benchmark_runner.py`
    - Add `from datetime import datetime` import
    - Implement `_zeitgestempelter_pfad(self, output_csv: str, zeitstempel: str) -> str` using `os.path.splitext`
    - _Requirements: 2.1, 2.2_
  - [x] 1.2 Update `benchmark_ausfuehren` to use timestamped filenames and print output path
    - Capture timestamp at start: `datetime.now().strftime("%Y%m%d_%H%M%S")`
    - Replace `output_csv` with timestamped path via `_zeitgestempelter_pfad`
    - Add `print(f"Benchmark-Ergebnisse: {output_csv}")` after CSV write
    - _Requirements: 2.3, 2.4, 2.5_
  - [x] 1.3 Write property test for timestamped filename (Property 3)
    - **Property 3: Zeitgestempelter Dateiname**
    - For all CSV base paths and valid timestamp strings: the generated filename matches `{basename}_{YYYYMMDD_HHMMSS}.csv`
    - **Validates: Requirements 2.1, 2.2**

- [x] 2. Extend `_ergebnisse_als_csv_schreiben` with prompt comment, sorting, and grouping
  - [x] 2.1 Add `prompt` parameter and write prompt comment line
    - Add `prompt: str` parameter to method signature
    - Write `# prompt: {prompt_einzeilig}\n` as first line, replacing `\n` and `\r` with spaces
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 2.2 Implement sorting by `(image_name, model_name)` and blank-line grouping
    - Sort results with `sorted(ergebnisse, key=lambda e: (e.image_name, e.model_name))`
    - Insert blank line (`f.write("\n")`) between image groups
    - Keep CSV header and data rows intact after comment line
    - _Requirements: 1.4, 3.1, 3.2, 3.3, 3.4_
  - [x] 2.3 Update the call site in `benchmark_ausfuehren` to pass `self.config.prompt_template`
    - Change `self._ergebnisse_als_csv_schreiben(ergebnisse, output_csv)` to `self._ergebnisse_als_csv_schreiben(ergebnisse, output_csv, self.config.prompt_template)`
    - _Requirements: 1.1_
  - [x] 2.4 Write property test for prompt comment line (Property 1)
    - **Property 1: Prompt-Kommentarzeile**
    - For all prompt strings (including those with `\n`, `\r`): first line starts with `# prompt: `, newlines replaced by spaces, exactly one line
    - **Validates: Requirements 1.1, 1.2, 1.3**
  - [x] 2.5 Write property test for CSV round-trip with prompt comment (Property 2)
    - **Property 2: CSV-Daten-Round-Trip mit Prompt-Kommentar**
    - For all result lists and prompt strings: writing and reading back (skipping comment and blank lines) yields matching data row count and field values
    - **Validates: Requirements 1.4, 3.4**
  - [x] 2.6 Write property test for sorting (Property 4)
    - **Property 4: Sortierung nach Bild und Modell**
    - For all non-empty result lists: data rows in CSV are sorted ascending by `(image_name, model_name)`
    - **Validates: Requirements 3.1, 3.2**
  - [x] 2.7 Write property test for blank lines between image groups (Property 5)
    - **Property 5: Leerzeilen zwischen Bildgruppen**
    - For all result lists with at least two distinct image names: exactly one blank line between each image group, none within a group
    - **Validates: Requirements 3.3**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Update existing tests for new method signatures
  - [x] 4.1 Update Property 9 (CSV Round-Trip) in `tests/test_benchmark_runner.py`
    - Adapt `_ergebnisse_als_csv_schreiben` call to include `prompt` parameter
    - Update CSV reading to skip comment line and blank lines
    - This property is superseded by Property 2 but the existing test class should still work with the new signature
    - _Requirements: 1.4, 3.4_
  - [x] 4.2 Update Property 10 and 11 tests for changed `benchmark_ausfuehren` behavior
    - Property 10 (einheitlicher Prompt): account for timestamped output filename — use `tmp_path` glob or adjust assertions
    - Property 11 (Zusammenfassung Konsistenz): no signature change needed, only calls `_zusammenfassung_berechnen`
    - _Requirements: 2.1_
  - [x] 4.3 Update unit tests in `tests/test_benchmark_runner.py`
    - Update `TestBenchmarkRunnerFehlerEinzelnesModell` and `TestBenchmarkRunnerZusammenfassungAusgabe` for timestamped filenames
    - Add assertion for console output of CSV path
    - _Requirements: 2.4_
  - [x] 4.4 Update integration tests in `tests/test_integration.py`
    - Update `TestBenchmarkEndToEnd.test_benchmark_full_run` to find timestamped CSV file instead of exact path
    - Update CSV reading to skip comment line and blank lines
    - Update `test_benchmark_requests_use_correct_models` similarly
    - _Requirements: 1.1, 2.1, 3.1_

- [x] 5. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All code is Python, using pytest + Hypothesis for property-based tests
- The design has 5 correctness properties, each mapped to a separate optional sub-task
- Existing Property 9 is superseded by Property 2 but should be updated for compatibility
- No new files or dependencies are introduced — only modifications to existing modules
