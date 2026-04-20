# Requirements Document

## Introduction

Dieses Feature erweitert den Lightroom Ollama Keyword Generator um standortbasierte Stichwörter. GPS-Koordinaten werden aus EXIF-Metadaten der Bilddateien und aus der Lightroom-Katalog-Datenbank gelesen. Mittels Offline-Reverse-Geocoding (`reverse_geocoder`) werden die Koordinaten in Ortsnamen (Stadt, Region, Land) aufgelöst. Die Standortdaten werden auf zwei Wegen genutzt: (a) als zusätzliche Stichwörter direkt in die Bilddatei geschrieben und (b) als Kontext in den Ollama-Prompt injiziert, damit das KI-Modell kontextbezogenere Stichwörter generiert.

## Glossary

- **GPS_Leser**: Modul, das GPS-Koordinaten aus EXIF-Metadaten von Bilddateien und aus der Lightroom-Katalog-Datenbank liest
- **Standort_Resolver**: Modul, das GPS-Koordinaten mittels Offline-Reverse-Geocoding in Ortsnamen (Stadt, Region, Land) auflöst
- **Standort_Daten**: Datenstruktur mit den aufgelösten Ortsinformationen (Stadt, Region, Land, Breitengrad, Längengrad)
- **OllamaClient**: Bestehender Client für die Ollama REST API zur Bildanalyse
- **KlassifikationsRouter**: Bestehender Zwei-Stufen-Prozess für Klassifikation und spezialisierte Stichwort-Generierung
- **BatchProcessor**: Bestehender Batch-Verarbeitungsprozess für Fotos
- **BenchmarkRunner**: Bestehender Benchmark-Modus für Modellvergleiche
- **StichwortSchreiber**: Bestehender Schreiber für IPTC/XMP-Keywords in Bilddateien
- **KatalogLeser**: Bestehender Leser für den Lightroom-Katalog (SQLite)
- **reverse_geocoder**: Python-Paket für Offline-Reverse-Geocoding (GPS → Ortsname)
- **EXIF_Daten**: Metadaten in Bilddateien, die unter anderem GPS-Koordinaten enthalten können

## Requirements

### Requirement 1: GPS-Koordinaten aus EXIF-Metadaten lesen

**User Story:** Als Fotograf möchte ich, dass GPS-Koordinaten automatisch aus den EXIF-Metadaten meiner Bilddateien gelesen werden, damit Standortinformationen für die Stichwort-Generierung verfügbar sind.

#### Acceptance Criteria

1. WHEN eine Bilddatei mit GPS-EXIF-Daten verarbeitet wird, THE GPS_Leser SHALL die Breitengrad- und Längengradwerte als Dezimalgrad-Paar extrahieren
2. WHEN eine Bilddatei keine GPS-EXIF-Daten enthält, THE GPS_Leser SHALL None zurückgeben
3. WHEN die GPS-EXIF-Daten ein ungültiges Format haben, THE GPS_Leser SHALL None zurückgeben und den Fehler protokollieren
4. THE GPS_Leser SHALL GPS-Koordinaten aus EXIF-Daten lesen, ohne externe Netzwerkverbindungen zu benötigen

### Requirement 2: GPS-Koordinaten aus Lightroom-Katalog lesen

**User Story:** Als Fotograf möchte ich, dass GPS-Koordinaten auch aus meinem Lightroom-Katalog gelesen werden, damit manuell zugewiesene Standorte ebenfalls berücksichtigt werden.

#### Acceptance Criteria

1. WHEN ein Foto im Lightroom-Katalog GPS-Koordinaten gespeichert hat, THE KatalogLeser SHALL die Breitengrad- und Längengradwerte als Dezimalgrad-Paar zurückgeben
2. WHEN ein Foto im Lightroom-Katalog keine GPS-Koordinaten hat, THE KatalogLeser SHALL None für die GPS-Daten zurückgeben
3. WHEN sowohl EXIF-Daten als auch Lightroom-Katalog GPS-Daten vorhanden sind, THE GPS_Leser SHALL die Lightroom-Katalog-Daten bevorzugen, da diese manuell korrigiert sein können

### Requirement 3: Offline-Reverse-Geocoding

**User Story:** Als Fotograf möchte ich, dass GPS-Koordinaten offline in lesbare Ortsnamen aufgelöst werden, damit keine Internetverbindung benötigt wird.

#### Acceptance Criteria

1. WHEN gültige GPS-Koordinaten übergeben werden, THE Standort_Resolver SHALL die Koordinaten mittels des `reverse_geocoder`-Pakets in Standort_Daten (Stadt, Region, Land) auflösen
2. THE Standort_Resolver SHALL ausschließlich Offline-Reverse-Geocoding verwenden, ohne Online-API-Aufrufe
3. WHEN das `reverse_geocoder`-Paket nicht installiert ist, THE Standort_Resolver SHALL einen ImportError mit einer beschreibenden Fehlermeldung auslösen
4. WHEN die Koordinaten (0.0, 0.0) übergeben werden, THE Standort_Resolver SHALL diese als ungültig behandeln und None zurückgeben
5. FOR ALL gültigen GPS-Koordinatenpaare (Breitengrad zwischen -90 und 90, Längengrad zwischen -180 und 180, nicht (0.0, 0.0)), THE Standort_Resolver SHALL Standort_Daten mit nicht-leeren Werten für Stadt und Land zurückgeben

### Requirement 4: Standort als Stichwörter hinzufügen

**User Story:** Als Fotograf möchte ich, dass Ortsnamen automatisch als Stichwörter zu meinen Fotos hinzugefügt werden, damit meine Fotos nach Standort durchsuchbar sind.

#### Acceptance Criteria

1. WHEN Standort_Daten für ein Foto verfügbar sind, THE BatchProcessor SHALL die Ortsnamen (Stadt, Region, Land) als zusätzliche Stichwörter zusammen mit den KI-generierten Stichwörtern an den StichwortSchreiber übergeben
2. WHEN Standort_Daten für ein Foto verfügbar sind, THE BatchProcessor SHALL die Standort-Stichwörter mit den KI-generierten Stichwörtern zusammenführen, ohne Duplikate zu erzeugen
3. WHEN keine Standort_Daten für ein Foto verfügbar sind, THE BatchProcessor SHALL ausschließlich die KI-generierten Stichwörter verwenden
4. THE BatchProcessor SHALL leere Standort-Felder (leere Zeichenketten) aus den Standort-Stichwörtern herausfiltern

### Requirement 5: Standort-Kontext in Ollama-Prompt injizieren

**User Story:** Als Fotograf möchte ich, dass der Aufnahmeort in den KI-Prompt einfließt, damit das Modell kontextbezogenere Stichwörter generiert.

#### Acceptance Criteria

1. WHEN Standort_Daten für ein Foto verfügbar sind, THE OllamaClient SHALL den Standort-Kontext als Präfix in den Prompt einfügen (z.B. "Dieses Foto wurde in Berlin, Deutschland aufgenommen.")
2. WHEN keine Standort_Daten für ein Foto verfügbar sind, THE OllamaClient SHALL den Prompt ohne Standort-Kontext verwenden
3. WHEN der KlassifikationsRouter aktiv ist und Standort_Daten verfügbar sind, THE KlassifikationsRouter SHALL den Standort-Kontext in den spezialisierten Kategorie-Prompt einfügen
4. THE OllamaClient SHALL den Standort-Kontext vor dem bestehenden Prompt-Text einfügen, ohne den bestehenden Prompt zu verändern

### Requirement 6: Benchmark-Modus mit Standortdaten

**User Story:** Als Entwickler möchte ich, dass der Benchmark-Modus ebenfalls Standortdaten berücksichtigt, damit ich die Auswirkung von Standort-Kontext auf die Keyword-Qualität messen kann.

#### Acceptance Criteria

1. WHEN der Benchmark-Modus ausgeführt wird, THE BenchmarkRunner SHALL GPS-Daten aus den EXIF-Metadaten der Benchmark-Bilder lesen
2. WHEN der Benchmark-Modus ausgeführt wird, THE BenchmarkRunner SHALL keine GPS-Daten aus dem Lightroom-Katalog lesen
3. WHEN ein Benchmark-Bild GPS-EXIF-Daten enthält, THE BenchmarkRunner SHALL den Standort-Kontext in den Prompt injizieren
4. WHEN ein Benchmark-Bild keine GPS-EXIF-Daten enthält, THE BenchmarkRunner SHALL den Benchmark ohne Standort-Kontext für dieses Bild durchführen
5. THE BenchmarkRunner SHALL den aufgelösten Standort in den CSV-Ergebnissen als zusätzliche Spalte ausgeben

### Requirement 7: Konfigurierbarkeit

**User Story:** Als Benutzer möchte ich die Standort-Funktionalität konfigurieren können, damit ich sie bei Bedarf deaktivieren kann.

#### Acceptance Criteria

1. THE Config SHALL einen optionalen Konfigurationsabschnitt `location` in der YAML-Datei unterstützen
2. WHEN der `location`-Abschnitt in der Konfiguration fehlt, THE Config SHALL die Standort-Funktionalität als deaktiviert behandeln
3. WHEN der `location`-Abschnitt vorhanden ist, THE Config SHALL die Einstellung `enabled` (Boolean) auswerten
4. WHEN `location.enabled` auf `false` gesetzt ist, THE BatchProcessor SHALL keine GPS-Daten lesen und keine Standort-Stichwörter hinzufügen
5. WHEN `location.enabled` auf `true` gesetzt ist und keine GPS-Daten für ein Foto verfügbar sind, THE BatchProcessor SHALL das Foto ohne Standort-Stichwörter verarbeiten

### Requirement 8: Standort-Datenmodell

**User Story:** Als Entwickler möchte ich eine klare Datenstruktur für Standortinformationen, damit die Standortdaten konsistent im gesamten System verwendet werden.

#### Acceptance Criteria

1. THE Standort_Daten SHALL die Felder stadt (str), region (str), land (str), breitengrad (float) und laengengrad (float) enthalten
2. THE Standort_Daten SHALL als unveränderliche Datenklasse (frozen dataclass) implementiert werden
3. FOR ALL Standort_Daten-Instanzen, THE Standort_Daten SHALL sicherstellen, dass breitengrad zwischen -90.0 und 90.0 liegt und laengengrad zwischen -180.0 und 180.0 liegt
4. THE Standort_Daten SHALL eine Methode `als_stichwort_liste` bereitstellen, die nicht-leere Felder (stadt, region, land) als Liste von Zeichenketten zurückgibt
5. FOR ALL Standort_Daten-Instanzen, THE Methode `als_stichwort_liste` SHALL eine Liste zurückgeben, deren Länge zwischen 0 und 3 liegt
