# Anforderungsdokument: Photo Classification Router

## Einleitung

Dieses Feature erweitert den Lightroom Ollama Keyword Generator um einen Vor-Klassifizierungsschritt. Bevor die eigentliche Stichwort-Generierung stattfindet, klassifiziert ein schnelles, kleines Vision-Modell (z. B. gemma4:e2b) jedes Foto in eine Kategorie (Landschaft, Porträt, Architektur, Dokument/Text, Essen, Tiere usw.). Basierend auf dieser Klassifikation wählt das System dann einen spezialisierten Prompt — und optional ein anderes Modell — aus, das für diesen Fototyp optimiert ist. Dadurch werden die generierten Stichwörter präziser und domänenspezifischer.

## Glossar

- **Klassifikations_Router**: Die Komponente, die den gesamten Zwei-Stufen-Prozess orchestriert — erst Klassifikation, dann spezialisierte Stichwort-Generierung.
- **Klassifikations_Modell**: Das schnelle, kleine Vision-Modell (z. B. gemma4:e2b), das für die Vor-Klassifizierung der Fotos verwendet wird.
- **Foto_Kategorie**: Eine vordefinierte Kategorie, in die ein Foto eingeordnet wird (z. B. Landschaft, Porträt, Architektur, Dokument, Essen, Tiere, Garten).
- **Kategorie_Konfiguration**: Die YAML-Konfiguration, die pro Foto_Kategorie den spezialisierten Prompt und optional ein alternatives Modell definiert.
- **Klassifikations_Ergebnis**: Das Ergebnis der Vor-Klassifizierung, bestehend aus der erkannten Foto_Kategorie und einem Konfidenzwert.
- **Spezialisierter_Prompt**: Ein auf eine bestimmte Foto_Kategorie zugeschnittener Prompt, der domänenspezifische Stichwörter erzeugt.
- **OllamaClient**: Der bestehende Client für die Kommunikation mit der Ollama REST API.
- **ConfigLoader**: Die bestehende Komponente zum Laden und Validieren der YAML-Konfiguration.
- **BatchProcessor**: Die bestehende Komponente zur Batch-Verarbeitung von Fotos.
- **Fallback_Prompt**: Der allgemeine Standard-Prompt, der verwendet wird, wenn keine Kategorie erkannt werden kann.

## Anforderungen

### Anforderung 1: Foto-Klassifikation

**User Story:** Als Fotograf möchte ich, dass jedes Foto automatisch in eine Kategorie eingeordnet wird, damit anschließend ein optimierter Prompt für die Stichwort-Generierung verwendet werden kann.

#### Akzeptanzkriterien

1. WHEN ein Foto zur Verarbeitung übergeben wird, THE Klassifikations_Router SHALL das Foto zuerst an das Klassifikations_Modell senden und eine Foto_Kategorie ermitteln.
2. THE Klassifikations_Modell SHALL jedes Foto in genau eine der folgenden vordefinierten Kategorien einordnen: Landschaft, Porträt, Architektur, Dokument, Essen, Tiere, Garten, Sonstiges.
3. WHEN das Klassifikations_Modell eine Foto_Kategorie zurückgibt, THE Klassifikations_Router SHALL die erkannte Kategorie zusammen mit dem Konfidenzwert als Klassifikations_Ergebnis speichern.
4. THE Klassifikations_Modell SHALL die Klassifikation eines einzelnen Fotos in unter 2000 Millisekunden abschließen, um den Gesamtprozess nicht wesentlich zu verlangsamen.

### Anforderung 2: Kategorie-basierte Prompt-Auswahl

**User Story:** Als Fotograf möchte ich, dass je nach Foto-Kategorie ein spezialisierter Prompt verwendet wird, damit die generierten Stichwörter präziser und domänenspezifischer sind.

#### Akzeptanzkriterien

1. WHEN ein Klassifikations_Ergebnis vorliegt, THE Klassifikations_Router SHALL den zur erkannten Foto_Kategorie gehörenden Spezialisierten_Prompt aus der Kategorie_Konfiguration laden.
2. THE Klassifikations_Router SHALL für die Kategorie "Landschaft" einen Spezialisierten_Prompt verwenden, der auf Wetter, Tageszeit, Vegetation und Gelände fokussiert.
3. THE Klassifikations_Router SHALL für die Kategorie "Architektur" einen Spezialisierten_Prompt verwenden, der auf Gebäudetyp, Architekturstil und berühmte Wahrzeichen fokussiert.
4. THE Klassifikations_Router SHALL für die Kategorie "Dokument" einen Spezialisierten_Prompt verwenden, der auf OCR-basierte Stichwörter und Textinhalte fokussiert.
5. THE Klassifikations_Router SHALL für die Kategorie "Porträt" einen Spezialisierten_Prompt verwenden, der auf Personen, Gesichtsausdrücke und Kleidung fokussiert.
6. THE Klassifikations_Router SHALL für die Kategorie "Essen" einen Spezialisierten_Prompt verwenden, der auf Gerichte, Zutaten und Präsentation fokussiert.
7. THE Klassifikations_Router SHALL für die Kategorie "Tiere" einen Spezialisierten_Prompt verwenden, der auf Artenbestimmung, Lebensraum und Verhalten fokussiert.
8. THE Klassifikations_Router SHALL für die Kategorie "Garten" einen Spezialisierten_Prompt verwenden, der auf Pflanzenarten, Blüten, Gartengestaltung, Jahreszeit und Gartenelemente fokussiert.
9. WHEN die erkannte Foto_Kategorie "Sonstiges" ist, THE Klassifikations_Router SHALL den Fallback_Prompt verwenden.

### Anforderung 3: Kategorie-basierte Modellauswahl

**User Story:** Als Fotograf möchte ich, dass für bestimmte Foto-Kategorien ein spezialisiertes Modell verwendet werden kann, damit die Ergebnisqualität maximiert wird.

#### Akzeptanzkriterien

1. WHERE eine Kategorie_Konfiguration ein alternatives Modell für eine Foto_Kategorie definiert, THE Klassifikations_Router SHALL dieses alternative Modell anstelle des Standard-Modells für die Stichwort-Generierung verwenden.
2. WHERE keine Kategorie_Konfiguration ein alternatives Modell für eine Foto_Kategorie definiert, THE Klassifikations_Router SHALL das in der Hauptkonfiguration definierte Standard-Modell verwenden.
3. WHEN die Kategorie "Dokument" erkannt wird, THE Kategorie_Konfiguration SHALL die Möglichkeit bieten, ein OCR-spezialisiertes Modell (z. B. glm-ocr) zu konfigurieren.

### Anforderung 4: YAML-Konfiguration für Klassifikation und Routing

**User Story:** Als Fotograf möchte ich die Klassifikation und das Routing über die YAML-Konfigurationsdatei steuern können, damit ich Prompts, Modelle und Kategorien flexibel anpassen kann.

#### Akzeptanzkriterien

1. THE ConfigLoader SHALL einen neuen Konfigurationsabschnitt "classification" aus der YAML-Datei laden, der das Klassifikations_Modell, den Klassifikations-Prompt und die Kategorie-Definitionen enthält.
2. THE ConfigLoader SHALL für jede Foto_Kategorie im Abschnitt "classification.categories" den Spezialisierten_Prompt und optional ein alternatives Modell laden.
3. IF der Konfigurationsabschnitt "classification" fehlt, THEN THE ConfigLoader SHALL die Klassifikation deaktivieren und den bisherigen Einzelprompt-Modus verwenden.
4. IF eine Foto_Kategorie in der Konfiguration keinen Spezialisierten_Prompt definiert, THEN THE ConfigLoader SHALL einen Validierungsfehler melden.
5. THE ConfigLoader SHALL den Klassifikations-Prompt als konfigurierbaren Wert laden, damit der Benutzer die Klassifikationsanweisung anpassen kann.

### Anforderung 5: Fehlerbehandlung bei der Klassifikation

**User Story:** Als Fotograf möchte ich, dass die Verarbeitung auch bei Klassifikationsfehlern fortgesetzt wird, damit keine Fotos unverarbeitet bleiben.

#### Akzeptanzkriterien

1. IF das Klassifikations_Modell einen Fehler zurückgibt, THEN THE Klassifikations_Router SHALL den Fallback_Prompt verwenden und die Verarbeitung fortsetzen.
2. IF das Klassifikations_Modell eine unbekannte Kategorie zurückgibt, THEN THE Klassifikations_Router SHALL die Kategorie "Sonstiges" zuweisen und den Fallback_Prompt verwenden.
3. IF das Klassifikations_Modell nicht innerhalb von 10000 Millisekunden antwortet, THEN THE Klassifikations_Router SHALL den Timeout protokollieren und den Fallback_Prompt verwenden.
4. WHEN ein Klassifikationsfehler auftritt, THE Klassifikations_Router SHALL den Fehler mit Foto-Pfad und Fehlerdetails im Log protokollieren.

### Anforderung 6: Integration in Batch-Verarbeitung

**User Story:** Als Fotograf möchte ich, dass die Klassifikation nahtlos in die bestehende Batch-Verarbeitung integriert wird, damit ich den Workflow nicht manuell anpassen muss.

#### Akzeptanzkriterien

1. WHEN der BatchProcessor ein Foto verarbeitet und die Klassifikation aktiviert ist, THE BatchProcessor SHALL den Klassifikations_Router anstelle des direkten OllamaClient-Aufrufs verwenden.
2. WHILE die Batch-Verarbeitung läuft, THE BatchProcessor SHALL für jedes Foto die erkannte Foto_Kategorie und das verwendete Modell auf der Konsole ausgeben.
3. THE BatchProcessor SHALL in der Zusammenfassung die Anzahl der Fotos pro Foto_Kategorie ausgeben.

### Anforderung 7: Integration in Benchmark-Modus

**User Story:** Als Fotograf möchte ich den Klassifikations-Router auch im Benchmark-Modus testen können, damit ich die Qualität der kategorie-spezifischen Prompts vergleichen kann.

#### Akzeptanzkriterien

1. WHEN der Benchmark-Modus mit aktivierter Klassifikation ausgeführt wird, THE BenchmarkRunner SHALL für jedes Bild die erkannte Foto_Kategorie und den verwendeten Spezialisierten_Prompt in den Benchmark-Ergebnissen erfassen.
2. THE BenchmarkRunner SHALL in der CSV-Ausgabe zusätzliche Spalten für die erkannte Foto_Kategorie und den verwendeten Prompt-Typ enthalten.
3. THE BenchmarkRunner SHALL in der Zusammenfassung die durchschnittliche Klassifikationszeit pro Modell ausgeben.

### Anforderung 8: Klassifikations-Ergebnis-Parsing

**User Story:** Als Entwickler möchte ich, dass die Antwort des Klassifikations_Modells zuverlässig in eine Foto_Kategorie geparst wird, damit das Routing korrekt funktioniert.

#### Akzeptanzkriterien

1. THE Klassifikations_Router SHALL die Textantwort des Klassifikations_Modells in eine gültige Foto_Kategorie parsen.
2. THE Klassifikations_Router SHALL die geparste Foto_Kategorie zurück in einen normalisierten Kategorienamen formatieren können (Round-Trip-Eigenschaft: Parsen → Formatieren → Parsen ergibt dieselbe Foto_Kategorie).
3. WHEN die Textantwort Variationen in Groß-/Kleinschreibung oder führende/nachfolgende Leerzeichen enthält, THE Klassifikations_Router SHALL diese normalisieren und die korrekte Foto_Kategorie zuordnen.
4. WHEN die Textantwort keine gültige Foto_Kategorie enthält, THE Klassifikations_Router SHALL die Kategorie "Sonstiges" zuweisen.
