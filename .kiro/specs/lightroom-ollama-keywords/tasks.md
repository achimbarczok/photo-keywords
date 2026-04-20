# Implementierungsplan: Lightroom Ollama Keywords

## Übersicht

Schrittweise Implementierung der Python-CLI-Anwendung zur automatischen Stichwort-Vergabe für Lightroom-Fotos über Ollama. Die Implementierung folgt der Pipeline-Architektur aus dem Design: Zuerst Projektstruktur und Fehlerklassen, dann die einzelnen Komponenten von innen nach außen (Datenmodelle → Kernlogik → Orchestrierung → CLI), jeweils mit Tests.

## Tasks

- [x] 1. Projektstruktur und Fehlerklassen anlegen
  - [x] 1.1 Projektverzeichnis und Paketstruktur erstellen
    - Verzeichnis `lightroom_ollama_keywords/` mit `__init__.py` anlegen
    - Verzeichnis `tests/` mit `__init__.py` anlegen
    - `requirements.txt` erstellen mit: `pyyaml`, `requests`, `pyexiftool`, `pytest`, `hypothesis`
    - _Anforderungen: 6.1_
  - [x] 1.2 Fehlerklassen-Hierarchie implementieren
    - Datei `lightroom_ollama_keywords/errors.py` erstellen
    - Alle Fehlerklassen gemäß Design implementieren: `KeywordGeneratorError`, `ConfigError`, `KatalogError`, `TrackerError`, `OllamaConnectionError`, `OllamaApiError`, `ImageReadError`, `MetadataWriteError`, `BenchmarkError`
    - _Anforderungen: 1.4, 2.4, 2.5, 2.6, 3.4, 4.5, 6.2, 9.5_
  - [x] 1.3 Datenklassen (Dataclasses) erstellen
    - Datei `lightroom_ollama_keywords/models.py` erstellen
    - `Config`, `FotoEintrag`, `VerarbeitungsEintrag`, `BatchErgebnis`, `BenchmarkErgebnis`, `BenchmarkZusammenfassung` als `@dataclass` implementieren
    - _Anforderungen: 1.1, 4.1, 5.3, 9.2, 9.4, 9.8_

- [x] 2. ConfigLoader implementieren
  - [x] 2.1 ConfigLoader-Klasse implementieren
    - Datei `lightroom_ollama_keywords/config_loader.py` erstellen
    - `load(config_path: str) -> Config` Methode: YAML laden, Pflichtparameter prüfen (`catalog_path`, `model_name`), Standardwerte für optionale Parameter setzen
    - `ConfigError` bei fehlenden Pflichtparametern mit Parametername in Fehlermeldung
    - _Anforderungen: 6.1, 6.2, 6.3_
  - [x] 2.2 Property-Test: Konfigurations-Round-Trip
    - **Property 7: Konfigurations-Round-Trip**
    - Für alle gültigen Config-Objekte: Serialisieren als YAML und Deserialisieren ergibt äquivalentes Objekt
    - **Validiert: Anforderung 6.1**
  - [x] 2.3 Property-Test: Validierung fehlender Pflichtparameter
    - **Property 8: Validierung fehlender Pflichtparameter**
    - Für alle Konfigurationen mit genau einem fehlenden Pflichtparameter: ConfigError mit Parametername
    - **Validiert: Anforderung 6.2**
  - [x] 2.4 Unit-Tests für ConfigLoader
    - Test: Korrekte Standardwerte bei fehlenden optionalen Parametern
    - Test: ConfigError bei fehlender YAML-Datei
    - _Anforderungen: 6.2, 6.3_

- [x] 3. Checkpoint – Konfiguration validieren
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer fragen.

- [x] 4. KatalogLeser implementieren
  - [x] 4.1 KatalogLeser-Klasse implementieren
    - Datei `lightroom_ollama_keywords/katalog_leser.py` erstellen
    - `__init__(catalog_path: str)`: SQLite-Verbindung im Read-Only-Modus öffnen (`file:{path}?mode=ro`)
    - `alle_fotos_lesen() -> list[FotoEintrag]`: SQL-Query gemäß Design (JOIN über Adobe_images, AgLibraryFile, AgLibraryFolder, AgLibraryRootFolder)
    - `close()`: Datenbankverbindung schließen
    - `KatalogError` bei nicht gefundenem/unlesbarem Katalog mit Pfad in Fehlermeldung
    - _Anforderungen: 1.1, 1.4_
  - [x] 4.2 Property-Test: Katalog-Pfad-Zusammensetzung
    - **Property 1: Katalog-Pfad-Zusammensetzung**
    - Für alle gültigen Katalog-Einträge: Dateipfad = absolutePath + pathFromRoot + baseName + '.' + extension, Anzahl Ergebnisse = Anzahl Adobe_images-Einträge
    - In-Memory-SQLite mit Lightroom-Schema und generierten Testdaten (Hypothesis)
    - **Validiert: Anforderung 1.1**
  - [x] 4.3 Unit-Tests für KatalogLeser
    - Test: KatalogError bei nicht existierender Katalogdatei mit Pfad in Fehlermeldung
    - _Anforderungen: 1.4_

- [x] 5. VerarbeitungsTracker implementieren
  - [x] 5.1 VerarbeitungsTracker-Klasse implementieren
    - Datei `lightroom_ollama_keywords/verarbeitungs_tracker.py` erstellen
    - `__init__(db_path: str)`: SQLite-DB öffnen/erstellen, Schema anlegen (CREATE TABLE IF NOT EXISTS mit UNIQUE-Constraint)
    - `ist_verarbeitet(file_path, model_name) -> bool`: Prüfung per SELECT
    - `unverarbeitete_filtern(fotos, model_name) -> list[FotoEintrag]`: Filterung
    - `verarbeitung_speichern(file_path, model_name, model_version)`: INSERT OR REPLACE mit ISO-8601-Zeitstempel
    - `close()`: Datenbankverbindung schließen
    - `TrackerError` bei Dateizugriffsproblemen mit Pfad in Fehlermeldung
    - _Anforderungen: 1.2, 1.3, 4.1, 4.2, 4.3, 4.4, 4.5_
  - [x] 5.2 Property-Test: Unverarbeitete-Fotos-Filterung
    - **Property 2: Unverarbeitete-Fotos-Filterung**
    - Für alle Foto-Listen und Tracking-Einträge: Filterung gibt genau die Fotos ohne passenden Tracking-Eintrag zurück
    - **Validiert: Anforderungen 1.2, 1.3**
  - [x] 5.3 Property-Test: Tracking Round-Trip mit Modellspezifität
    - **Property 5: Tracking Round-Trip mit Modellspezifität**
    - Für alle Dateipfade und unterschiedliche Modellnamen: ist_verarbeitet korrekt nach Speichern, Modellspezifität gewährleistet
    - **Validiert: Anforderungen 4.1, 4.3, 4.4**
  - [x] 5.4 Unit-Tests für VerarbeitungsTracker
    - Test: TrackerError bei nicht zugreifbarer Tracking-DB mit Pfad in Fehlermeldung
    - _Anforderungen: 4.5_

- [x] 6. Checkpoint – Datenbank-Komponenten validieren
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer fragen.

- [x] 7. OllamaClient implementieren
  - [x] 7.1 OllamaClient-Klasse implementieren
    - Datei `lightroom_ollama_keywords/ollama_client.py` erstellen
    - `__init__(endpoint, model_name, prompt_template)`: Konfiguration speichern
    - `analyse_bild(image_path) -> list[str]`: Bild als base64 kodieren, POST /api/generate mit `stream: false`, Antwort parsen
    - `_bild_zu_base64(image_path) -> str`: Bilddatei lesen und base64-kodieren
    - `_antwort_parsen(response_text) -> list[str]`: Komma-getrennte Antwort in bereinigte Stichwort-Liste umwandeln (Whitespace trimmen, leere Einträge und Duplikate entfernen)
    - `modell_version_abfragen() -> str`: GET /api/show
    - Fehlerbehandlung: `OllamaConnectionError`, `OllamaApiError`, `ImageReadError`
    - _Anforderungen: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
  - [x] 7.2 Property-Test: Antwort-Parsing
    - **Property 3: Antwort-Parsing**
    - Für alle Komma-getrennten Strings: Parsing ergibt Liste ohne führende/nachfolgende Whitespace und ohne leere Strings
    - **Validiert: Anforderung 2.3**
  - [x] 7.3 Unit-Tests für OllamaClient
    - Test: OllamaConnectionError bei nicht erreichbarer API mit Endpunkt in Fehlermeldung
    - Test: OllamaApiError bei API-Fehler, Fehler protokolliert
    - Test: ImageReadError bei nicht lesbarer Bilddatei mit Dateipfad
    - _Anforderungen: 2.4, 2.5, 2.6_

- [x] 8. StichwortSchreiber implementieren
  - [x] 8.1 StichwortSchreiber-Klasse implementieren
    - Datei `lightroom_ollama_keywords/stichwort_schreiber.py` erstellen
    - `__init__(exiftool_path=None)`: ExifTool im Batch-Modus initialisieren (pyexiftool)
    - `stichwörter_schreiben(file_path, keywords)`: Vorhandene Keywords lesen, mit neuen zusammenführen (ohne Duplikate), IPTC:Keywords und XMP:Subject schreiben
    - `_vorhandene_keywords_lesen(file_path) -> set[str]`: Bestehende IPTC-Keywords auslesen
    - `close()`: ExifTool-Prozess beenden
    - `MetadataWriteError` bei Schreibfehlern
    - _Anforderungen: 3.1, 3.2, 3.3, 3.4, 7.2_
  - [x] 8.2 Property-Test: Keyword-Zusammenführung ohne Datenverlust
    - **Property 4: Keyword-Zusammenführung ohne Datenverlust**
    - Für alle Mengen vorhandener und neuer Keywords: Ergebnis = Vereinigung, keine Duplikate, alle vorhandenen und neuen enthalten
    - **Validiert: Anforderungen 3.2, 3.3**
  - [x] 8.3 Unit-Tests für StichwortSchreiber
    - Test: MetadataWriteError bei Schreibfehler mit Dateipfad
    - _Anforderungen: 3.4_

- [x] 9. Checkpoint – Kernkomponenten validieren
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer fragen.

- [x] 10. BatchProcessor implementieren
  - [x] 10.1 BatchProcessor-Klasse implementieren
    - Datei `lightroom_ollama_keywords/batch_processor.py` erstellen
    - `__init__(ollama, schreiber, tracker, model_name, model_version)`: Abhängigkeiten injizieren
    - `batch_verarbeiten(fotos: list[FotoEintrag]) -> BatchErgebnis`: Für jedes Foto: Fortschritt ausgeben, Bild analysieren, Stichwörter schreiben, Tracking speichern; bei Fehler: protokollieren und fortfahren; am Ende: Zusammenfassung ausgeben
    - Fortschrittsanzeige: aktuelles Foto, Gesamtanzahl, verbleibende Fotos
    - Zusammenfassung: Anzahl verarbeitet, Fehler, Dauer
    - Hinweis am Ende: "Bitte in Lightroom 'Metadaten aus Datei lesen' ausführen"
    - _Anforderungen: 5.1, 5.2, 5.3, 5.4, 7.1_
  - [x] 10.2 Property-Test: Batch-Größen-Begrenzung
    - **Property 6: Batch-Größen-Begrenzung**
    - Für alle Foto-Listen und positive Batch-Größen: Anzahl verarbeiteter Fotos ≤ Batch-Größe
    - Mock-OllamaClient und Mock-StichwortSchreiber verwenden
    - **Validiert: Anforderung 5.1**
  - [x] 10.3 Unit-Tests für BatchProcessor
    - Test: Hinweis "Metadaten aus Datei lesen" wird ausgegeben
    - Test: Fehler bei einzelnem Foto stoppt nicht die Batch-Verarbeitung
    - _Anforderungen: 5.2, 5.3, 7.1_

- [x] 11. BenchmarkRunner implementieren
  - [x] 11.1 BenchmarkRunner-Klasse implementieren
    - Datei `lightroom_ollama_keywords/benchmark_runner.py` erstellen
    - `__init__(config: Config)`: Konfiguration speichern
    - `benchmark_ausfuehren(image_dir, output_csv) -> list[BenchmarkZusammenfassung]`: Bilder einlesen, pro Modell OllamaClient erstellen (mit demselben Prompt), pro Bild Antwortzeit messen, Ergebnisse als CSV schreiben, Zusammenfassung berechnen und ausgeben
    - `_bilder_einlesen(image_dir) -> list[str]`: Bilddateien (jpg, jpeg, png, tiff, raw) einlesen, BenchmarkError bei fehlendem/leerem Verzeichnis
    - `_ergebnisse_als_csv_schreiben(ergebnisse, output_path)`: CSV mit Spalten model, image, keywords, response_time_ms
    - `_zusammenfassung_berechnen(ergebnisse) -> list[BenchmarkZusammenfassung]`: Pro Modell: Anzahl, Durchschnitt, Fehler
    - `_zusammenfassung_ausgeben(zusammenfassungen)`: Formatierte Konsolenausgabe
    - Fehlerbehandlung: BenchmarkError bei fehlendem Verzeichnis, Fehler bei einzelnem Modell protokollieren und fortfahren
    - _Anforderungen: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_
  - [x] 11.2 Property-Test: Benchmark-CSV Round-Trip
    - **Property 9: Benchmark-CSV Round-Trip**
    - Für alle Listen von BenchmarkErgebnis-Objekten: Schreiben als CSV und Einlesen ergibt äquivalente Liste
    - **Validiert: Anforderung 9.4**
  - [x] 11.3 Property-Test: Benchmark verwendet einheitlichen Prompt
    - **Property 10: Benchmark verwendet einheitlichen Prompt**
    - Für alle Modellnamen und Testbilder: BenchmarkRunner sendet denselben Prompt an alle Modelle
    - Mock-OllamaClient verwenden, der den empfangenen Prompt aufzeichnet
    - **Validiert: Anforderung 9.3**
  - [x] 11.4 Property-Test: Benchmark-Zusammenfassung Konsistenz
    - **Property 11: Benchmark-Zusammenfassung Konsistenz**
    - Für alle BenchmarkErgebnis-Listen: bilder_verarbeitet + fehler = Gesamtanzahl, durchschnitt_ms = arithmetisches Mittel, jedes Modell genau einmal
    - **Validiert: Anforderung 9.8**
  - [x] 11.5 Unit-Tests für BenchmarkRunner
    - Test: BenchmarkError bei nicht existierendem Bildverzeichnis mit Pfad in Fehlermeldung
    - Test: Fehler bei einzelnem Modell stoppt nicht den Benchmark
    - Test: Zusammenfassung auf Konsole mit Statistiken pro Modell
    - _Anforderungen: 9.5, 9.7, 9.8_

- [x] 12. Checkpoint – Alle Komponenten validieren
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer fragen.

- [x] 13. CLI-Einstiegspunkt und Logging implementieren
  - [x] 13.1 main.py implementieren
    - Datei `lightroom_ollama_keywords/main.py` erstellen
    - CLI-Argumente: `--config` (Pfad zur YAML-Datei), `--benchmark` (Verzeichnis mit Testbildern)
    - Normaler Modus: Config laden → Logging einrichten → Logdatei-Pfad auf Konsole ausgeben → KatalogLeser → alle Fotos lesen → VerarbeitungsTracker → unverarbeitete filtern → Batch erstellen (max batch_size) → BatchProcessor → Zusammenfassung → Hinweis "Metadaten aus Datei lesen"
    - Benchmark-Modus: Config laden → Logging einrichten → BenchmarkRunner → benchmark_ausfuehren
    - Logging: Python `logging`-Modul konfigurieren, alle Schritte protokollieren (Start, Fotos, Stichwörter, Fehler, Ende)
    - Fatale Fehler abfangen und mit aussagekräftiger Meldung beenden
    - Alle Ressourcen (DB-Verbindungen, ExifTool) im finally-Block schließen
    - _Anforderungen: 5.1, 5.4, 7.1, 8.1, 8.2, 8.3, 8.4, 9.5_
  - [x] 13.2 Unit-Tests für main.py
    - Test: Logdatei-Pfad wird auf Konsole ausgegeben
    - _Anforderungen: 8.4_

- [x] 14. Integrationstests
  - [x] 14.1 Integrationstest: Ollama-Kommunikation
    - Mock-HTTP-Server für Ollama-API erstellen
    - Test: Korrekter Request/Response-Zyklus mit base64-Bild und Stichwort-Antwort
    - _Anforderungen: 2.1, 2.2_
  - [x] 14.2 Integrationstest: End-to-End Batch
    - Test-Lightroom-Katalog (SQLite mit Lightroom-Schema und Testdaten) erstellen
    - Mock-Ollama-Server, Testbilder (kleine JPEGs), temporäre Tracking-DB
    - Vollständiger Durchlauf: Katalog lesen → filtern → analysieren → schreiben → tracken
    - _Anforderungen: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_
  - [x] 14.3 Integrationstest: Benchmark End-to-End
    - Mock-Ollama-Server mit mehreren Modellen
    - Testbilder-Verzeichnis, CSV-Ausgabe validieren
    - _Anforderungen: 9.1, 9.2, 9.4_

- [x] 15. Abschluss-Checkpoint
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer fragen.

## Hinweise

- Tasks mit `*` sind optional und können für ein schnelleres MVP übersprungen werden
- Jeder Task referenziert spezifische Anforderungen für Nachverfolgbarkeit
- Checkpoints stellen inkrementelle Validierung sicher
- Property-Tests validieren universelle Korrektheitseigenschaften (Hypothesis, mind. 100 Iterationen)
- Unit-Tests validieren spezifische Beispiele und Fehlerfälle
- Alle Komponenten verwenden Dependency Injection für Testbarkeit
