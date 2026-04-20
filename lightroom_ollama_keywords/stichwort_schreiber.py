"""StichwortSchreiber – schreibt IPTC-Keywords via ExifTool in Bilddateien."""

from __future__ import annotations

import logging
import subprocess

from lightroom_ollama_keywords.errors import MetadataWriteError

logger = logging.getLogger(__name__)


class StichwortSchreiber:
    """Schreibt Stichwörter als IPTC-Keywords und XMP-Subject in Bilddateien."""

    def __init__(self, exiftool_path: str | None = None) -> None:
        """Initialisiert den StichwortSchreiber.

        Args:
            exiftool_path: Pfad zur exiftool-Executable.
                           None = ExifTool im PATH suchen.
        """
        self._exiftool_path = exiftool_path or "exiftool"
        self._et: object | None = None
        # ExifToolHelper nur zum Lesen verwenden
        try:
            import exiftool
            kwargs: dict = {}
            if exiftool_path is not None:
                kwargs["executable"] = exiftool_path
            self._et = exiftool.ExifToolHelper(
                auto_start=True,
                check_execute=False,
                check_tag_names=False,
                common_args=None,
                **kwargs,
            )
        except Exception:
            self._et = None

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def stichwörter_schreiben(self, file_path: str, keywords: list[str]) -> None:
        """Schreibt Stichwörter in die Bilddatei (IPTC + XMP).

        Vorhandene Keywords bleiben erhalten; neue werden ergänzt,
        Duplikate vermieden.

        Verwendet ExifTool's -@ Argfile-Modus für korrektes UTF-8 auf Windows.

        Raises:
            MetadataWriteError: Wenn das Schreiben fehlschlägt.
        """
        import tempfile
        import os

        try:
            vorhandene = self._vorhandene_keywords_lesen(file_path)
            zusammengeführt = self._keywords_zusammenführen(vorhandene, set(keywords))
            neue_keywords = zusammengeführt - vorhandene

            if not neue_keywords:
                logger.info("Keine neuen Keywords für %s", file_path)
                return

            # Argfile mit UTF-8 BOM schreiben, damit ExifTool UTF-8 erkennt
            argfile_fd, argfile_path = tempfile.mkstemp(suffix=".args", prefix="exiftool_")
            try:
                with os.fdopen(argfile_fd, "w", encoding="utf-8") as f:
                    f.write("-codedcharacterset=utf8\n")
                    for kw in sorted(neue_keywords):
                        f.write(f"-IPTC:Keywords+={kw}\n")
                        f.write(f"-XMP:Subject+={kw}\n")
                    f.write("-overwrite_original\n")
                    f.write(f"{file_path}\n")

                result = subprocess.run(
                    [self._exiftool_path, "-@", argfile_path, "-charset", "filename=utf8"],
                    capture_output=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    stderr = result.stderr.decode("utf-8", errors="replace")
                    raise MetadataWriteError(
                        f"ExifTool-Fehler für '{file_path}': {stderr}"
                    )
            finally:
                os.unlink(argfile_path)
        except MetadataWriteError:
            raise
        except Exception as exc:
            raise MetadataWriteError(
                f"Fehler beim Schreiben der Metadaten für '{file_path}': {exc}"
            ) from exc

    def close(self) -> None:
        """Beendet den ExifTool-Prozess."""
        if self._et is not None and hasattr(self._et, "running") and self._et.running:
            self._et.terminate()

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _vorhandene_keywords_lesen(self, file_path: str) -> set[str]:
        """Liest bereits vorhandene IPTC-Keywords aus der Bilddatei."""
        try:
            tags = self._et.get_tags(file_path, tags=["IPTC:Keywords"])
            if not tags:
                return set()
            raw = tags[0].get("IPTC:Keywords", [])
            if isinstance(raw, str):
                return {raw}
            if isinstance(raw, list):
                return set(raw)
            return set()
        except Exception:
            # Wenn keine Keywords gelesen werden können, leere Menge
            return set()

    @staticmethod
    def _keywords_zusammenführen(
        vorhandene: set[str], neue: set[str]
    ) -> set[str]:
        """Vereinigt vorhandene und neue Keywords ohne Duplikate.

        Dies ist die reine Logik, die in Property-Tests geprüft wird.
        """
        return vorhandene | neue
