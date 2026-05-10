# Photo Keywords

Automatische Stichwort-Vergabe für Fotos in Adobe Lightroom Classic über lokal laufende KI-Modelle (Ollama). Alles läuft offline auf deinem Rechner — kein Cloud-Upload, keine externen APIs, volle Kontrolle über deine Daten.

## Was macht dieses Tool?

Du hast tausende Fotos in Lightroom ohne Stichwörter? Dieses Tool analysiert deine Fotos mit einem lokalen KI-Modell und schreibt automatisch passende deutsche Stichwörter in die Bilddateien. Danach liest Lightroom die neuen Stichwörter ein und du kannst sofort danach suchen.

**Beispiel-Output für ein Foto aus Chicago:**
```
Stadt, Chicago, Illinois, US, Wolkenkratzer, Glasfassade, Skyline, Moderne Architektur, Hochhäuser
```

## Features

- **KI-Bildanalyse** — Multimodale Vision-Modelle (Gemma4, LLaVA, etc.) analysieren Fotos und generieren deutsche Stichwörter
- **Foto-Klassifikation** — Zwei-Stufen-Prozess: Foto wird erst kategorisiert (Landschaft, Porträt, Stadt, Innenraum, etc.), dann mit spezialisiertem Prompt analysiert
- **Standort-Stichwörter** — GPS aus EXIF/Lightroom-Katalog → Offline-Reverse-Geocoding → Stadt, Region, Land als Stichwörter + Kontext für bessere KI-Keywords
- **RAW-Support** — CR2, NEF, TIFF und andere Formate werden automatisch konvertiert
- **Antwort-Validierung** — Automatische Qualitätsprüfung der KI-Antworten mit Retry-Mechanismus
- **Fehler-Tracking** — Fehlgeschlagene Dateien werden gespeichert und bei zukünftigen Läufen übersprungen
- **Benchmark-Modus** — Modellvergleich mit CSV-Ausgabe (Antwortzeiten, Keywords, Klassifikation)
- **GPS-Report** — Übersicht welche Fotos GPS-Daten haben und welche nicht
- **Batch-Verarbeitung** — Konfigurierbare Batch-Größe, Fortschrittsanzeige mit Zeitschätzung

## Voraussetzungen

- **Python 3.10+**
- **[Ollama](https://ollama.com/)** — lokal installiert, mit einem Vision-Modell:
  ```bash
  ollama pull gemma4:e4b
  ```
- **[ExifTool](https://exiftool.org/)** — zum Schreiben der Keywords in die Bilddateien
- **Adobe Lightroom Classic** — der Katalog (.lrcat) wird nur gelesen, nie beschrieben
- **Optional:** `reverse_geocoder` für Standort-Stichwörter

## Installation

```bash
git clone https://github.com/achimbarczok/photo-keywords.git
cd photo-keywords
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt

# Optional: Standort-Funktionalität
pip install reverse_geocoder
```

## Schnellstart

1. Erstelle eine `config.yaml` (wird von Git ignoriert):

```yaml
catalog_path: "C:/Pfad/zu/deinem/Lightroom Catalog.lrcat"
model_name: "gemma4:e4b"
ollama_endpoint: "http://localhost:11434"
batch_size: 10
exiftool_path: "C:/Program Files/exiftool/exiftool.exe"
tracking_db_path: "./tracking.db"
log_file_path: "./keyword_generator.log"

prompt_template: >
  Du bist ein professioneller Foto-Analyst. Analysiere dieses Foto und liefere
  beschreibende deutsche Stichwörter. Antworte NUR mit einer kommaseparierten
  Liste. Keine Erklärungen.
```

2. Starte die Verarbeitung:

```bash
python -m photo_keywords --config config.yaml
```

3. In Lightroom: Fotos auswählen → Metadaten → *Metadaten aus Datei lesen*

## Befehle

### Keywords generieren

```bash
# Nächsten Batch verarbeiten
python -m photo_keywords --config config.yaml

# Fehlgeschlagene Fotos erneut versuchen
python -m photo_keywords --config config.yaml --retry-errors

# Benchmark: Modelle vergleichen
python -m photo_keywords --config benchmark_config.yaml --benchmark ./testbilder/
```

### GPS-Report

Zeigt welche Fotos GPS-Daten haben und welche nicht — hilfreich um zu entscheiden, für welche Tage man GPX-Tracks in Lightroom importieren sollte.

```bash
# Alle Fotos
python -m photo_keywords gps-report --config config.yaml

# Nur ein bestimmter Tag
python -m photo_keywords gps-report --config config.yaml --day 2024-08-26

# Nur ein bestimmter Monat
python -m photo_keywords gps-report --config config.yaml --month 2024-08
```

### Fehler anzeigen

```bash
# Alle Fehler auflisten
python -m photo_keywords errors --config config.yaml

# Fehler nach Dateityp gruppiert
python -m photo_keywords errors --config config.yaml --by-type
```

## Konfiguration

### Vollständige Config mit allen Optionen

```yaml
# Pflicht
catalog_path: "C:/Pfad/zum/Katalog.lrcat"
model_name: "gemma4:e4b"

# Optional (Standardwerte gezeigt)
ollama_endpoint: "http://localhost:11434"
batch_size: 50
exiftool_path: null   # null = ExifTool im PATH suchen
tracking_db_path: "./tracking.db"
log_file_path: "./keyword_generator.log"

prompt_template: >
  Analysiere dieses Foto und liefere beschreibende deutsche Stichwörter.
  Antworte NUR mit einer kommaseparierten Liste. Keine Erklärungen.

# Standort-Funktionalität (optional, benötigt reverse_geocoder)
location:
  enabled: true

# Klassifikation (optional — ohne diesen Abschnitt wird ein Einzelprompt verwendet)
classification:
  model: "gemma4:e4b"
  prompt: >
    Classify this photo into exactly ONE of these categories.
    Reply with ONLY the category name, nothing else.
    Categories: Landscape, Portrait, Urban, Interior, Document, Food, Animals, Garden, Museum, Event, Other

  # Basis-Prompt: wird allen Kategorie-Prompts vorangestellt
  base_prompt: >
    Du bist ein professioneller Foto-Analyst. Analysiere dieses Foto und liefere
    beschreibende deutsche Stichwörter für die Foto-Katalogisierung.
    Antworte NUR mit einer kommaseparierten Liste. Keine Erklärungen.

  categories:
    Landschaft:
      prompt: "Fokussiere auf: Wetter, Tageszeit, Vegetation, Gelände, Jahreszeit."
    Porträt:
      prompt: "Fokussiere auf: Personen, Gesichtsausdrücke, Kleidung, Pose."
    Stadt:
      prompt: "Fokussiere auf: Gebäudetyp, Architekturstil, Straßenszene, Skyline."
    Innenraum:
      prompt: "Fokussiere auf: Raumtyp, Einrichtung, Möbel, Atmosphäre."
    Dokument:
      prompt: "Fokussiere auf: Dokumenttyp, Textinhalte, Sprache, Format."
    Essen:
      prompt: "Fokussiere auf: Gericht, Zutaten, Küche, Präsentation."
    Tiere:
      prompt: "Fokussiere auf: Tierart, Lebensraum, Verhalten."
    Garten:
      prompt: "Fokussiere auf: Pflanzenarten, Blüten, Gartengestaltung."
    Museum:
      prompt: "Fokussiere auf: Ausstellungsstück, Epoche, Material."
    Veranstaltung:
      prompt: "Fokussiere auf: Art der Veranstaltung, Anlass, Personen."
    Sonstiges:
      prompt: "Beschreibe alles was du siehst: Objekte, Materialien, Farben."

# Benchmark-Modus
benchmark_models:
  - "gemma4:e4b"
benchmark_output_csv: "./benchmark_results/benchmark_results.csv"
```

### Wie die Klassifikation funktioniert

Wenn der `classification`-Abschnitt vorhanden ist, wird jedes Foto in zwei Schritten verarbeitet:

1. **Klassifikation** — Das Modell ordnet das Foto einer Kategorie zu (Landschaft, Porträt, Stadt, etc.)
2. **Spezialisierte Analyse** — Der `base_prompt` + der kategoriespezifische `prompt` werden zusammengesetzt und an das Modell geschickt

Ohne `classification`-Abschnitt wird einfach der `prompt_template` für alle Fotos verwendet.

### Wie der Standort funktioniert

Wenn `location.enabled: true`:

1. GPS-Koordinaten werden aus EXIF-Daten oder dem Lightroom-Katalog gelesen (Katalog hat Vorrang)
2. Koordinaten werden offline per `reverse_geocoder` in Ortsnamen aufgelöst
3. Stadt, Region und Land werden als separate Stichwörter hinzugefügt
4. Der Standort wird als Kontext-Prefix in den Prompt eingefügt (z.B. "Dieses Foto wurde in Berlin, DE aufgenommen."), damit das Modell kontextbezogenere Keywords generiert

## Unterstützte Dateiformate

| Format | Analyse | Keywords schreiben |
|--------|---------|-------------------|
| JPEG (.jpg, .jpeg) | ✅ direkt | ✅ direkt |
| PNG (.png) | ✅ direkt | ✅ direkt |
| DNG (.dng) | ✅ direkt | ✅ direkt |
| TIFF (.tiff, .tif) | ✅ via Konvertierung | ✅ direkt |
| CR2 (.cr2) | ✅ via Konvertierung* | ✅ direkt |
| NEF (.nef) | ✅ via Konvertierung* | ✅ direkt |
| Video (.mp4, .mov, etc.) | ❌ ausgeschlossen | — |
| PSD (.psd) | ❌ ausgeschlossen | — |

*RAW-Konvertierung benötigt Pillow. Manche RAW-Formate brauchen zusätzlich `rawpy`.

## Sicherheit

- Der Lightroom-Katalog wird **nur gelesen** (SQLite read-only Modus)
- Keywords werden **nur hinzugefügt**, nie überschrieben oder gelöscht
- Alle Verarbeitung läuft **lokal** — keine Daten verlassen deinen Rechner
- Die `tracking.db` speichert nur Dateipfade und Modellnamen, keine Bildinhalte

## Verarbeitungs-Pipeline

```
Lightroom-Katalog (.lrcat, read-only)
        │
   KatalogLeser ──── Foto-Einträge lesen (ohne Video/PSD)
        │
 VerarbeitungsTracker ── bereits verarbeitete + fehlgeschlagene filtern
        │
   GpsLeser ──── GPS aus EXIF / Katalog (optional)
        │
 StandortResolver ── Reverse-Geocoding → Stadt, Region, Land (optional)
        │
 KlassifikationsRouter ── Kategorie bestimmen → spezialisierter Prompt (optional)
        │
   OllamaClient ──── Bild + Prompt → KI-Stichwörter (mit auto-Konvertierung für RAW)
        │
 AntwortValidator ── Qualitätsprüfung + Retry (optional)
        │
 BatchProcessor ──── Standort + Kategorie + KI-Keywords zusammenführen
        │
 StichwortSchreiber ── IPTC/XMP via ExifTool (UTF-8 Argfile)
        │
   Tracking-DB ──── Foto + Modell + Zeitstempel speichern
```

## Projektstruktur

```
photo-keywords/
├── config.yaml                          # Eigene Config (git-ignoriert)
├── benchmark_config.yaml                # Benchmark-Konfiguration (Beispiel)
├── requirements.txt                     # Python-Abhängigkeiten
├── testbilder/                          # Eigene Testbilder (git-ignoriert)
├── benchmark_results/                   # CSV-Ergebnisse (git-ignoriert)
│
├── photo_keywords/                      # Hauptpaket
│   ├── main.py                          # CLI mit Subcommands
│   ├── config_loader.py                 # YAML-Konfiguration
│   ├── katalog_leser.py                 # Lightroom-Katalog (SQLite)
│   ├── verarbeitungs_tracker.py         # Tracking + Fehler-DB
│   ├── ollama_client.py                 # Ollama REST API + RAW-Konvertierung
│   ├── klassifikations_router.py        # Foto-Klassifikation + Routing
│   ├── antwort_validator.py             # Antwort-Validierung + Retry
│   ├── batch_processor.py              # Batch-Verarbeitung + Zeitschätzung
│   ├── gps_leser.py                     # GPS aus EXIF / Katalog
│   ├── standort_resolver.py             # Offline-Reverse-Geocoding
│   ├── gps_report.py                    # GPS-Bericht
│   ├── stichwort_schreiber.py           # IPTC/XMP via ExifTool
│   ├── benchmark_runner.py             # Benchmark-Modus
│   ├── models.py                        # Datenklassen
│   └── errors.py                        # Fehlerklassen
│
├── tests/                               # 230+ Tests (pytest + Hypothesis)
│
└── .kiro/                               # Kiro Spec-Driven Development
    ├── steering/                        # Projekt-Kontext
    └── specs/                           # Requirements, Design, Tasks
```

## Tests

```bash
python -m pytest tests/ -v                    # Alle Tests (230+)
python -m pytest tests/ -v -k "property"      # Nur Property-Tests (Hypothesis)
python -m pytest tests/ -v -k "integration"   # Nur Integrationstests
```

## Tipps

- **Batch-Größe**: Starte mit `batch_size: 5-10` zum Testen, dann hochsetzen
- **Modellwechsel**: Bei neuem `model_name` werden alle Fotos erneut verarbeitet (bestehende Keywords bleiben)
- **Lightroom offen lassen**: Der Katalog wird read-only geöffnet, Lightroom muss nicht geschlossen werden
- **Nach der Verarbeitung**: In Lightroom alle Fotos auswählen → Metadaten → "Metadaten aus Datei lesen"
- **Tracking zurücksetzen**: `tracking.db` löschen um alle Fotos erneut zu verarbeiten

## Entwicklung

Dieses Projekt wurde mit [Kiro](https://kiro.dev) entwickelt — einer KI-gestützten IDE. Die Entwicklung folgte dem Spec-Driven-Development-Ansatz:

1. Requirements als User Stories mit Akzeptanzkriterien
2. Technisches Design mit Correctness Properties
3. Implementierungsplan mit Tasks
4. Property-basierte Tests (Hypothesis) zur Verifikation

Die Spec-Dokumente liegen in `.kiro/specs/`.

## Lizenz

MIT License — siehe [LICENSE](LICENSE).
