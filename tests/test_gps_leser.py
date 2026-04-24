"""Unit-Tests für GpsLeser – gps_aus_exif(), _dms_zu_dezimal(), gps_aus_katalog(), gps_ermitteln()."""

from __future__ import annotations

import logging
import sqlite3
from unittest.mock import MagicMock, mock_open, patch

import pytest
from exifread.utils import Ratio

from photo_keywords.gps_leser import GpsLeser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gps_tags(
    lat_dms: list[Ratio],
    lat_ref: str,
    lon_dms: list[Ratio],
    lon_ref: str,
) -> dict:
    """Build a dict mimicking exifread.process_file() output for GPS tags."""
    lat_tag = MagicMock()
    lat_tag.values = lat_dms

    lat_ref_tag = MagicMock()
    lat_ref_tag.__str__ = lambda self: lat_ref

    lon_tag = MagicMock()
    lon_tag.values = lon_dms

    lon_ref_tag = MagicMock()
    lon_ref_tag.__str__ = lambda self: lon_ref

    return {
        "GPS GPSLatitude": lat_tag,
        "GPS GPSLatitudeRef": lat_ref_tag,
        "GPS GPSLongitude": lon_tag,
        "GPS GPSLongitudeRef": lon_ref_tag,
    }


# ---------------------------------------------------------------------------
# _dms_zu_dezimal
# ---------------------------------------------------------------------------


class TestDmsZuDezimal:
    """Validates: Requirement 1.1 — DMS-zu-Dezimalgrad-Konvertierung."""

    def test_north_east(self) -> None:
        # Berlin: 52°31'12.34" N, 13°24'56.78" E
        dms_lat = [Ratio(52, 1), Ratio(31, 1), Ratio(1234, 100)]
        dms_lon = [Ratio(13, 1), Ratio(24, 1), Ratio(5678, 100)]

        lat = GpsLeser._dms_zu_dezimal(dms_lat, "N")
        lon = GpsLeser._dms_zu_dezimal(dms_lon, "E")

        expected_lat = 52 + 31 / 60 + 12.34 / 3600
        expected_lon = 13 + 24 / 60 + 56.78 / 3600

        assert abs(lat - expected_lat) < 1e-9
        assert abs(lon - expected_lon) < 1e-9

    def test_south_west_negated(self) -> None:
        # Buenos Aires: ~34°36'12" S, ~58°22'54" W
        dms_lat = [Ratio(34, 1), Ratio(36, 1), Ratio(12, 1)]
        dms_lon = [Ratio(58, 1), Ratio(22, 1), Ratio(54, 1)]

        lat = GpsLeser._dms_zu_dezimal(dms_lat, "S")
        lon = GpsLeser._dms_zu_dezimal(dms_lon, "W")

        expected_lat = -(34 + 36 / 60 + 12 / 3600)
        expected_lon = -(58 + 22 / 60 + 54 / 3600)

        assert abs(lat - expected_lat) < 1e-9
        assert abs(lon - expected_lon) < 1e-9

    def test_zero_values(self) -> None:
        dms = [Ratio(0, 1), Ratio(0, 1), Ratio(0, 1)]
        assert GpsLeser._dms_zu_dezimal(dms, "N") == 0.0
        assert GpsLeser._dms_zu_dezimal(dms, "S") == 0.0

    def test_case_insensitive_ref(self) -> None:
        dms = [Ratio(10, 1), Ratio(0, 1), Ratio(0, 1)]
        assert GpsLeser._dms_zu_dezimal(dms, "s") == -10.0
        assert GpsLeser._dms_zu_dezimal(dms, "w") == -10.0
        assert GpsLeser._dms_zu_dezimal(dms, "N") == 10.0
        assert GpsLeser._dms_zu_dezimal(dms, "E") == 10.0


# ---------------------------------------------------------------------------
# gps_aus_exif
# ---------------------------------------------------------------------------


class TestGpsAusExif:
    """Validates: Requirements 1.1, 1.2, 1.3, 1.4."""

    def test_valid_gps_tags(self, tmp_path) -> None:
        """Requirement 1.1: GPS-Koordinaten als Dezimalgrad-Paar extrahieren."""
        # Berlin: 52°31'0" N, 13°24'0" E
        tags = _make_gps_tags(
            lat_dms=[Ratio(52, 1), Ratio(31, 1), Ratio(0, 1)],
            lat_ref="N",
            lon_dms=[Ratio(13, 1), Ratio(24, 1), Ratio(0, 1)],
            lon_ref="E",
        )

        leser = GpsLeser()
        dummy = tmp_path / "test.jpg"
        dummy.write_bytes(b"fake")

        with patch("photo_keywords.gps_leser.exifread.process_file", return_value=tags):
            result = leser.gps_aus_exif(str(dummy))

        assert result is not None
        expected_lat = 52 + 31 / 60
        expected_lon = 13 + 24 / 60
        assert abs(result[0] - expected_lat) < 1e-9
        assert abs(result[1] - expected_lon) < 1e-9

    def test_no_gps_tags_returns_none(self, tmp_path) -> None:
        """Requirement 1.2: None bei fehlenden GPS-Tags."""
        leser = GpsLeser()
        dummy = tmp_path / "no_gps.jpg"
        dummy.write_bytes(b"fake")

        with patch("photo_keywords.gps_leser.exifread.process_file", return_value={}):
            result = leser.gps_aus_exif(str(dummy))

        assert result is None

    def test_partial_gps_tags_returns_none(self, tmp_path) -> None:
        """Requirement 1.2: None wenn nur einige GPS-Tags vorhanden."""
        tags = {"GPS GPSLatitude": MagicMock(), "GPS GPSLatitudeRef": MagicMock()}
        leser = GpsLeser()
        dummy = tmp_path / "partial.jpg"
        dummy.write_bytes(b"fake")

        with patch("photo_keywords.gps_leser.exifread.process_file", return_value=tags):
            result = leser.gps_aus_exif(str(dummy))

        assert result is None

    def test_invalid_format_returns_none_and_logs(self, tmp_path, caplog) -> None:
        """Requirement 1.3: None + Logging bei ungültigem GPS-Format."""
        lat_tag = MagicMock()
        lat_tag.values = "not_a_list"  # invalid format
        lat_ref_tag = MagicMock()
        lat_ref_tag.__str__ = lambda self: "N"
        lon_tag = MagicMock()
        lon_tag.values = "not_a_list"
        lon_ref_tag = MagicMock()
        lon_ref_tag.__str__ = lambda self: "E"

        tags = {
            "GPS GPSLatitude": lat_tag,
            "GPS GPSLatitudeRef": lat_ref_tag,
            "GPS GPSLongitude": lon_tag,
            "GPS GPSLongitudeRef": lon_ref_tag,
        }

        leser = GpsLeser()
        dummy = tmp_path / "invalid.jpg"
        dummy.write_bytes(b"fake")

        with patch("photo_keywords.gps_leser.exifread.process_file", return_value=tags):
            with caplog.at_level(logging.WARNING):
                result = leser.gps_aus_exif(str(dummy))

        assert result is None
        assert "Ungültiges GPS-Format" in caplog.text

    def test_unreadable_file_returns_none_and_logs(self, tmp_path, caplog) -> None:
        """Requirement 1.3: None + Logging bei nicht lesbarer Datei."""
        leser = GpsLeser()

        with caplog.at_level(logging.WARNING):
            result = leser.gps_aus_exif("/nonexistent/path.jpg")

        assert result is None
        assert "EXIF-Daten nicht lesbar" in caplog.text

    def test_south_west_coordinates(self, tmp_path) -> None:
        """Requirement 1.1: Korrekte Konvertierung für S/W-Referenzen."""
        tags = _make_gps_tags(
            lat_dms=[Ratio(34, 1), Ratio(0, 1), Ratio(0, 1)],
            lat_ref="S",
            lon_dms=[Ratio(58, 1), Ratio(0, 1), Ratio(0, 1)],
            lon_ref="W",
        )

        leser = GpsLeser()
        dummy = tmp_path / "sw.jpg"
        dummy.write_bytes(b"fake")

        with patch("photo_keywords.gps_leser.exifread.process_file", return_value=tags):
            result = leser.gps_aus_exif(str(dummy))

        assert result is not None
        assert result[0] == -34.0
        assert result[1] == -58.0


# ---------------------------------------------------------------------------
# Helpers – Katalog-DB
# ---------------------------------------------------------------------------


@pytest.fixture()
def katalog_db() -> sqlite3.Connection:
    """In-memory SQLite DB with AgHarvestedExifMetadata schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """\
        CREATE TABLE AgHarvestedExifMetadata (
            image INTEGER,
            hasGps REAL,
            gpsLatitude REAL,
            gpsLongitude REAL
        )"""
    )
    return conn


# ---------------------------------------------------------------------------
# gps_aus_katalog
# ---------------------------------------------------------------------------


class TestGpsAusKatalog:
    """Validates: Requirements 2.1, 2.2."""

    def test_katalog_with_gps_returns_coordinates(self, katalog_db) -> None:
        """Requirement 2.1: GPS-Koordinaten aus Katalog lesen."""
        katalog_db.execute(
            "INSERT INTO AgHarvestedExifMetadata VALUES (1, 1.0, 52.52, 13.405)"
        )
        leser = GpsLeser()
        result = leser.gps_aus_katalog(katalog_db, image_id=1)

        assert result is not None
        assert abs(result[0] - 52.52) < 1e-9
        assert abs(result[1] - 13.405) < 1e-9

    def test_katalog_without_gps_returns_none(self, katalog_db) -> None:
        """Requirement 2.2: None bei fehlendem Katalog-GPS."""
        # Image exists but hasGps = 0.0
        katalog_db.execute(
            "INSERT INTO AgHarvestedExifMetadata VALUES (1, 0.0, NULL, NULL)"
        )
        leser = GpsLeser()
        result = leser.gps_aus_katalog(katalog_db, image_id=1)

        assert result is None

    def test_katalog_image_not_found_returns_none(self, katalog_db) -> None:
        """Requirement 2.2: None wenn image_id nicht existiert."""
        leser = GpsLeser()
        result = leser.gps_aus_katalog(katalog_db, image_id=999)

        assert result is None

    def test_katalog_null_coordinates_returns_none(self, katalog_db) -> None:
        """Requirement 2.2: None wenn GPS-Felder NULL sind trotz hasGps=1."""
        katalog_db.execute(
            "INSERT INTO AgHarvestedExifMetadata VALUES (1, 1.0, NULL, NULL)"
        )
        leser = GpsLeser()
        result = leser.gps_aus_katalog(katalog_db, image_id=1)

        assert result is None

    def test_katalog_db_error_returns_none_and_logs(self, caplog) -> None:
        """Requirement 2.2: None + Logging bei DB-Fehler."""
        conn = sqlite3.connect(":memory:")
        # No table created → query will fail
        leser = GpsLeser()

        with caplog.at_level(logging.WARNING):
            result = leser.gps_aus_katalog(conn, image_id=1)

        assert result is None
        assert "Katalog-GPS nicht lesbar" in caplog.text


# ---------------------------------------------------------------------------
# gps_ermitteln
# ---------------------------------------------------------------------------


class TestGpsErmitteln:
    """Validates: Requirements 2.3 — Katalog-GPS hat Vorrang vor EXIF-GPS."""

    def test_katalog_preferred_over_exif(self, katalog_db, tmp_path) -> None:
        """Requirement 2.3: Katalog-GPS hat Vorrang."""
        # Katalog has Berlin coordinates
        katalog_db.execute(
            "INSERT INTO AgHarvestedExifMetadata VALUES (1, 1.0, 52.52, 13.405)"
        )
        # EXIF would return different coordinates (Buenos Aires)
        tags = _make_gps_tags(
            lat_dms=[Ratio(34, 1), Ratio(0, 1), Ratio(0, 1)],
            lat_ref="S",
            lon_dms=[Ratio(58, 1), Ratio(0, 1), Ratio(0, 1)],
            lon_ref="W",
        )
        leser = GpsLeser()
        dummy = tmp_path / "test.jpg"
        dummy.write_bytes(b"fake")

        with patch("photo_keywords.gps_leser.exifread.process_file", return_value=tags):
            result = leser.gps_ermitteln(
                str(dummy), katalog_conn=katalog_db, image_id=1
            )

        assert result is not None
        # Should be Katalog coordinates (Berlin), not EXIF (Buenos Aires)
        assert abs(result[0] - 52.52) < 1e-9
        assert abs(result[1] - 13.405) < 1e-9

    def test_falls_back_to_exif_when_no_katalog_gps(
        self, katalog_db, tmp_path
    ) -> None:
        """Requirement 2.3: Fallback auf EXIF wenn kein Katalog-GPS."""
        tags = _make_gps_tags(
            lat_dms=[Ratio(52, 1), Ratio(31, 1), Ratio(0, 1)],
            lat_ref="N",
            lon_dms=[Ratio(13, 1), Ratio(24, 1), Ratio(0, 1)],
            lon_ref="E",
        )
        leser = GpsLeser()
        dummy = tmp_path / "test.jpg"
        dummy.write_bytes(b"fake")

        with patch("photo_keywords.gps_leser.exifread.process_file", return_value=tags):
            result = leser.gps_ermitteln(
                str(dummy), katalog_conn=katalog_db, image_id=999
            )

        assert result is not None
        expected_lat = 52 + 31 / 60
        expected_lon = 13 + 24 / 60
        assert abs(result[0] - expected_lat) < 1e-9
        assert abs(result[1] - expected_lon) < 1e-9

    def test_exif_only_when_no_katalog_conn(self, tmp_path) -> None:
        """Requirement 2.3: Nur EXIF wenn kein Katalog-Connection."""
        tags = _make_gps_tags(
            lat_dms=[Ratio(10, 1), Ratio(0, 1), Ratio(0, 1)],
            lat_ref="N",
            lon_dms=[Ratio(20, 1), Ratio(0, 1), Ratio(0, 1)],
            lon_ref="E",
        )
        leser = GpsLeser()
        dummy = tmp_path / "test.jpg"
        dummy.write_bytes(b"fake")

        with patch("photo_keywords.gps_leser.exifread.process_file", return_value=tags):
            result = leser.gps_ermitteln(str(dummy))

        assert result is not None
        assert result[0] == 10.0
        assert result[1] == 20.0

    def test_returns_none_when_no_gps_anywhere(self, katalog_db, tmp_path) -> None:
        """Both sources return None → gps_ermitteln returns None."""
        leser = GpsLeser()
        dummy = tmp_path / "no_gps.jpg"
        dummy.write_bytes(b"fake")

        with patch("photo_keywords.gps_leser.exifread.process_file", return_value={}):
            result = leser.gps_ermitteln(
                str(dummy), katalog_conn=katalog_db, image_id=999
            )

        assert result is None
