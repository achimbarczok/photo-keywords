# 📷 Photo Keywords

> Automatic AI-powered keyword tagging for Adobe Lightroom Classic photos using local LLMs via Ollama. Fully offline — no cloud uploads, no external APIs.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-230%2B-green.svg)]()

**English** | 🌐 [Deutsch](README.de.md)

---

## ✨ What it does

Got thousands of photos in Lightroom without keywords? This tool analyzes your photos with a local vision model and writes descriptive keywords directly into the image files. Lightroom then reads them in — instant searchability.

**Example output for a photo taken in Chicago:**
```
Stadt, Chicago, Illinois, US, Wolkenkratzer, Glasfassade, Skyline, Moderne Architektur
```

## 🚀 Features

| Feature | Description |
|---------|-------------|
| **AI Image Analysis** | Local vision models (Gemma4, LLaVA, etc.) generate descriptive keywords |
| **Photo Classification** | Two-stage process: categorize first (Landscape, Portrait, Urban, etc.), then analyze with specialized prompt |
| **Location Keywords** | GPS from EXIF → offline reverse geocoding → city, region, country as keywords |
| **RAW Support** | CR2, NEF, TIFF auto-converted for analysis; keywords written to original file |
| **Response Validation** | Automatic quality checks with retry mechanism |
| **Error Tracking** | Failed files are remembered and skipped in future runs |
| **Benchmark Mode** | Compare models side-by-side with CSV output |
| **GPS Report** | See which photos have GPS data and which don't |
| **Progress Estimation** | Time remaining and ETA during processing |

## 📋 Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com/)** with a vision model:
  ```bash
  ollama pull gemma4:e4b
  ```
- **[ExifTool](https://exiftool.org/)** for writing keywords to image files
- **Adobe Lightroom Classic** catalog (.lrcat file)

## 🛠️ Installation

```bash
git clone https://github.com/achimbarczok/photo-keywords.git
cd photo-keywords
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt

# Optional: location keywords (offline reverse geocoding)
pip install reverse_geocoder
```

## ⚡ Quick Start

1. Create a `config.yaml`:

```yaml
catalog_path: "C:/path/to/your/Lightroom Catalog.lrcat"
model_name: "gemma4:e4b"
ollama_endpoint: "http://localhost:11434"
batch_size: 10
exiftool_path: "C:/Program Files/exiftool/exiftool.exe"
tracking_db_path: "./tracking.db"
log_file_path: "./keyword_generator.log"

prompt_template: >
  Analyze this photo and provide descriptive keywords for photo cataloging.
  Return ONLY a comma-separated list of keywords. No explanations.
```

2. Run:

```bash
python -m photo_keywords --config config.yaml
```

3. In Lightroom: Select photos → Metadata → *Read Metadata from File*

## 📖 Commands

### `keywords` (default)

```bash
# Process next batch
python -m photo_keywords --config config.yaml

# Retry previously failed photos
python -m photo_keywords --config config.yaml --retry-errors

# Benchmark: compare models
python -m photo_keywords --config benchmark_config.yaml --benchmark ./testbilder/
```

### `gps-report`

Shows which photos have GPS data — useful for deciding where to import GPX tracks.

```bash
python -m photo_keywords gps-report --config config.yaml
python -m photo_keywords gps-report --config config.yaml --month 2024-08
```

### `errors`

```bash
python -m photo_keywords errors --config config.yaml
python -m photo_keywords errors --config config.yaml --by-type
```

## ⚙️ Configuration

<details>
<summary><strong>Full config with all options</strong></summary>

```yaml
# Required
catalog_path: "path/to/catalog.lrcat"
model_name: "gemma4:e4b"

# Optional
ollama_endpoint: "http://localhost:11434"
batch_size: 50
exiftool_path: null   # null = find in PATH
tracking_db_path: "./tracking.db"
log_file_path: "./keyword_generator.log"

prompt_template: >
  Analyze this photo and provide descriptive keywords.
  Return ONLY a comma-separated list. No explanations.

# Location (requires: pip install reverse_geocoder)
location:
  enabled: true

# Classification (optional — enables two-stage analysis)
classification:
  model: "gemma4:e4b"
  prompt: >
    Classify this photo into exactly ONE category.
    Reply with ONLY the category name.
    Categories: Landscape, Portrait, Urban, Interior, Document, Food, Animals, Garden, Museum, Event, Other

  base_prompt: >
    You are a professional photo analyst. Analyze this photo and provide
    descriptive keywords for photo cataloging.
    Return ONLY a comma-separated list. No explanations.

  categories:
    Landschaft:
      prompt: "Focus on: weather, time of day, vegetation, terrain, season."
    Porträt:
      prompt: "Focus on: people, expressions, clothing, pose, background."
    Stadt:
      prompt: "Focus on: building type, architecture style, landmarks, street scene."
    Innenraum:
      prompt: "Focus on: room type, furniture, lighting, atmosphere."
    Dokument:
      prompt: "Focus on: document type, text content, language, format."
    Essen:
      prompt: "Focus on: dish, ingredients, cuisine, presentation."
    Tiere:
      prompt: "Focus on: animal species, habitat, behavior."
    Garten:
      prompt: "Focus on: plant species, flowers, garden design."
    Museum:
      prompt: "Focus on: exhibit, era, material, historical context."
    Veranstaltung:
      prompt: "Focus on: event type, occasion, people, venue."
    Sonstiges:
      prompt: "Describe everything you see: objects, materials, colors."

# Benchmark
benchmark_models:
  - "gemma4:e4b"
benchmark_output_csv: "./benchmark_results/benchmark_results.csv"
```

</details>

## 🔒 Safety

- Lightroom catalog is opened **read-only** (SQLite `?mode=ro`)
- Keywords are **only added**, never overwritten or deleted
- All processing runs **locally** — no data leaves your machine
- Failed files are tracked and skipped automatically

## 📁 Supported Formats

| Format | Analysis | Write Keywords |
|--------|:--------:|:--------------:|
| JPEG | ✅ direct | ✅ direct |
| PNG | ✅ direct | ✅ direct |
| DNG | ✅ direct | ✅ direct |
| TIFF | ✅ auto-convert | ✅ direct |
| CR2/CR3/NEF/ARW | ✅ auto-convert* | ✅ direct |
| Video (MP4, MOV, etc.) | ❌ excluded | — |
| PSD | ❌ excluded | — |

*RAW conversion requires Pillow. Some formats may need `rawpy` additionally.

## 🏗️ Architecture

```
Lightroom Catalog (.lrcat, read-only)
        │
   KatalogLeser ──── read photo entries (excluding video/PSD)
        │
 VerarbeitungsTracker ── filter processed + failed
        │
   GpsLeser ──── GPS from EXIF / catalog (optional)
        │
 StandortResolver ── reverse geocoding → city, region, country (optional)
        │
 KlassifikationsRouter ── classify → specialized prompt (optional)
        │
   OllamaClient ──── image + prompt → AI keywords (auto-converts RAW)
        │
 AntwortValidator ── quality check + retry (optional)
        │
 BatchProcessor ──── merge location + category + AI keywords
        │
 StichwortSchreiber ── write IPTC/XMP via ExifTool (UTF-8)
        │
   Tracking-DB ──── store: file + model + timestamp
```

## 🧪 Tests

```bash
python -m pytest tests/ -v                    # All 230+ tests
python -m pytest tests/ -v -k "property"      # Property-based tests (Hypothesis)
python -m pytest tests/ -v -k "integration"   # Integration tests
```

## 💡 Tips

- Start with `batch_size: 5-10` for testing, increase later
- Changing `model_name` re-processes all photos (existing keywords are preserved)
- Lightroom can stay open — the catalog is read-only
- After processing: select all → Metadata → "Read Metadata from File"
- Delete `tracking.db` to reprocess everything from scratch

## 🤖 Built with Kiro

This project was developed using [Kiro](https://kiro.dev), an AI-powered IDE. Development followed the Spec-Driven Development methodology:

1. Requirements as user stories with acceptance criteria
2. Technical design with correctness properties
3. Implementation plan with referenced requirements
4. Property-based tests (Hypothesis) for verification

Spec documents are in `.kiro/specs/`.

## 📄 License

[MIT](LICENSE)
