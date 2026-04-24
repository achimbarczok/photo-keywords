---
inclusion: always
---

# Photo Keywords Generator — Projektkontext

## Überblick
Automatische Stichwort-Vergabe für Adobe Lightroom Classic über lokal laufende KI-Modelle (Ollama).
Alle Verarbeitung läuft offline — kein Cloud-Upload, keine externen APIs.

## Architektur
- **Sprache**: Python 3.10+, deutsche Bezeichner im Code
- **KI-Backend**: Ollama REST API (lokal), Vision-Modelle (gemma4, llava, etc.)
- **Metadaten**: ExifTool für IPTC/XMP-Keywords
- **Katalog**: Lightroom .lrcat (SQLite, read-only)
- **Konfiguration**: YAML-Dateien
- **Tests**: pytest + Hypothesis (Property-basierte Tests)

## Kernmodule
- `katalog_leser.py` — Lightroom-Katalog lesen (SQLite read-only)
- `ollama_client.py` — Ollama REST API, Bildanalyse, Antwort-Parsing
- `klassifikations_router.py` — Zwei-Stufen-Prozess: Klassifikation → spezialisierter Prompt
- `antwort_validator.py` — Validierung und Retry bei schlechten Antworten
- `batch_processor.py` — Batch-Verarbeitung mit GPS/Standort-Integration
- `stichwort_schreiber.py` — IPTC/XMP-Keywords via ExifTool (UTF-8 Argfile)
- `gps_leser.py` — GPS aus EXIF und Lightroom-Katalog
- `standort_resolver.py` — Offline-Reverse-Geocoding (reverse_geocoder)
- `benchmark_runner.py` — Modellvergleich mit CSV-Ausgabe
- `verarbeitungs_tracker.py` — Tracking-DB (SQLite)
- `gps_report.py` — GPS-Bericht: Fotos ohne GPS-Daten auflisten

## Konventionen
- Deutsche Bezeichner im Code (Klassen, Methoden, Variablen)
- Deutsche Docstrings
- Frozen Dataclasses für Datenmodelle
- Graceful Degradation bei GPS/Standort-Fehlern
- ExifTool-Schreibvorgänge über UTF-8 Argfiles (Windows-Kompatibilität)
- Property-basierte Tests mit Hypothesis (min. 100 Iterationen)

## Wichtige Abhängigkeiten
- `exifread` — EXIF-GPS lesen
- `reverse_geocoder` — Offline-Geocoding (optional)
- `PyExifTool` — ExifTool-Wrapper (nur zum Lesen)
- `requests` — Ollama API
- `pyyaml` — Konfiguration
- `hypothesis` — Property-basierte Tests
