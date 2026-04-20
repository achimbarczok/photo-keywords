# Implementation Plan: Location-Based Keywords

## Overview

Erweitert den Lightroom Ollama Keyword Generator um standortbasierte Stichwörter. GPS-Koordinaten werden aus EXIF-Metadaten und Lightroom-Katalog gelesen, per Offline-Reverse-Geocoding in Ortsnamen aufgelöst und als Stichwörter + Prompt-Kontext verwendet. Die Implementierung erfolgt bottom-up: Datenmodelle → neue Module → Erweiterung bestehender Komponenten → Wiring → Benchmark.

## Tasks

- [x] 1. Datenmodelle und Fehlerklasse anlegen
  - [x] 1.1 `StandortDaten` frozen dataclass in `models.py` hinzufügen
    - Felder: `stadt` (str), `region` (str), `land` (str), `breitengrad` (float), `laengengrad` (float)
    - `__post_init__` Validierung: breitengrad ∈ [-90, 90], laengengrad ∈ [-180, 180], sonst `ValueError`
    - Methode `als_stichwort_liste() -> list[str]`: nicht-leere Felder (stadt, region, land) als Liste
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 1.2 `StandortConfig` dataclass in `models.py` hinzufügen
    - Feld: `enabled: bool = False`
    - `Config` um Feld `standort: StandortConfig = field(default_factory=StandortConfig)` erweitern
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 1.3 `BenchmarkErgebnis` um optionales Feld `standort: str | None = None` erweitern
    - _Requirements: 6.5_

  - [x] 1.4 `GpsLeseError` in `errors.py` hinzufügen
    - Erbt von `KeywordGeneratorError`
    - _Requirements: 1.3_

  - [x] 1.5 Property-Tests für StandortDaten schreiben
    - **Property 7: StandortDaten-Koordinatenvalidierung**
    - **Property 8: als_stichwort_liste gibt nur nicht-leere Felder zurück**
    - **Validates: Requirements 8.3, 8.4, 8.5**

  - [x] 1.6 Unit-Tests für StandortDaten schreiben
    - Test: frozen dataclass → `FrozenInstanceError` bei Mutation
    - Test: `als_stichwort_liste` mit leeren Feldern
    - Test: `ValueError` bei ungültigen Koordinaten
    - _Requirements: 8.2, 8.3, 8.4_

- [x] 2. Checkpoint — Datenmodelle validieren
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Neues Modul `gps_leser.py` implementieren
  - [x] 3.1 `GpsLeser`-Klasse mit `gps_aus_exif()` implementieren
    - EXIF-Tags `GPS GPSLatitude`, `GPS GPSLatitudeRef`, `GPS GPSLongitude`, `GPS GPSLongitudeRef` via `exifread` lesen
    - DMS-zu-Dezimalgrad-Konvertierung (`_dms_zu_dezimal` static method)
    - None zurückgeben bei fehlenden/ungültigen GPS-Tags, Fehler protokollieren
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 3.2 `GpsLeser.gps_aus_katalog()` implementieren
    - SQL-Query auf `AgHarvestedExifMetadata` (SELECT gpsLatitude, gpsLongitude WHERE image = :image_id AND hasGps = 1.0)
    - None zurückgeben bei fehlendem Katalog-GPS
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 `GpsLeser.gps_ermitteln()` implementieren
    - Prioritätslogik: Katalog-GPS > EXIF-GPS > None
    - Optionale Parameter `katalog_conn` und `image_id`
    - _Requirements: 2.3_

  - [x] 3.4 Property-Tests für GpsLeser schreiben
    - **Property 1: DMS-zu-Dezimalgrad-Konvertierung**
    - **Validates: Requirements 1.1**
    - **Property 2: Katalog-GPS Round-Trip**
    - **Validates: Requirements 2.1**
    - **Property 3: Katalog-GPS hat Vorrang vor EXIF-GPS**
    - **Validates: Requirements 2.3**

  - [x] 3.5 Unit-Tests für GpsLeser schreiben
    - Test: EXIF ohne GPS-Tags → None
    - Test: EXIF mit ungültigem Format → None + Logging
    - Test: Katalog ohne GPS → None
    - _Requirements: 1.2, 1.3, 2.2_

- [x] 4. Neues Modul `standort_resolver.py` implementieren
  - [x] 4.1 `StandortResolver`-Klasse mit `standort_aufloesen()` implementieren
    - Koordinaten validieren: breitengrad ∈ [-90, 90], laengengrad ∈ [-180, 180], nicht (0.0, 0.0)
    - `reverse_geocoder.search()` aufrufen
    - Ergebnis in `StandortDaten` umwandeln (stadt=name, region=admin1, land=cc)
    - `ImportError` mit beschreibender Meldung wenn `reverse_geocoder` nicht installiert
    - None bei ungültigen Koordinaten oder internem Fehler
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 4.2 Property-Test für StandortResolver schreiben
    - **Property 4: Gültige Koordinaten erzeugen gültige StandortDaten**
    - **Validates: Requirements 3.1, 3.5**

  - [x] 4.3 Unit-Tests für StandortResolver schreiben
    - Test: (0.0, 0.0) → None
    - Test: `reverse_geocoder` nicht installiert → ImportError
    - _Requirements: 3.3, 3.4_

- [x] 5. Checkpoint — Neue Module validieren
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Bestehende Komponenten erweitern
  - [x] 6.1 `ConfigLoader._parse_standort()` implementieren
    - Neuen optionalen `location`-Abschnitt aus YAML parsen
    - Fehlender Abschnitt → `StandortConfig(enabled=False)`
    - `location.enabled` Boolean auswerten
    - `Config`-Konstruktor um `standort=self._parse_standort(data.get("location"))` erweitern
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 6.2 Property-Test für Config-Location-Parsing schreiben
    - **Property 10: Config-Location-Parsing**
    - **Validates: Requirements 7.1, 7.2, 7.3**

  - [x] 6.3 `OllamaClient.analyse_bild()` um optionalen `standort_daten`-Parameter erweitern
    - Neuer Parameter: `standort_daten: StandortDaten | None = None`
    - Statische Methode `_standort_prompt_prefix()` implementieren
    - Wenn standort_daten vorhanden: Prefix + "\n" + original prompt
    - Wenn None: prompt unverändert
    - Format: "Dieses Foto wurde in {stadt}, {land} aufgenommen." (bzw. mit region wenn region ≠ stadt)
    - _Requirements: 5.1, 5.2, 5.4_

  - [x] 6.4 Property-Test für Standort-Prompt-Konstruktion schreiben
    - **Property 6: Standort-Prompt-Konstruktion bewahrt Original-Prompt**
    - **Validates: Requirements 5.1, 5.4**

  - [x] 6.5 `KlassifikationsRouter.bild_analysieren()` um `standort_daten`-Parameter erweitern
    - Neuer Parameter: `standort_daten: StandortDaten | None = None`
    - `standort_daten` an interne `OllamaClient.analyse_bild()`-Aufrufe weiterreichen
    - _Requirements: 5.3_

  - [x] 6.6 `BatchProcessor` um Standort-Verarbeitung erweitern
    - Neue Konstruktor-Parameter: `gps_leser`, `standort_resolver`, `katalog_conn`
    - In `batch_verarbeiten()`: GPS ermitteln → Standort auflösen → an Analyse übergeben
    - Statische Methode `_keywords_zusammenfuehren()`: Standort-Stichwörter + KI-Keywords zusammenführen (duplikatfrei, keine leeren Strings, Standort zuerst)
    - Zusammengeführte Keywords an StichwortSchreiber übergeben
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 7.4, 7.5_

  - [x] 6.7 Property-Test für Keyword-Zusammenführung schreiben
    - **Property 5: Keyword-Zusammenführung ist vollständig, duplikatfrei und ohne leere Strings**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

- [x] 7. Checkpoint — Erweiterte Komponenten validieren
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. BenchmarkRunner erweitern und Wiring in main.py
  - [x] 8.1 `BenchmarkRunner` um Standort-Verarbeitung erweitern
    - `GpsLeser` und `StandortResolver` instanziieren
    - GPS nur aus EXIF lesen (kein Katalog)
    - Standort-Kontext in Prompt injizieren via `analyse_bild(image_path, standort_daten)`
    - Aufgelösten Standort in `BenchmarkErgebnis.standort` speichern
    - CSV-Ausgabe um Spalte `standort` erweitern
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 8.2 Property-Test für Benchmark-CSV Standort Round-Trip schreiben
    - **Property 9: Benchmark-CSV Standort Round-Trip**
    - **Validates: Requirements 6.5**

  - [x] 8.3 `main.py` Wiring anpassen
    - In `_run_normal()`: `GpsLeser` und `StandortResolver` instanziieren wenn `config.standort.enabled`
    - Katalog-Connection an `BatchProcessor` übergeben
    - `GpsLeser` und `StandortResolver` an `BatchProcessor` übergeben
    - _Requirements: 7.4, 7.5_

- [x] 9. Integrationstests schreiben
  - [x] 9.1 Integrationstest: GPS → Standort → Keywords
    - Vollständiger Pfad: EXIF-GPS lesen → Reverse-Geocoding → Standort-Stichwörter in Keyword-Liste
    - _Requirements: 1.1, 3.1, 4.1_

  - [x] 9.2 Integrationstest: Batch mit Standort
    - BatchProcessor mit aktivierter Standort-Funktion, Mock-Ollama
    - _Requirements: 4.1, 4.2, 5.1, 7.5_

  - [x] 9.3 Integrationstest: Benchmark mit Standort-CSV
    - BenchmarkRunner erzeugt CSV mit Standort-Spalte
    - _Requirements: 6.1, 6.3, 6.5_

- [x] 10. Final Checkpoint — Alle Tests bestehen
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks mit `*` sind optional und können für ein schnelleres MVP übersprungen werden
- Jeder Task referenziert spezifische Requirements für Nachverfolgbarkeit
- Checkpoints stellen inkrementelle Validierung sicher
- Property-Tests validieren universelle Korrektheitseigenschaften aus dem Design
- Unit-Tests validieren spezifische Beispiele und Fehlerfälle
- Abhängigkeiten: `exifread` (EXIF-GPS), `reverse_geocoder` (Offline-Geocoding) müssen installiert sein
