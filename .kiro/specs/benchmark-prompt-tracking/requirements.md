# Requirements Document

## Einleitung

Dieses Dokument beschreibt die Anforderungen zur Erweiterung des bestehenden Benchmark-Modus im Lightroom Ollama Keyword Generator. Aktuell erzeugt der Benchmark eine CSV-Datei mit den Spalten `model`, `image`, `keywords` und `response_time_ms`. Die Erweiterung umfasst drei Verbesserungen: (1) den verwendeten Prompt in den CSV-Ergebnissen festhalten, damit ältere Benchmark-Läufe mit unterschiedlichen Prompts nachvollziehbar bleiben, (2) zeitgestempelte Ausgabedateien erzeugen, damit frühere Ergebnisse nicht überschrieben werden, und (3) das CSV-Format so gestalten, dass ein visueller Keyword-Vergleich pro Bild über mehrere Modelle hinweg leicht möglich ist.

## Glossar

- **Benchmark_Runner**: Die Komponente, die den Benchmark-Modus orchestriert — sie sendet Testbilder an mehrere Ollama-Modelle, misst die Antwortzeiten und erzeugt die CSV-Ergebnisdatei.
- **Benchmark_CSV**: Die CSV-Ausgabedatei, die pro Zeile ein Benchmark-Ergebnis (Modell, Bild, Stichwörter, Antwortzeit) enthält.
- **Prompt_Template**: Die konfigurierte Textvorlage, die als Prompt an alle Ollama-Modelle gesendet wird.
- **Zeitstempel_Dateiname**: Ein Dateiname, der das Datum und die Uhrzeit des Benchmark-Laufs enthält, um eindeutige Ausgabedateien zu erzeugen.

## Anforderungen

### Anforderung 1: Prompt in CSV-Ergebnissen festhalten

**User Story:** Als Fotograf möchte ich in den Benchmark-Ergebnissen sehen, welcher Prompt verwendet wurde, damit ich ältere Benchmark-Läufe mit unterschiedlichen Prompts nachvollziehen und vergleichen kann.

#### Akzeptanzkriterien

1. WHEN der Benchmark_Runner die Benchmark_CSV schreibt, THE Benchmark_Runner SHALL eine Kommentarzeile am Anfang der Datei einfügen, die den verwendeten Prompt_Template enthält.
2. THE Benchmark_Runner SHALL die Kommentarzeile mit dem Präfix `# prompt: ` beginnen, gefolgt vom vollständigen Prompt_Template-Text in einer einzigen Zeile.
3. WHEN der Prompt_Template Zeilenumbrüche enthält, THE Benchmark_Runner SHALL die Zeilenumbrüche durch Leerzeichen ersetzen, damit die Kommentarzeile einzeilig bleibt.
4. THE Benchmark_Runner SHALL die CSV-Datenzeilen (Header und Ergebnisse) unverändert nach der Kommentarzeile schreiben, sodass bestehende CSV-Parser die Datei weiterhin lesen können, wenn sie Kommentarzeilen ignorieren.

### Anforderung 2: Zeitgestempelte Ausgabedateien

**User Story:** Als Fotograf möchte ich, dass jeder Benchmark-Lauf eine eigene Ausgabedatei mit Zeitstempel erzeugt, damit ältere Ergebnisse erhalten bleiben und ich verschiedene Läufe vergleichen kann.

#### Akzeptanzkriterien

1. WHEN der Benchmark_Runner eine Benchmark_CSV erzeugt, THE Benchmark_Runner SHALL den Dateinamen aus dem konfigurierten Basispfad und einem Zeitstempel im Format `YYYYMMDD_HHMMSS` zusammensetzen.
2. THE Benchmark_Runner SHALL den Zeitstempel_Dateiname nach dem Muster `{basisname}_{YYYYMMDD_HHMMSS}.csv` bilden, wobei `{basisname}` der Dateiname ohne `.csv`-Endung aus der Konfiguration ist.
3. THE Benchmark_Runner SHALL den Zeitstempel zum Startzeitpunkt des Benchmark-Laufs erfassen, sodass alle Ergebnisse eines Laufs denselben Zeitstempel tragen.
4. THE Benchmark_Runner SHALL den vollständigen Pfad der erzeugten Benchmark_CSV auf der Konsole ausgeben, damit der Benutzer die Datei leicht finden kann.
5. IF eine Datei mit dem erzeugten Zeitstempel_Dateiname bereits existiert, THEN THE Benchmark_Runner SHALL die bestehende Datei überschreiben, da zwei Benchmark-Läufe in derselben Sekunde nicht erwartet werden.

### Anforderung 3: Visueller Keyword-Vergleich pro Bild

**User Story:** Als Fotograf möchte ich die Keywords verschiedener Modelle pro Bild visuell vergleichen können, damit ich auf einen Blick sehe, welches Modell die besten Stichwörter für ein bestimmtes Bild erzeugt hat.

#### Akzeptanzkriterien

1. THE Benchmark_Runner SHALL die Benchmark_CSV nach Bildnamen gruppiert sortieren, sodass alle Ergebnisse für dasselbe Bild direkt untereinander stehen.
2. WHEN die Benchmark_CSV nach Bildnamen sortiert ist, THE Benchmark_Runner SHALL innerhalb jeder Bildgruppe die Zeilen nach Modellnamen alphabetisch sortieren.
3. THE Benchmark_Runner SHALL eine Leerzeile zwischen den Bildgruppen einfügen, damit die Gruppen visuell voneinander getrennt sind.
4. THE Benchmark_Runner SHALL die CSV-Spalte `keywords` weiterhin als semikolon-getrennte Liste formatieren, um die Kompatibilität mit bestehenden Auswertungen zu gewährleisten.
