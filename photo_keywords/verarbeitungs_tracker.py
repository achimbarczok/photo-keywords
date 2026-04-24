"""VerarbeitungsTracker – Verwaltet die Tracking-Datenbank für verarbeitete Fotos."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from photo_keywords.errors import TrackerError
from photo_keywords.models import FotoEintrag


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
        """Erstellt die Tabellen und Indizes, falls sie noch nicht existieren."""
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
            CREATE TABLE IF NOT EXISTS fehler (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                model_name TEXT NOT NULL,
                fehler_text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                UNIQUE(file_path, model_name)
            );
            CREATE INDEX IF NOT EXISTS idx_fehler_file_model
                ON fehler(file_path, model_name);
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
        """Filtert eine Liste von Fotos und gibt nur unverarbeitete zurück.

        Überspringt sowohl erfolgreich verarbeitete als auch fehlgeschlagene Fotos.
        """
        return [
            foto for foto in fotos
            if not self.ist_verarbeitet(foto.file_path, model_name)
            and not self.hat_fehler(foto.file_path, model_name)
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

    # ------------------------------------------------------------------
    # Fehler-Tracking
    # ------------------------------------------------------------------

    def hat_fehler(self, file_path: str, model_name: str) -> bool:
        """Prüft, ob ein Foto bereits mit einem Fehler markiert ist."""
        cursor = self._conn.execute(
            "SELECT 1 FROM fehler WHERE file_path = ? AND model_name = ?",
            (file_path, model_name),
        )
        return cursor.fetchone() is not None

    def fehler_speichern(
        self, file_path: str, model_name: str, fehler_text: str
    ) -> None:
        """Speichert einen Fehler-Eintrag für ein Foto."""
        timestamp = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO fehler
                (file_path, model_name, fehler_text, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (file_path, model_name, fehler_text, timestamp),
        )
        self._conn.commit()

    def fehler_zuruecksetzen(self, model_name: str) -> int:
        """Löscht alle Fehler-Einträge für ein Modell. Gibt Anzahl gelöschter Einträge zurück."""
        cursor = self._conn.execute(
            "DELETE FROM fehler WHERE model_name = ?",
            (model_name,),
        )
        self._conn.commit()
        return cursor.rowcount
