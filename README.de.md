# 📷 Photo Keywords

> Automatische KI-gestützte Stichwort-Vergabe für Adobe Lightroom Classic Fotos über lokale LLMs via Ollama. Vollständig offline — kein Cloud-Upload, keine externen APIs.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-230%2B-green.svg)]()

🌐 [English](README.md) | **Deutsch**

---

## ✨ Was es macht

Tausende Fotos in Lightroom ohne Stichwörter? Dieses Tool analysiert deine Fotos mit einem lokalen Vision-Modell und schreibt beschreibende Stichwörter direkt in die Bilddateien. Lightroom liest sie dann ein — sofortige Durchsuchbarkeit.

**Beispielausgabe für ein Foto aus Chicago:**
```
Stadt, Chicago, Illinois, US, Wolkenkratzer, Glasfassade, Skyline, Moderne Architektur
```

## 🚀 Features

| Feature | Beschreibung |
|---------|-------------|
| **KI-Bildanalyse** | Lokale Vision-Modelle (Gemma4, LLaVA, etc.) generieren beschreibende Stichwörter |
| **Foto-Klassifikation** | Zwei-Stufen-Prozess: erst kategorisieren (Landschaft, Porträt, Stadt, etc.), dann mit spezialisiertem Prompt analysieren |
| **Standort-Stichwörter** | GPS aus EXIF → Offline-Reverse-Geocoding → Stadt, Region, Land als Stichwörter |
| **RAW-Unterstützung** | CR2, NEF, TIFF werden automatisch konvertiert; Stichwörter werden in die Originaldatei geschrieben |
| **Antwort-Validierung** | Automatische Qualitätsprüfung mit Retry-Mechanismus |
| **Fehler-Tracking** | Fehlgeschlagene Dateien werden gespeichert und bei zukünftigen Läufen übersprungen |
| **Benchmark-Modus** | Modelle nebeneinander vergleichen mit CSV-Ausgabe |
| **GPS-Bericht** | Zeigt welche Fotos GPS-Daten haben und welche nicht |
| **Fortschrittsanzeige** | Verbleibende Zeit und ETA während der Verarbeitung |

## 📋 Voraussetzungen

- **Python 3.10+**
- **[Ollama](https://ollama.com/)** mit einem Vision-Modell:
  ```bash
  ollama pull gemma4:e4b
  ```
- **[ExifTool](https://exiftool.org/)** zum Schreiben der Stichwörter in Bilddateien
- **Adobe Lightroom Classic** Katalog (.lrcat-Datei)

## 🛠️ Installation

```bash
git clone https://github.com/achimbarczok/photo-keywords.git
cd photo-keywords
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt

# Optional: Standort-Stichwörter (Offline-Reverse-Geocoding)
pip install reverse_geocoder
```

## ⚡ Schnellstart

1. Erstelle eine `config.yaml`:

```yaml
catalog_path: "C:/Pfad/zu/deinem/Lightroom Catalog.lrcat"
model_name: "gemma4:e4b"
ollama_endpoint: "http://localhost:11434"
batch_size: 10
exiftool_path: "C:/Program Files/exiftool/exiftool.exe"
tracking_db_path: "./tracking.db"
log_file_path: "./keyword_generator.log"

prompt_template: >
  Analysiere dieses Foto und liefere beschreibende Stichwörter für die Foto-Katalogisierung.
  Gib NUR eine kommagetrennte Liste von Stichwörtern zurück. Keine Erklärungen.
```

2. Ausführen:

```bash
python -m photo_keywords --config config.yaml
```

3. In Lightroom: Fotos auswählen → Metadaten → *Metadaten aus Datei lesen*

## 📖 Befehle

### `keywords` (Standard)

```bash
# Nächsten Batch verarbeiten
python -m photo_keywords --config config.yaml

# Zuvor fehlgeschlagene Fotos erneut versuchen
python -m photo_keywords --config config.yaml --retry-errors

# Benchmark: Modelle vergleichen
python -m photo_keywords --config benchmark_config.yaml --benchmark ./testbilder/
```

### `gps-report`

Zeigt welche Fotos GPS-Daten haben — nützlich um zu entscheiden, wo GPX-Tracks importiert werden sollten.

```bash
python -m photo_keywords gps-report --config config.yaml
python -m photo_keywords gps-report --config config.yaml --month 2024-08
```

### `errors`

```bash
python -m photo_keywords errors --config config.yaml
python -m photo_keywords errors --config config.yaml --by-type
```

## ⚙️ Konfiguration

<details>
<summary><strong>Vollständige Konfiguration mit allen Optionen</strong></summary>

```yaml
# Erforderlich
catalog_path: "pfad/zum/katalog.lrcat"
model_name: "gemma4:e4b"

# Optional
ollama_endpoint: "http://localhost:11434"
batch_size: 50
exiftool_path: null   # null = in PATH suchen
tracking_db_path: "./tracking.db"
log_file_path: "./keyword_generator.log"

prompt_template: >
  Analysiere dieses Foto und liefere beschreibende Stichwörter.
  Gib NUR eine kommagetrennte Liste zurück. Keine Erklärungen.

# Standort (erfordert: pip install reverse_geocoder)
location:
  enabled: true

# Klassifikation (optional — aktiviert Zwei-Stufen-Analyse)
classification:
  model: "gemma4:e4b"
  prompt: >
    Klassifiziere dieses Foto in genau EINE Kategorie.
    Antworte NUR mit dem Kategorienamen.
    Kategorien: Landschaft, Porträt, Stadt, Innenraum, Dokument, Essen, Tiere, Garten, Museum, Veranstaltung, Sonstiges

  base_prompt: >
    Du bist ein professioneller Foto-Analyst. Analysiere dieses Foto und liefere
    beschreibende Stichwörter für die Foto-Katalogisierung.
    Gib NUR eine kommagetrennte Liste zurück. Keine Erklärungen.

  categories:
    Landschaft:
      prompt: "Fokus auf: Wetter, Tageszeit, Vegetation, Gelände, Jahreszeit."
    Porträt:
      prompt: "Fokus auf: Personen, Ausdruck, Kleidung, Pose, Hintergrund."
    Stadt:
      prompt: "Fokus auf: Gebäudetyp, Architekturstil, Wahrzeichen, Straßenszene."
    Innenraum:
      prompt: "Fokus auf: Raumtyp, Möbel, Beleuchtung, Atmosphäre."
    Dokument:
      prompt: "Fokus auf: Dokumenttyp, Textinhalt, Sprache, Format."
    Essen:
      prompt: "Fokus auf: Gericht, Zutaten, Küche, Präsentation."
    Tiere:
      prompt: "Fokus auf: Tierart, Lebensraum, Verhalten."
    Garten:
      prompt: "Fokus auf: Pflanzenarten, Blumen, Gartengestaltung."
    Museum:
      prompt: "Fokus auf: Exponat, Epoche, Material, historischer Kontext."
    Veranstaltung:
      prompt: "Fokus auf: Veranstaltungstyp, Anlass, Personen, Veranstaltungsort."
    Sonstiges:
      prompt: "Beschreibe alles was du siehst: Objekte, Materialien, Farben."

# Benchmark
benchmark_models:
  - "gemma4:e4b"
benchmark_output_csv: "./benchmark_results/benchmark_results.csv"
```

</details>

## 🔒 Sicherheit

- Lightroom-Katalog wird **nur lesend** geöffnet (SQLite `?mode=ro`)
- Stichwörter werden **nur hinzugefügt**, nie überschrieben oder gelöscht
- Alle Verarbeitung läuft **lokal** — keine Daten verlassen deinen Rechner
- Fehlgeschlagene Dateien werden getrackt und automatisch übersprungen

## 📁 Unterstützte Formate

| Format | Analyse | Stichwörter schreiben |
|--------|:--------:|:---------------------:|
| JPEG | ✅ direkt | ✅ direkt |
| PNG | ✅ direkt | ✅ direkt |
| DNG | ✅ direkt | ✅ direkt |
| TIFF | ✅ Auto-Konvertierung | ✅ direkt |
| CR2/CR3/NEF/ARW | ✅ Auto-Konvertierung* | ✅ direkt |
| Video (MP4, MOV, etc.) | ❌ ausgeschlossen | — |
| PSD | ❌ ausgeschlossen | — |

*RAW-Konvertierung erfordert Pillow. Einige Formate benötigen zusätzlich `rawpy`.

## 🏗️ Architektur

```
Lightroom-Katalog (.lrcat, nur lesend)
        │
   KatalogLeser ──── Foto-Einträge lesen (ohne Video/PSD)
        │
 VerarbeitungsTracker ── verarbeitete + fehlgeschlagene filtern
        │
   GpsLeser ──── GPS aus EXIF / Katalog (optional)
        │
 StandortResolver ── Reverse-Geocoding → Stadt, Region, Land (optional)
        │
 KlassifikationsRouter ── klassifizieren → spezialisierter Prompt (optional)
        │
   OllamaClient ──── Bild + Prompt → KI-Stichwörter (konvertiert RAW automatisch)
        │
 AntwortValidator ── Qualitätsprüfung + Retry (optional)
        │
 BatchProcessor ──── Standort + Kategorie + KI-Stichwörter zusammenführen
        │
 StichwortSchreiber ── IPTC/XMP via ExifTool schreiben (UTF-8)
        │
   Tracking-DB ──── speichern: Datei + Modell + Zeitstempel
```

## 🧪 Tests

```bash
python -m pytest tests/ -v                    # Alle 230+ Tests
python -m pytest tests/ -v -k "property"      # Property-basierte Tests (Hypothesis)
python -m pytest tests/ -v -k "integration"   # Integrationstests
```

## 💡 Tipps

- Starte mit `batch_size: 5-10` zum Testen, später erhöhen
- Änderung von `model_name` verarbeitet alle Fotos neu (bestehende Stichwörter bleiben erhalten)
- Lightroom kann offen bleiben — der Katalog wird nur gelesen
- Nach der Verarbeitung: alle auswählen → Metadaten → „Metadaten aus Datei lesen"
- `tracking.db` löschen um alles von vorne zu verarbeiten

## 🤖 Entwickelt mit Kiro

Dieses Projekt wurde mit [Kiro](https://kiro.dev) entwickelt, einer KI-gestützten IDE. Die Entwicklung folgte der Spec-Driven Development Methodik:

1. Anforderungen als User Stories mit Akzeptanzkriterien
2. Technisches Design mit Korrektheitseigenschaften
3. Implementierungsplan mit referenzierten Anforderungen
4. Property-basierte Tests (Hypothesis) zur Verifikation

Spec-Dokumente befinden sich in `.kiro/specs/`.

## 📄 Lizenz

[MIT](LICENSE)
