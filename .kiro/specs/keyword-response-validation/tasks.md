# Implementation Plan: Keyword Response Validation

## Overview

Implementierung einer Antwort-Validierungsschicht mit automatischem Retry-Mechanismus für den Lightroom Ollama Keyword Generator. Die Umsetzung erfolgt inkrementell: zuerst Datenmodelle, dann die reine Validierungslogik, anschließend die Integration in den OllamaClient mit Retry-Loop, dann die Konfigurationserweiterung, und abschließend die Integrationstests.

## Tasks

- [x] 1. Datenmodelle und AntwortValidator erstellen
  - [x] 1.1 Neue Dataclasses `ValidierungsConfig` und `ValidierungsErgebnis` in `lightroom_ollama_keywords/models.py` hinzufügen
    - `ValidierungsConfig` mit Feldern: `max_retries` (int, default 2), `wortanzahl_schwellenwert` (float, default 3.0), `einzeleintrag_schwellenwert` (int, default 4), `retry_prompt` (str, mit deutschem Standardtext)
    - `ValidierungsErgebnis` mit Feldern: `gueltig` (bool), `grund` (str | None, default None)
    - Feld `validierung: ValidierungsConfig` zur bestehenden `Config`-Dataclass hinzufügen (mit `field(default_factory=ValidierungsConfig)`)
    - _Requirements: 1.5, 5.1, 5.2, 5.3_

  - [x] 1.2 Neue Datei `lightroom_ollama_keywords/antwort_validator.py` mit der Klasse `AntwortValidator` erstellen
    - Klassenvariable `ABLEHNUNGS_PHRASEN` mit allen geforderten deutschen und englischen Phrasen
    - Konstruktor nimmt `ValidierungsConfig` entgegen
    - Methode `validieren(keywords: list[str]) -> ValidierungsErgebnis` mit Prüfreihenfolge: leere Liste → Ablehnungsphrase → Einzeleintrag → durchschnittliche Wortanzahl → gültig
    - Hilfsmethode `_durchschnittliche_wortanzahl(keywords: list[str]) -> float`
    - Hilfsmethode `_enthaelt_ablehnungs_phrase(text: str) -> str | None` (case-insensitiv)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 6.1, 6.2, 6.3, 6.4_

  - [x]* 1.3 Property-Test: Durchschnittliche Wortanzahl erkennt Sätze
    - **Property 1: Durchschnittliche Wortanzahl erkennt Sätze**
    - Hypothesis-Strategie: Listen von Strings generieren, bei denen die durchschnittliche Wortanzahl den Schwellenwert überschreitet
    - Datei: `tests/test_antwort_validator_properties.py`
    - **Validates: Requirements 1.2**

  - [x]* 1.4 Property-Test: Ablehnungsphrasen-Erkennung
    - **Property 2: Ablehnungsphrasen-Erkennung (case-insensitiv, Teilstring)**
    - Hypothesis-Strategie: Stichwortlisten mit eingebetteten Ablehnungsphrasen in zufälliger Groß-/Kleinschreibung generieren
    - Datei: `tests/test_antwort_validator_properties.py`
    - **Validates: Requirements 1.3, 6.2, 6.4**

  - [x]* 1.5 Property-Test: Einzeleintrag-Erkennung
    - **Property 3: Einzeleintrag-Erkennung**
    - Hypothesis-Strategie: Einelementige Listen mit Strings generieren, deren Wortanzahl den Einzeleintrag-Schwellenwert überschreitet
    - Datei: `tests/test_antwort_validator_properties.py`
    - **Validates: Requirements 1.4**

  - [x]* 1.6 Property-Test: Ergebnis-Struktur-Invariante
    - **Property 4: Ergebnis-Struktur-Invariante**
    - Hypothesis-Strategie: Beliebige Stichwortlisten generieren und prüfen, dass `gueltig=False` ↔ `grund` ist nicht-leerer String, `gueltig=True` ↔ `grund` ist None
    - Datei: `tests/test_antwort_validator_properties.py`
    - **Validates: Requirements 1.5**

  - [x]* 1.7 Property-Test: Gültige Stichwortlisten werden akzeptiert
    - **Property 5: Gültige Stichwortlisten werden akzeptiert**
    - Hypothesis-Strategie: Nicht-leere Listen von kurzen Stichwörtern (≤2 Wörter, keine Ablehnungsphrasen) generieren
    - Datei: `tests/test_antwort_validator_properties.py`
    - **Validates: Requirements 1.7**

  - [x]* 1.8 Unit-Tests für AntwortValidator
    - Leere Liste → ungültig (Req 1.6)
    - Vordefinierte Ablehnungsphrasen vollständig vorhanden (Req 6.1, 6.3)
    - Standardwerte von ValidierungsConfig korrekt (Req 5.2, 5.3)
    - Datei: `tests/test_antwort_validator.py`
    - _Requirements: 1.6, 5.2, 5.3, 6.1, 6.3_

- [x] 2. Checkpoint – AntwortValidator-Tests prüfen
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. OllamaClient um Validierung und Retry-Mechanismus erweitern
  - [x] 3.1 `OllamaClient.__init__()` um optionalen Parameter `validierungs_config: ValidierungsConfig | None` erweitern
    - `AntwortValidator`-Instanz im Konstruktor erstellen
    - `ValidierungsConfig` speichern (Standardwerte wenn None)
    - _Requirements: 1.1, 5.1_

  - [x] 3.2 `OllamaClient.analyse_bild()` um Validierungs- und Retry-Loop erweitern
    - Nach `_antwort_parsen()`: Ergebnis mit `AntwortValidator.validieren()` prüfen
    - Bei ungültiger Antwort: bis `max_retries` mit `retry_prompt` wiederholen
    - API-Payload bei Retry: `retry_prompt` statt `prompt_template` verwenden
    - Nach erschöpften Retries: letzte Antwort zurückgeben
    - Logging: Retry-Nummer, Bildpfad, Begründung bei jedem Retry (INFO)
    - Logging: Warnung bei erschöpften Retries (WARNING)
    - Logging: Erfolg bei erfolgreichem Retry (INFO)
    - _Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3_

  - [x]* 3.3 Property-Test: Retry-Anzahl ist begrenzt
    - **Property 6: Retry-Anzahl ist begrenzt**
    - Mock `requests.post` mit kontrollierten Sequenzen ungültiger Antworten
    - Prüfen: Gesamtanzahl API-Aufrufe ≤ 1 + max_retries
    - Datei: `tests/test_ollama_client_validation_properties.py`
    - **Validates: Requirements 2.2**

  - [x]* 3.4 Unit-Tests für OllamaClient Retry-Mechanismus
    - Validator wird in `analyse_bild()` aufgerufen (Req 1.1)
    - Retry verwendet `retry_prompt` statt Original-Prompt (Req 2.1, 2.4)
    - Letzte Antwort bei erschöpften Retries zurückgegeben (Req 2.3)
    - Custom `retry_prompt` wird verwendet (Req 2.5)
    - Retry-Logging enthält Bildpfad, Retry-Nr, Grund (Req 3.1)
    - WARNING-Log bei erschöpften Retries (Req 3.2)
    - INFO-Log bei erfolgreichem Retry (Req 3.3)
    - Datei: `tests/test_ollama_client_validation.py`
    - _Requirements: 1.1, 2.1, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3_

- [x] 4. Checkpoint – OllamaClient-Retry-Tests prüfen
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. ConfigLoader um Validierungs-Konfiguration erweitern
  - [x] 5.1 Methode `_parse_validation()` in `lightroom_ollama_keywords/config_loader.py` hinzufügen
    - Optionalen `validation`-Abschnitt aus YAML parsen
    - Felder: `max_retries`, `word_count_threshold`, `single_entry_threshold`, `retry_prompt`
    - Bei fehlendem Abschnitt: `ValidierungsConfig` mit Standardwerten zurückgeben
    - Import von `ValidierungsConfig` aus `models.py` hinzufügen
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 5.2 `ConfigLoader.load()` erweitern, um `config.validierung` zu setzen
    - `self._parse_validation(data.get("validation"))` aufrufen und Ergebnis in `Config.validierung` speichern
    - _Requirements: 5.1_

  - [x]* 5.3 Property-Test: Validierungs-Konfiguration Round-Trip
    - **Property 7: Validierungs-Konfiguration Round-Trip**
    - Hypothesis-Strategie: Gültige Kombinationen von Validierungsparametern generieren, als YAML serialisieren, durch ConfigLoader parsen, Äquivalenz prüfen
    - Datei: `tests/test_config_loader_validation_properties.py`
    - **Validates: Requirements 5.1**

  - [x]* 5.4 Unit-Tests für ConfigLoader Validierungs-Parsing
    - YAML ohne `validation`-Abschnitt → Standardwerte
    - YAML mit teilweisem `validation`-Abschnitt → Standardwerte für fehlende Felder
    - YAML mit vollständigem `validation`-Abschnitt → alle Werte übernommen
    - Datei: `tests/test_config_loader_validation.py`
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 6. Checkpoint – ConfigLoader-Tests prüfen
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Integration verdrahten und Integrationstests
  - [x] 7.1 Aufrufstellen anpassen, die `OllamaClient` instanziieren
    - In `lightroom_ollama_keywords/main.py` (oder wo `OllamaClient` erstellt wird): `validierungs_config` aus `Config.validierung` an `OllamaClient` übergeben
    - Sicherstellen, dass `BatchProcessor` und `KlassifikationsRouter` ohne Änderungen weiterhin funktionieren
    - _Requirements: 4.1, 4.2, 4.3_

  - [x]* 7.2 Integrationstests für transparente Validierung
    - BatchProcessor mit Mock-Ollama: ungültige Antwort → Retry → gültige Antwort, transparent ohne Anpassung am BatchProcessor (Req 4.1)
    - KlassifikationsRouter mit Mock-Ollama: ungültige Antwort → Retry → gültige Antwort, transparent ohne Anpassung am Router (Req 4.2)
    - Datei: `tests/test_integration_validation.py`
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 8. Final Checkpoint – Alle Tests prüfen
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks mit `*` sind optional und können für ein schnelleres MVP übersprungen werden
- Jeder Task referenziert spezifische Anforderungen für Nachvollziehbarkeit
- Checkpoints stellen inkrementelle Validierung sicher
- Property-Tests validieren universelle Korrektheitseigenschaften aus dem Design
- Unit-Tests validieren spezifische Beispiele und Randfälle
- Die Integration in Task 7.1 ist der einzige Punkt, an dem bestehende Dateien außerhalb von `OllamaClient` angepasst werden müssen
