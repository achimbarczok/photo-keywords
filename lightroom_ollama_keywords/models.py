"""Datenklassen für den Lightroom Ollama Keyword Generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass
class ValidierungsConfig:
    """Konfiguration für die Antwort-Validierung."""

    max_retries: int = 2
    wortanzahl_schwellenwert: float = 3.0
    einzeleintrag_schwellenwert: int = 4
    retry_prompt: str = (
        "Antworte ausschließlich mit einer komma-getrennten Liste von Stichwörtern. "
        "Keine Sätze, keine Erklärungen, keine Einleitungen. "
        "Nur Stichwörter, getrennt durch Kommas."
    )


@dataclass
class ValidierungsErgebnis:
    """Ergebnis einer Antwort-Validierung."""

    gueltig: bool
    grund: str | None = None


@dataclass(frozen=True)
class StandortDaten:
    """Aufgelöste Standortinformationen für ein Foto."""

    stadt: str
    region: str
    land: str
    breitengrad: float
    laengengrad: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.breitengrad <= 90.0):
            raise ValueError(
                f"Breitengrad muss zwischen -90 und 90 liegen: {self.breitengrad}"
            )
        if not (-180.0 <= self.laengengrad <= 180.0):
            raise ValueError(
                f"Längengrad muss zwischen -180 und 180 liegen: {self.laengengrad}"
            )

    def als_stichwort_liste(self) -> list[str]:
        """Gibt nicht-leere Felder (stadt, region, land) als Liste zurück."""
        return [f for f in (self.stadt, self.region, self.land) if f]


@dataclass
class StandortConfig:
    """Konfiguration für die Standort-Funktionalität."""

    enabled: bool = False


@dataclass
class Config:
    """Konfiguration für den Keyword Generator."""

    catalog_path: str
    ollama_endpoint: str
    model_name: str
    batch_size: int
    prompt_template: str
    tracking_db_path: str
    log_file_path: str
    exiftool_path: str | None
    benchmark_models: list[str]
    benchmark_output_csv: str
    klassifikation: KlassifikationsConfig | None = None
    validierung: ValidierungsConfig = field(default_factory=ValidierungsConfig)
    standort: StandortConfig = field(default_factory=StandortConfig)


@dataclass
class FotoEintrag:
    """Ein Foto-Eintrag aus dem Lightroom-Katalog."""

    image_id: int
    file_path: str


@dataclass
class VerarbeitungsEintrag:
    """Ein Eintrag in der Verarbeitungs-Tracking-Datenbank."""

    file_path: str
    model_name: str
    model_version: str
    timestamp: str  # ISO 8601


@dataclass
class BatchErgebnis:
    """Ergebnis einer Batch-Verarbeitung."""

    verarbeitet: int
    fehler: int
    dauer_sekunden: float
    fehler_details: list[str]


@dataclass
class BenchmarkErgebnis:
    """Ergebnis eines einzelnen Benchmark-Durchlaufs (ein Bild, ein Modell)."""

    model_name: str
    image_name: str
    keywords: list[str]
    response_time_ms: float
    error: str | None = None
    standort: str | None = None
    foto_kategorie: str | None = None
    prompt_typ: str | None = None
    klassifikations_zeit_ms: float | None = None


@dataclass
class BenchmarkZusammenfassung:
    """Zusammenfassung der Benchmark-Ergebnisse pro Modell."""

    model_name: str
    bilder_verarbeitet: int
    durchschnitt_ms: float
    fehler: int
    durchschnitt_klassifikations_ms: float | None = None


class FotoKategorie(str, Enum):
    """Vordefinierte Foto-Kategorien für die Klassifikation."""

    LANDSCHAFT = "Landschaft"
    PORTRAET = "Porträt"
    ARCHITEKTUR = "Architektur"
    DOKUMENT = "Dokument"
    ESSEN = "Essen"
    TIERE = "Tiere"
    GARTEN = "Garten"
    MUSEUM = "Museum"
    VERANSTALTUNG = "Veranstaltung"
    SONSTIGES = "Sonstiges"


@dataclass
class KategorieConfig:
    """Konfiguration für eine einzelne Foto-Kategorie."""

    prompt: str
    modell: str | None = None


@dataclass
class KlassifikationsConfig:
    """Gesamte Klassifikations-Konfiguration."""

    modell: str
    prompt: str
    kategorien: dict[FotoKategorie, KategorieConfig] = field(default_factory=dict)


@dataclass
class KlassifikationsErgebnis:
    """Ergebnis eines klassifizierten Bild-Durchlaufs."""

    kategorie: FotoKategorie
    keywords: list[str]
    klassifikations_zeit_ms: float
    keyword_zeit_ms: float
    verwendeter_prompt_typ: str
    verwendetes_modell: str
