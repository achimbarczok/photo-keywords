# Requirements Document

## Einleitung

Dieses Dokument beschreibt die Anforderungen für eine automatisierte Routine zur Stichwort-Vergabe für Fotos in Adobe Lightroom Classic. Die Routine nutzt Ollama mit einem lokal installierten LLM zur Bilderkennung, um Stichwörter zu generieren und diese als Metadaten in den Lightroom-Katalog zu schreiben. Ein Tracking-Mechanismus stellt sicher, dass bereits verarbeitete Fotos nicht erneut eingelesen werden. Die Lösung läuft unter Windows.

## Glossar

- **Keyword_Generator**: Das Gesamtsystem, das Fotos aus dem Lightroom-Katalog liest, über Ollama analysiert und Stichwörter zurückschreibt.
- **Ollama_Client**: Die Komponente, die mit der lokalen Ollama-Instanz kommuniziert und Bildanalyse-Anfragen sendet.
- **Katalog_Leser**: Die Komponente, die den Lightroom-Classic-Katalog (SQLite-Datenbank) ausliest, um Foto-Metadaten und Dateipfade zu ermitteln.
- **Stichwort_Schreiber**: Die Komponente, die generierte Stichwörter in die Foto-Metadaten (XMP-Sidecar oder eingebettete EXIF/IPTC-Daten) schreibt.
- **Verarbeitungs_Tracker**: Die Komponente, die protokolliert, welche Fotos mit welchem LLM-Modell und welcher Modellversion bereits verarbeitet wurden.
- **Lightroom_Katalog**: Die SQLite-Datenbank von Adobe Lightroom Classic, die Foto-Metadaten und Verweise auf Bilddateien enthält.
- **XMP-Sidecar**: Eine XML-basierte Datei, die Metadaten neben der Originalbilddatei speichert.
- **Ollama**: Ein lokal installiertes Framework zum Ausführen von LLMs, das eine REST-API bereitstellt.
- **LLM-Modell**: Ein spezifisches Large Language Model mit Bilderkennungsfähigkeit (z.B. llava, bakllava), das über Ollama ausgeführt wird.
- **Batch**: Eine konfigurierbare Gruppe von Fotos, die in einem Durchlauf verarbeitet wird.
- **Benchmark_Runner**: Die Komponente, die den Benchmark-Modus orchestriert — sie sendet Testbilder an mehrere Ollama-Modelle, misst die Antwortzeiten und erzeugt die CSV-Ergebnisdatei.

## Anforderungen

### Anforderung 1: Unverarbeitete Fotos identifizieren

**User Story:** Als Fotograf möchte ich, dass das System automatisch erkennt, welche Fotos noch nicht mit einem bestimmten LLM-Modell verarbeitet wurden, damit keine doppelte Verarbeitung stattfindet.

#### Akzeptanzkriterien

1. WHEN der Keyword_Generator gestartet wird, THE Katalog_Leser SHALL alle Foto-Einträge aus dem Lightroom_Katalog auslesen und deren Dateipfade ermitteln.
2. WHEN die Foto-Liste ermittelt wurde, THE Verarbeitungs_Tracker SHALL für jedes Foto prüfen, ob es bereits mit dem aktuell konfigurierten LLM-Modell (Name und Version) verarbeitet wurde.
3. THE Keyword_Generator SHALL nur Fotos zur Verarbeitung weiterleiten, die noch nicht mit dem aktuell konfigurierten LLM-Modell verarbeitet wurden.
4. IF der Lightroom_Katalog nicht gefunden oder nicht gelesen werden kann, THEN THE Katalog_Leser SHALL eine aussagekräftige Fehlermeldung mit dem erwarteten Katalogpfad ausgeben und die Verarbeitung abbrechen.

### Anforderung 2: Bildanalyse über Ollama

**User Story:** Als Fotograf möchte ich, dass meine Fotos von einem lokalen LLM analysiert werden, damit automatisch passende Stichwörter generiert werden.

#### Akzeptanzkriterien

1. WHEN ein unverarbeitetes Foto zur Analyse bereitsteht, THE Ollama_Client SHALL das Bild an die lokale Ollama-REST-API senden und eine Stichwort-Analyse anfordern.
2. THE Ollama_Client SHALL dem LLM-Modell einen konfigurierbaren Prompt senden, der das Modell anweist, beschreibende Stichwörter für das Bild zu generieren.
3. WHEN die Ollama-API eine Antwort liefert, THE Ollama_Client SHALL die Antwort in eine Liste einzelner Stichwörter parsen.
4. IF die Ollama-API nicht erreichbar ist, THEN THE Ollama_Client SHALL eine Fehlermeldung ausgeben, die den konfigurierten Ollama-Endpunkt enthält, und die Verarbeitung abbrechen.
5. IF die Ollama-API einen Fehler zurückgibt, THEN THE Ollama_Client SHALL den Fehlercode und die Fehlermeldung protokollieren und mit dem nächsten Foto fortfahren.
6. IF die Bilddatei nicht gelesen werden kann, THEN THE Ollama_Client SHALL den Dateipfad und den Fehlergrund protokollieren und mit dem nächsten Foto fortfahren.

### Anforderung 3: Stichwörter in Foto-Metadaten schreiben

**User Story:** Als Fotograf möchte ich, dass die generierten Stichwörter in die Foto-Metadaten geschrieben werden, damit sie in Lightroom und anderen Programmen sichtbar sind.

#### Akzeptanzkriterien

1. WHEN Stichwörter für ein Foto generiert wurden, THE Stichwort_Schreiber SHALL die Stichwörter als IPTC-Keywords in die Metadaten der Bilddatei schreiben.
2. THE Stichwort_Schreiber SHALL bereits vorhandene Stichwörter in der Bilddatei beibehalten und die neuen Stichwörter ergänzen, ohne Duplikate zu erzeugen.
3. THE Stichwort_Schreiber SHALL keine bereits vorhandenen Stichwörter entfernen oder überschreiben.
4. IF das Schreiben der Metadaten fehlschlägt, THEN THE Stichwort_Schreiber SHALL den Dateipfad und den Fehlergrund protokollieren und mit dem nächsten Foto fortfahren.

### Anforderung 4: Verarbeitungs-Tracking

**User Story:** Als Fotograf möchte ich nachvollziehen können, welche Fotos mit welchem LLM-Modell verarbeitet wurden, damit ich bei einem Modellwechsel gezielt erneut verarbeiten kann.

#### Akzeptanzkriterien

1. WHEN ein Foto erfolgreich verarbeitet und die Stichwörter geschrieben wurden, THE Verarbeitungs_Tracker SHALL einen Eintrag mit dem Dateipfad des Fotos, dem LLM-Modellnamen, der Modellversion und dem Verarbeitungszeitstempel speichern.
2. THE Verarbeitungs_Tracker SHALL die Tracking-Daten in einer lokalen Datei (z.B. SQLite-Datenbank oder JSON-Datei) persistent speichern.
3. WHEN ein anderes LLM-Modell konfiguriert wird, THE Verarbeitungs_Tracker SHALL die betreffenden Fotos als unverarbeitet für dieses neue Modell behandeln.
4. THE Verarbeitungs_Tracker SHALL für jedes Foto mehrere Verarbeitungseinträge (einen pro LLM-Modell) unterstützen.
5. IF die Tracking-Datei nicht gelesen oder geschrieben werden kann, THEN THE Verarbeitungs_Tracker SHALL eine Fehlermeldung mit dem Dateipfad ausgeben und die Verarbeitung abbrechen.

### Anforderung 5: Batch-Verarbeitung

**User Story:** Als Fotograf möchte ich die Verarbeitung in konfigurierbaren Batches durchführen, damit ich die Systemlast kontrollieren und den Fortschritt verfolgen kann.

#### Akzeptanzkriterien

1. THE Keyword_Generator SHALL eine konfigurierbare Batch-Größe unterstützen, die die Anzahl der Fotos pro Durchlauf begrenzt.
2. WHILE ein Batch verarbeitet wird, THE Keyword_Generator SHALL den Fortschritt auf der Konsole ausgeben (aktuelles Foto, Gesamtanzahl, verbleibende Fotos).
3. WHEN ein Batch vollständig verarbeitet wurde, THE Keyword_Generator SHALL eine Zusammenfassung ausgeben (Anzahl verarbeiteter Fotos, Anzahl Fehler, Dauer).
4. THE Keyword_Generator SHALL die Verarbeitung nach Abschluss eines Batches beenden, sodass der nächste Batch durch erneuten Start fortgesetzt werden kann.

### Anforderung 6: Konfiguration

**User Story:** Als Fotograf möchte ich alle relevanten Parameter zentral konfigurieren können, damit ich die Routine flexibel an meine Umgebung anpassen kann.

#### Akzeptanzkriterien

1. THE Keyword_Generator SHALL folgende Parameter über eine Konfigurationsdatei unterstützen: Pfad zum Lightroom_Katalog, Ollama-API-Endpunkt, LLM-Modellname, Batch-Größe und Prompt-Vorlage.
2. IF ein erforderlicher Konfigurationsparameter fehlt, THEN THE Keyword_Generator SHALL eine Fehlermeldung ausgeben, die den fehlenden Parameter benennt, und die Verarbeitung abbrechen.
3. THE Keyword_Generator SHALL sinnvolle Standardwerte für optionale Parameter bereitstellen (Ollama-Endpunkt: http://localhost:11434, Batch-Größe: 50).

### Anforderung 7: Lightroom-Synchronisation

**User Story:** Als Fotograf möchte ich die extern geschriebenen Stichwörter in Lightroom sehen können, damit ich sie für die Organisation meiner Fotos nutzen kann.

#### Akzeptanzkriterien

1. WHEN die Stichwörter in die Bilddateien geschrieben wurden, THE Keyword_Generator SHALL den Benutzer darauf hinweisen, dass in Lightroom die Funktion "Metadaten aus Datei lesen" ausgeführt werden muss, um die neuen Stichwörter zu importieren.
2. THE Stichwort_Schreiber SHALL die Stichwörter im standardkonformen IPTC/XMP-Format schreiben, sodass Lightroom Classic die Stichwörter korrekt einlesen kann.

### Anforderung 8: Protokollierung

**User Story:** Als Fotograf möchte ich eine detaillierte Protokollierung der Verarbeitung, damit ich Fehler nachvollziehen und die Ergebnisse überprüfen kann.

#### Akzeptanzkriterien

1. THE Keyword_Generator SHALL alle Verarbeitungsschritte in eine Logdatei schreiben (Start, verarbeitete Fotos, generierte Stichwörter, Fehler, Ende).
2. WHEN ein Foto erfolgreich verarbeitet wurde, THE Keyword_Generator SHALL den Dateipfad und die generierten Stichwörter in die Logdatei schreiben.
3. WHEN ein Fehler auftritt, THE Keyword_Generator SHALL den Fehler mit Zeitstempel, Dateipfad (falls zutreffend) und Fehlerbeschreibung in die Logdatei schreiben.
4. THE Keyword_Generator SHALL den Pfad zur Logdatei beim Start auf der Konsole ausgeben.

### Anforderung 9: Benchmark-Modus

**User Story:** Als Fotograf möchte ich verschiedene Ollama-Vision-Modelle systematisch vergleichen können, damit ich das Modell mit dem besten Verhältnis aus Keyword-Qualität und Antwortzeit für meinen Workflow auswählen kann.

#### Akzeptanzkriterien

1. WHEN der Keyword_Generator im Benchmark-Modus gestartet wird, THE Keyword_Generator SHALL ein angegebenes Verzeichnis mit Testbildern einlesen und jedes Testbild an alle konfigurierten Ollama-Vision-Modelle senden.
2. THE Keyword_Generator SHALL für jede Kombination aus Testbild und Modell die Antwortzeit in Millisekunden messen.
3. THE Keyword_Generator SHALL für alle Modelle im Benchmark dieselbe Prompt-Vorlage verwenden, um einen fairen Vergleich sicherzustellen.
4. WHEN der Benchmark abgeschlossen ist, THE Keyword_Generator SHALL die Ergebnisse als CSV-Datei ausgeben, die pro Zeile das Modell, den Bilddateinamen, die generierten Stichwörter und die Antwortzeit in Millisekunden enthält.
5. THE Keyword_Generator SHALL den Benchmark-Modus über einen CLI-Parameter (z.B. `--benchmark`) aktivierbar machen, der ein Verzeichnis mit Testbildern als Argument erwartet.
6. THE Keyword_Generator SHALL die Liste der zu vergleichenden Modelle über die Konfigurationsdatei unterstützen (z.B. moondream, llava-phi3, gemma3, llava:7b, minicpm-v).
7. IF ein konfiguriertes Modell während des Benchmarks nicht erreichbar oder nicht verfügbar ist, THEN THE Keyword_Generator SHALL den Modellnamen und den Fehlergrund protokollieren und mit dem nächsten Modell fortfahren.
8. WHEN der Benchmark abgeschlossen ist, THE Keyword_Generator SHALL eine Zusammenfassung auf der Konsole ausgeben, die pro Modell die Anzahl verarbeiteter Bilder, die durchschnittliche Antwortzeit und die Anzahl der Fehler enthält.
