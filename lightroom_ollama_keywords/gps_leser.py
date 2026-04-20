"""GpsLeser – Liest GPS-Koordinaten aus EXIF-Metadaten und Lightroom-Katalog."""

from __future__ import annotations

import logging
import sqlite3

import exifread
import exifread.utils

logger = logging.getLogger(__name__)

_KATALOG_GPS_QUERY = """\
SELECT gpsLatitude, gpsLongitude
FROM AgHarvestedExifMetadata
WHERE image = :image_id AND hasGps = 1.0
"""


class GpsLeser:
    """Liest GPS-Koordinaten aus verschiedenen Quellen."""

    def gps_aus_exif(self, image_path: str) -> tuple[float, float] | None:
        """Liest GPS-Koordinaten aus EXIF-Metadaten einer Bilddatei.

        Liest die Tags GPS GPSLatitude, GPS GPSLatitudeRef,
        GPS GPSLongitude, GPS GPSLongitudeRef und konvertiert
        die DMS-Werte (Grad/Minuten/Sekunden) in Dezimalgrad.

        Returns:
            (breitengrad, laengengrad) als Dezimalgrad oder None.
        """
        try:
            with open(image_path, "rb") as f:
                tags = exifread.process_file(f, details=False)
        except Exception:
            logger.warning("EXIF-Daten nicht lesbar: %s", image_path)
            return None

        lat_tag = tags.get("GPS GPSLatitude")
        lat_ref_tag = tags.get("GPS GPSLatitudeRef")
        lon_tag = tags.get("GPS GPSLongitude")
        lon_ref_tag = tags.get("GPS GPSLongitudeRef")

        if not all((lat_tag, lat_ref_tag, lon_tag, lon_ref_tag)):
            return None

        try:
            breitengrad = self._dms_zu_dezimal(
                lat_tag.values, str(lat_ref_tag)
            )
            laengengrad = self._dms_zu_dezimal(
                lon_tag.values, str(lon_ref_tag)
            )
        except Exception:
            logger.warning(
                "Ungültiges GPS-Format in EXIF-Daten: %s", image_path
            )
            return None

        return (breitengrad, laengengrad)

    def gps_aus_katalog(
        self, katalog_conn: sqlite3.Connection, image_id: int
    ) -> tuple[float, float] | None:
        """Liest GPS-Koordinaten aus der Lightroom-Katalog-Datenbank.

        Query auf AgHarvestedExifMetadata:
            SELECT gpsLatitude, gpsLongitude
            FROM AgHarvestedExifMetadata
            WHERE image = :image_id AND hasGps = 1.0

        Returns:
            (breitengrad, laengengrad) als Dezimalgrad oder None.
        """
        try:
            cursor = katalog_conn.execute(
                _KATALOG_GPS_QUERY, {"image_id": image_id}
            )
            row = cursor.fetchone()
        except sqlite3.Error:
            logger.warning(
                "Katalog-GPS nicht lesbar für image_id=%d", image_id
            )
            return None

        if row is None:
            return None

        lat, lon = row
        if lat is None or lon is None:
            return None

        return (float(lat), float(lon))

    def gps_ermitteln(
        self,
        image_path: str,
        katalog_conn: sqlite3.Connection | None = None,
        image_id: int | None = None,
    ) -> tuple[float, float] | None:
        """Ermittelt GPS-Koordinaten mit Priorität: Katalog > EXIF.

        1. Wenn katalog_conn und image_id vorhanden: Katalog-GPS versuchen
        2. Wenn kein Katalog-GPS: EXIF-GPS versuchen
        3. Wenn beides None: None zurückgeben

        Returns:
            (breitengrad, laengengrad) oder None.
        """
        if katalog_conn is not None and image_id is not None:
            katalog_gps = self.gps_aus_katalog(katalog_conn, image_id)
            if katalog_gps is not None:
                return katalog_gps

        return self.gps_aus_exif(image_path)

    @staticmethod
    def _dms_zu_dezimal(
        dms_wert: list[exifread.utils.Ratio], referenz: str
    ) -> float:
        """Konvertiert EXIF DMS-Werte (Grad, Minuten, Sekunden) in Dezimalgrad.

        Negative Werte für S (Süd) und W (West).
        """
        grad = float(dms_wert[0])
        minuten = float(dms_wert[1])
        sekunden = float(dms_wert[2])

        dezimal = grad + minuten / 60.0 + sekunden / 3600.0

        if referenz.upper() in ("S", "W"):
            dezimal = -dezimal

        return dezimal
