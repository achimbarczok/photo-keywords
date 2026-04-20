# Lightroom Ollama Keywords

Automatische Stichwort-Vergabe für Fotos in Adobe Lightroom Classic über lokal laufende KI-Modelle (Ollama). Alles läuft offline — kein Cloud-Upload, keine externen APIs.

## Features

- **KI-Bildanalyse** — Multimodale LLMs (Gemma4, LLaVA, Moondream) analysieren Fotos und generieren deutsche Stichwörter
- **Foto-Klassifikation** — Zwei-Stufen-Prozess: Foto wird erst kategorisiert (Landschaft, Porträt, Architektur, etc.), dann mit spezialisiertem Prompt analysiert
- **Antwort-Validierung** — Automatische Qualitätsprüfung der KI-Antworten mit Retry-Mechanismus
- **Standort-Stichwörter** — GPS aus EXIF/Lightroom-Katalog → Offline-Reverse-Geocoding → Stadt, Region, Land als Stichwörter
- **Benchmark-Modus** — Modellvergleich mit CSV-Ausgabe (Antwortzeiten, Keywords, Klassifikation, Standort)
- **Tracking** — Modellspezifisches Tracking verhindert doppelte Verarbeitung

## Voraussetzungen

- Python 3.10+
- [Ollama](https://ollama.com/) mit einem Vision-Modell (z.B. `ollama pull gemma4:e4b`)
- [ExifTool](https://exiftool.org/) zum Schreiben der Keywords
- Adobe Lightroom Classic (Katalog wird nur gelesen)
- Optional: `reverse_geocoder` für Standort-Stichwörter (`pip install reverse_geocoder`)

## Installation

```bash
git clone https://github.com/DEIN-USERNAME/lightroom-ollama-keywords.git
cd lightroom-ollama-keywords
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Konfiguration

Erstelle eine `config.yaml` (wird von Git ignoriert):

```yaml
catalog_path: "C:/Users/DeinName/Lightroom/MeinKatalog.lrcat"
model_name: "gemma4:e4b"
ollama_endpoint: "http://localhost:11434"
batch_size: 10
exiftool_path: "C:/Program Files/exiftool/exiftool.exe"  # oder null für PATH

prompt_template: >
  Du bist ein professioneller Foto-Analyst. Analysiere dieses Foto und
  liefere beschreibende deutsche Stichwörter. Antworte NUR mit einer
  kommaseparierten Liste. Keine Erklärungen.

tracking_db_path: "./tracking.db"
log_file_path: "./keyword_generator.log"

# Standort-Funktionalität (optional, benötigt reverse_geocoder)
location:
  enabled: true

# Klassifikation (optional — ohne diesen Abschnitt wird ein Einzelprompt verwendet)
classification:
  model: "gemma4:e4b"
  prompt: >
    Classify this photo into exactly ONE of these categories.
    Reply with ONLY the category name, nothing else.
    Categories: Landscape, Portrait, Architecture, Document, Food, Animals, Garden, Museum, Event, Other
  categories:
    Landschaft:
      prompt: >
        Analysiere dieses Foto. Fokus auf: Wetter, Tageszeit, Vegetation, Gelände, Jahreszeit.
        Antworte NUR mit kommaseparierter Liste deutscher Stichwörter.
    Porträt:
      prompt: >
        Analysiere dieses Foto. Fokus auf: Personen, Gesichtsausdrücke, Kleidung, Pose.
        Antworte NUR mit kommaseparierter Liste deutscher Stichwörter.
    # ... weitere Kategorien analog
```

## Verwendung

### Stichwörter generieren

```bash
python -m lightroom_ollama_keywords --config config.yaml
```

Verarbeitet bis zu `batch_size` Fotos. Beim nächsten Lauf werden automatisch die nächsten unverarbeiteten Fotos genommen.

Danach in Lightroom: Fotos auswählen → Metadaten → *Metadaten aus Datei lesen*

### Benchmark — Modelle vergleichen

```bash
python -m lightroom_ollama_keywords --config benchmark_config.yaml --benchmark ./testbilder/
```

Erzeugt eine CSV in `benchmark_results/` mit Keywords, Antwortzeiten, Kategorien und Standort pro Modell.

## Verarbeitungs-Pipeline

```
Lightroom-Katalog (.lrcat, read-only)
        │
   KatalogLeser ──── Foto-Einträge lesen
        │
 VerarbeitungsTracker ── bereits verarbeitete filtern
        │
   GpsLeser ──── GPS aus EXIF / Katalog (optional)
        │
 StandortResolver ── Reverse-Geocoding → Stadt, Region, Land (optional)
        │
 KlassifikationsRouter ── Kategorie bestimmen → spezialisierter Prompt (optional)
        │
   OllamaClient ──── Bild + Prompt → KI-Stichwörter
        │
 AntwortValidator ── Qualitätsprüfung + Retry (optional)
        │
 BatchProcessor ──── Standort + KI-Keywords zusammenführen
        │
 StichwortSchreiber ── IPTC/XMP via ExifTool (UTF-8)
        │
   Tracking-DB ──── Foto + Modell + Zeitstempel speichern
```

## Projektstruktur

```
lightroom-ollama-keywords/
├── config.yaml                          # Eigene Config (git-ignoriert)
├── benchmark_config.yaml                # Benchmark-Konfiguration
├── requirements.txt                     # Python-Abhängigkeiten
├── testbilder/                          # Testbilder für Benchmark
├── benchmark_results/                   # CSV-Ergebnisse (git-ignoriert)
│
├── lightroom_ollama_keywords/           # Hauptpaket
│   ├── main.py                          # CLI-Einstiegspunkt
│   ├── config_loader.py                 # YAML-Konfiguration
│   ├── katalog_leser.py                 # Lightroom-Katalog (SQLite)
│   ├── verarbeitungs_tracker.py         # Tracking-Datenbank
│   ├── ollama_client.py                 # Ollama REST API
│   ├── klassifikations_router.py        # Foto-Klassifikation + Routing
│   ├── antwort_validator.py             # Antwort-Validierung + Retry
│   ├── batch_processor.py              # Batch-Verarbeitung + Standort
│   ├── gps_leser.py                     # GPS aus EXIF / Katalog
│   ├── standort_resolver.py             # Offline-Reverse-Geocoding
│   ├── stichwort_schreiber.py           # IPTC/XMP via ExifTool
│   ├── benchmark_runner.py             # Benchmark-Modus
│   ├── models.py                        # Datenklassen
│   └── errors.py                        # Fehlerklassen
│
├── tests/                               # 250+ Tests (pytest + Hypothesis)
│
└── .kiro/                               # Kiro Spec-Driven Development
    ├── steering/                        # Projekt-Kontext für Kiro
    └── specs/                           # Requirements, Design, Tasks
        ├── lightroom-ollama-keywords/
        ├── photo-classification-router/
        ├── keyword-response-validation/
        ├── benchmark-prompt-tracking/
        └── location-based-keywords/
```

## Tests

```bash
python -m pytest tests/ -v                    # Alle Tests
python -m pytest tests/ -v -k "property"      # Nur Property-Tests (Hypothesis)
python -m pytest tests/ -v -k "integration"   # Nur Integrationstests
```

## Entwicklung mit Kiro

Dieses Projekt wurde mit [Kiro](https://kiro.dev) entwickelt — einer KI-gestützten IDE. Die Entwicklung folgte dem Spec-Driven-Development-Ansatz:

1. Requirements als User Stories mit Akzeptanzkriterien
2. Technisches Design mit Correctness Properties
3. Implementierungsplan mit Tasks
4. Property-basierte Tests (Hypothesis) zur Verifikation

Die Spec-Dokumente liegen in `.kiro/specs/`.

## Lizenz

Privates Projekt.
