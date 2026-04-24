
# Implementierungsplan: Photo Classification Router

## Übersicht

Erweiterung des Lightroom Ollama Keyword Generators um einen Zwei-Stufen-Prozess: Erst klassifiziert ein schnelles Vision-Modell (gemma4:e2b) jedes Foto in eine von acht Kategorien, dann wählt der KlassifikationsRouter den passenden spezialisierten Prompt und optional ein alternatives Modell für die Stichwort-Generierung. Integration in BatchProcessor und BenchmarkRunner mit Fallback-Strategie bei Fehlern.

## Tasks

- [x] 1. Neue Datenklassen und FotoKategorie-Enum erstellen
  - [x] 1.1 `FotoKategorie`-Enum, `KategorieConfig`, `KlassifikationsConfig` und `KlassifikationsErgebnis` in `lightroom_ollama_keywords/models.py` hinzufügen
    - `FotoKategorie(str, Enum)` mit Werten: Landschaft, Porträt, Architektur, Dokument, Essen, Tiere, Garten, Sonstiges
    - `KategorieConfig` Dataclass mit `prompt: str` und `modell: str | None`
    - `KlassifikationsConfig` Dataclass mit `modell: str`, `prompt: str`, `kategorien: dict[FotoKategorie, KategorieConfig]`
    - `KlassifikationsErgebnis` Dataclass mit `kategorie`, `keywords`, `klassifikations_zeit_ms`, `keyword_zeit_ms`, `verwendeter_prompt_typ`, `verwendetes_modell`
    - _Anforderungen: 1.2, 1.3, 2.1_
  - [x] 1.2 `BenchmarkErgebnis` um optionale Klassifikationsfelder erweitern
    - Neue Felder: `foto_kategorie: str | None = None`, `prompt_typ: str | None = None`, `klassifikations_zeit_ms: float | None = None`
    - _Anforderungen: 7.1, 7.2_
  - [x] 1.3 `KlassifikationsError` in `lightroom_ollama_keywords/errors.py` hinzufügen
    - Erbt von `KeywordGeneratorError`
    - _Anforderungen: 5.1, 5.4_
  - [x] 1.4 `BenchmarkZusammenfassung` um `durchschnitt_klassifikations_ms: float | None = None` erweitern
    - _Anforderungen: 7.3_

- [x] 2. KlassifikationsRouter implementieren
  - [x] 2.1 Neue Datei `lightroom_ollama_keywords/klassifikations_router.py` erstellen mit `KlassifikationsRouter`-Klasse
    - `__init__` mit `endpoint`, `klassifikations_config`, `standard_modell`, `fallback_prompt`
    - Interner `OllamaClient` für Klassifikation erstellen
    - `_KATEGORIE_LOOKUP`-Dictionary für Normalisierung
    - _Anforderungen: 1.1, 2.1, 3.1, 3.2_
  - [x] 2.2 `kategorie_parsen(antwort: str) -> FotoKategorie` als statische Methode implementieren
    - Normalisierung: `strip()`, `lower()`
    - Lookup gegen `_KATEGORIE_LOOKUP`-Dictionary
    - Bei keinem Match: `FotoKategorie.SONSTIGES` zurückgeben
    - _Anforderungen: 8.1, 8.3, 8.4, 5.2_
  - [x] 2.3 `kategorie_formatieren(kategorie: FotoKategorie) -> str` als statische Methode implementieren
    - Gibt `kategorie.value` zurück
    - _Anforderungen: 8.2_
  - [x] 2.4 `bild_analysieren(image_path: str) -> KlassifikationsErgebnis` implementieren
    - Schritt 1: Bild an Klassifikations-Modell senden, Zeit messen
    - Schritt 2: Antwort mit `kategorie_parsen` in FotoKategorie umwandeln
    - Schritt 3: Passenden Prompt + Modell aus KategorieConfig laden
    - Schritt 4: Bild an Stichwort-Modell mit spezialisiertem Prompt senden, Zeit messen
    - Schritt 5: `KlassifikationsErgebnis` zurückgeben
    - _Anforderungen: 1.1, 1.3, 2.1, 2.2–2.9, 3.1, 3.2_
  - [x] 2.5 Fehlerbehandlung in `bild_analysieren` implementieren
    - Bei `OllamaApiError`, `OllamaConnectionError`, `KlassifikationsError`: Fallback-Prompt verwenden
    - Bei Timeout (10s): Timeout loggen, Fallback-Prompt verwenden
    - Fehler mit Foto-Pfad und Details loggen
    - _Anforderungen: 5.1, 5.2, 5.3, 5.4_
  - [x] 2.6 Property-Test: Kategorie-Parsing — Normalisierung und Fallback (Property 1)
    - **Property 1: Kategorie-Parsing — Normalisierung und Fallback**
    - Für alle Strings: `kategorie_parsen` gibt immer ein gültiges `FotoKategorie`-Mitglied zurück. Variationen in Groß-/Kleinschreibung und Whitespace werden korrekt normalisiert. Unbekannte Strings ergeben `SONSTIGES`.
    - **Validiert: Anforderungen 1.2, 5.2, 8.1, 8.3, 8.4**
  - [x] 2.7 Property-Test: Kategorie Round-Trip — Parsen → Formatieren → Parsen (Property 2)
    - **Property 2: Kategorie Round-Trip**
    - Für alle gültigen `FotoKategorie`-Werte: `kategorie_parsen(kategorie_formatieren(kategorie))` ergibt dieselbe `FotoKategorie`.
    - **Validiert: Anforderungen 8.2**
  - [x] 2.8 Property-Test: Prompt- und Modellauswahl nach Kategorie (Property 3)
    - **Property 3: Prompt- und Modellauswahl nach Kategorie**
    - Für alle `FotoKategorie`-Werte und gültige `KategorieConfig`-Mappings: Der Router wählt den korrekten Prompt. Bei alternativem Modell wird dieses verwendet, sonst das Standard-Modell.
    - **Validiert: Anforderungen 2.1, 3.1, 3.2**
  - [x] 2.9 Unit-Tests für KlassifikationsRouter
    - Klassifikation wird vor Stichwort-Generierung aufgerufen (Anforderung 1.1)
    - KlassifikationsErgebnis enthält alle Felder (Anforderung 1.3)
    - Fallback bei OllamaApiError (Anforderung 5.1)
    - Fallback bei Timeout 10s (Anforderung 5.3)
    - Fehler-Logging mit Foto-Pfad und Details (Anforderung 5.4)
    - Kategorie "Sonstiges" verwendet Fallback-Prompt (Anforderung 2.9)

- [x] 3. Checkpoint — Sicherstellen, dass alle Tests bestehen
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer fragen.

- [x] 4. ConfigLoader um Klassifikations-Konfiguration erweitern
  - [x] 4.1 `Config`-Dataclass um `klassifikation: KlassifikationsConfig | None = None` erweitern
    - _Anforderungen: 4.3_
  - [x] 4.2 `ConfigLoader.load` erweitern: `classification`-Abschnitt aus YAML laden
    - Wenn `classification` vorhanden: `KlassifikationsConfig` erstellen mit Modell, Prompt und Kategorien
    - Wenn `classification` fehlt: `klassifikation = None` (deaktiviert, bisheriger Einzelprompt-Modus)
    - Validierung: Jede Kategorie MUSS einen Prompt haben, sonst `ConfigError`
    - _Anforderungen: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [x] 4.3 Property-Test: Klassifikations-Konfigurations-Round-Trip (Property 4)
    - **Property 4: Klassifikations-Konfigurations-Round-Trip**
    - Für alle gültigen `KlassifikationsConfig`-Objekte: Serialisieren als YAML und Laden über `ConfigLoader` ergibt eine äquivalente Konfiguration.
    - **Validiert: Anforderungen 4.1, 4.2, 4.5**
  - [x] 4.4 Property-Test: Validierung fehlender Kategorie-Prompts (Property 5)
    - **Property 5: Validierung fehlender Kategorie-Prompts**
    - Für alle Konfigurationen mit mindestens einer Kategorie ohne Prompt: `ConfigLoader` löst `ConfigError` aus.
    - **Validiert: Anforderungen 4.4**
  - [x] 4.5 Unit-Tests für erweiterten ConfigLoader
    - Classification fehlt → `klassifikation = None` (Anforderung 4.3)
    - Dokument-Kategorie mit alternativem OCR-Modell ladbar (Anforderung 3.3)
    - Klassifikations-Prompt als konfigurierbarer Wert (Anforderung 4.5)

- [x] 5. Checkpoint — Sicherstellen, dass alle Tests bestehen
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer fragen.

- [x] 6. BatchProcessor um KlassifikationsRouter erweitern
  - [x] 6.1 `BatchProcessor.__init__` um optionalen `klassifikations_router: KlassifikationsRouter | None = None` Parameter erweitern
    - _Anforderungen: 6.1_
  - [x] 6.2 `batch_verarbeiten` erweitern: KlassifikationsRouter verwenden wenn vorhanden
    - Wenn `klassifikations_router` vorhanden: `bild_analysieren` statt direktem `OllamaClient`-Aufruf
    - Pro Foto: erkannte Kategorie und verwendetes Modell auf Konsole ausgeben
    - In Zusammenfassung: Anzahl Fotos pro Kategorie ausgeben
    - _Anforderungen: 6.1, 6.2, 6.3_
  - [x] 6.3 Unit-Tests für erweiterten BatchProcessor
    - Delegiert an KlassifikationsRouter wenn vorhanden (Anforderung 6.1)
    - Konsolenausgabe enthält Kategorie und Modell pro Foto (Anforderung 6.2)
    - Zusammenfassung enthält Kategorie-Statistik (Anforderung 6.3)

- [x] 7. BenchmarkRunner um Klassifikation erweitern
  - [x] 7.1 `benchmark_ausfuehren` erweitern: KlassifikationsRouter nutzen wenn `config.klassifikation` vorhanden
    - Pro Bild: `KlassifikationsRouter.bild_analysieren` aufrufen
    - `BenchmarkErgebnis` mit `foto_kategorie`, `prompt_typ`, `klassifikations_zeit_ms` befüllen
    - _Anforderungen: 7.1_
  - [x] 7.2 `_ergebnisse_als_csv_schreiben` erweitern: neue Spalten `foto_kategorie`, `prompt_typ`, `klassifikations_zeit_ms`
    - Spalten nur schreiben wenn Klassifikationsdaten vorhanden
    - _Anforderungen: 7.2_
  - [x] 7.3 `_zusammenfassung_berechnen` erweitern: durchschnittliche Klassifikationszeit pro Modell
    - Neues Feld `durchschnitt_klassifikations_ms` in `BenchmarkZusammenfassung`
    - `_zusammenfassung_ausgeben` um Klassifikationszeit erweitern
    - _Anforderungen: 7.3_
  - [x] 7.4 Property-Test: Erweiterte Benchmark-CSV Round-Trip (Property 6)
    - **Property 6: Erweiterte Benchmark-CSV Round-Trip**
    - Für alle Listen von `BenchmarkErgebnis`-Objekten mit Klassifikationsfeldern: Schreiben als CSV und Einlesen ergibt äquivalente Daten inkl. Klassifikationsspalten.
    - **Validiert: Anforderungen 7.2**
  - [x] 7.5 Property-Test: Benchmark-Zusammenfassung mit Klassifikationszeit (Property 7)
    - **Property 7: Benchmark-Zusammenfassung mit Klassifikationszeit**
    - Für alle Listen von `BenchmarkErgebnis`-Objekten mit Klassifikationszeiten: `durchschnitt_klassifikations_ms` entspricht dem arithmetischen Mittel der erfolgreichen Klassifikationszeiten pro Modell.
    - **Validiert: Anforderungen 7.3**
  - [x] 7.6 Unit-Tests für erweiterten BenchmarkRunner
    - BenchmarkErgebnis enthält foto_kategorie und prompt_typ (Anforderung 7.1)
    - CSV enthält erweiterte Spalten (Anforderung 7.2)
    - Zusammenfassung enthält Klassifikationszeit (Anforderung 7.3)

- [x] 8. Integration und Verdrahtung in main.py
  - [x] 8.1 `main.py` erweitern: KlassifikationsRouter erstellen wenn `config.klassifikation` vorhanden
    - KlassifikationsRouter mit Konfigurationswerten initialisieren
    - An BatchProcessor und BenchmarkRunner übergeben
    - _Anforderungen: 4.3, 6.1, 7.1_
  - [x] 8.2 `benchmark_config.yaml` um Beispiel-`classification`-Abschnitt erweitern
    - Alle 8 Kategorien mit spezialisierten Prompts
    - Dokument-Kategorie mit optionalem alternativem Modell
    - _Anforderungen: 4.1, 4.2, 2.2–2.8, 3.3_
  - [x] 8.3 Integrationstests
    - Klassifikation + Stichwörter End-to-End mit Mock-Ollama
    - Benchmark mit aktivierter Klassifikation, CSV-Validierung
    - Benchmark ohne Klassifikation: Rückwärtskompatibilität
    - _Anforderungen: 6.1, 7.1, 4.3_

- [x] 9. Abschluss-Checkpoint — Sicherstellen, dass alle Tests bestehen
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer fragen.

## Hinweise

- Tasks mit `*` markiert sind optional und können für ein schnelleres MVP übersprungen werden
- Alle Property-Tests verwenden pytest + Hypothesis mit mindestens 100 Iterationen
- Jeder Property-Test referenziert die zugehörige Design-Property und die validierten Anforderungen
- Die Kategorien sind: Landschaft, Porträt, Architektur, Dokument, Essen, Tiere, Garten, Sonstiges
- Fallback-Strategie: Bei jedem Klassifikationsfehler wird der Fallback-Prompt verwendet — kein Foto bleibt unverarbeitet
- Rückwärtskompatibilität: Ohne `classification`-Abschnitt in der YAML funktioniert alles wie bisher
