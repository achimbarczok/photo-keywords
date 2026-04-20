"""VerarbeitungsTracker – Verwaltet die Tracking-Datenbank für verarbeitete Fotos."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from lightroom_ollama_keywords.errors import TrackerError
from lightroom_ollama_keywords.models import FotoEintrag


class VerarbeitungsTracker:
    """Verwaltet eine SQLite-Datenbank, die protokolliert, welche Fotos
    mit welchem Modell verarbeitet wurden."""

    def __init__(self, db_path: str) -> None:
        """Öffnet oder erstellt die Tracking-Datenbank und legt das Schema an.

        Args:
            db_path: Pfad zur SQLite-Datenbankdatei.

        Raises:
            TrackerError: Bei Dateizugriffsproblemen.
        """
        try:
            self._conn = sqlite3.connect(db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._create_schema()
        except (sqlite3.OperationalError, OSError) as exc:
            raise TrackerError(
                f"Tracking-Datenbank kann nicht geöffnet werden: {db_path}"
            ) from exc

    def _create_schema(self) -> None:
        """Erstellt die Tabelle und den Index, falls sie noch nicht existieren."""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS verarbeitungen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                model_name TEXT NOT NULL,
                model_version TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                UNIQUE(file_path, model_name)
            );
            CREATE INDEX IF NOT EXISTS idx_file_model
                ON verarbeitungen(file_path, model_name);
            """
        )

    def ist_verarbeitet(self, file_path: str, model_name: str) -> bool:
        """Prüft, ob ein Foto bereits mit dem angegebenen Modell verarbeitet wurde."""
        cursor = self._conn.execute(
            "SELECT 1 FROM verarbeitungen WHERE file_path = ? AND model_name = ?",
            (file_path, model_name),
        )
        return cursor.fetchone() is not None

    def unverarbeitete_filtern(
        self, fotos: list[FotoEintrag], model_name: str
    ) -> list[FotoEintrag]:
        """Filtert eine Liste von Fotos und gibt nur unverarbeitete zurück."""
        return [
            foto for foto in fotos if not self.ist_verarbeitet(foto.file_path, model_name)
        ]

    def verarbeitung_speichern(
        self, file_path: str, model_name: str, model_version: str
    ) -> None:
        """Speichert einen Verarbeitungseintrag mit ISO-8601-Zeitstempel."""
        timestamp = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO verarbeitungen
                (file_path, model_name, model_version, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (file_path, model_name, model_version, timestamp),
        )
        self._conn.commit()

    def close(self) -> None:
        """Schließt die Datenbankverbindung."""
        self._conn.close()
