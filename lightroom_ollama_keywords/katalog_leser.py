"""KatalogLeser — Liest Foto-Einträge aus dem Lightroom-Katalog (SQLite, read-only)."""

from __future__ import annotations

import os
import sqlite3

from lightroom_ollama_keywords.errors import KatalogError
from lightroom_ollama_keywords.models import FotoEintrag

_FOTO_QUERY = """\
SELECT
    image.id_local AS image_id,
    root_folder.absolutePath || folder.pathFromRoot || file.baseName || '.' || file.extension AS file_path
FROM
    Adobe_images AS image
JOIN AgLibraryFile AS file
    ON image.rootFile = file.id_local
JOIN AgLibraryFolder AS folder
    ON file.folder = folder.id_local
JOIN AgLibraryRootFolder AS root_folder
    ON folder.rootFolder = root_folder.id_local
WHERE
    LOWER(file.extension) NOT IN ('mp4', 'mov', 'avi', 'mkv', 'wmv', 'flv', 'webm', 'm4v', 'mpg', 'mpeg', '3gp', 'psd')
"""


class KatalogLeser:
    """Liest Foto-Einträge aus einem Lightroom-Classic-Katalog."""

    def __init__(self, catalog_path: str) -> None:
        """Öffnet den Katalog im Read-Only-Modus.

        Raises:
            KatalogError: Wenn die Datei nicht gefunden oder nicht lesbar ist.
        """
        if not os.path.isfile(catalog_path):
            raise KatalogError(
                f"Lightroom-Katalog nicht gefunden: {catalog_path}"
            )

        try:
            uri = f"file:{catalog_path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True)
        except sqlite3.OperationalError as exc:
            raise KatalogError(
                f"Lightroom-Katalog nicht lesbar: {catalog_path}"
            ) from exc

    def alle_fotos_lesen(self) -> list[FotoEintrag]:
        """Liest alle Foto-Einträge mit vollständigem Dateipfad."""
        try:
            cursor = self._conn.execute(_FOTO_QUERY)
            return [
                FotoEintrag(image_id=row[0], file_path=row[1])
                for row in cursor.fetchall()
            ]
        except sqlite3.Error as exc:
            raise KatalogError(
                f"Fehler beim Lesen der Foto-Einträge: {exc}"
            ) from exc

    def close(self) -> None:
        """Schließt die Datenbankverbindung."""
        self._conn.close()
