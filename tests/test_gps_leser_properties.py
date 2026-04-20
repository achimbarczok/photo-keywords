"""Property-basierte Tests für GpsLeser."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

from exifread.utils import Ratio
from hypothesis import given, settings
from hypothesis import strategies as st

from lightroom_ollama_keywords.gps_leser import GpsLeser


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_valid_lat_degrees = st.integers(min_value=0, max_value=89)
_valid_lon_degrees = st.integers(min_value=0, max_value=179)
_valid_minutes = st.integers(min_value=0, max_value=59)
_valid_seconds = st.floats(min_value=0.0, max_value=59.999, allow_nan=False, allow_infinity=False)

_lat_ref = st.sampled_from(["N", "S"])
_lon_ref = st.sampled_from(["E", "W"])

_valid_lat = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)
_valid_lon = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seconds_to_ratio(seconds: float) -> Ratio:
    """Convert a float seconds value to an exifread Ratio (numerator/1000)."""
    num = round(seconds * 1000)
    return Ratio(num, 1000)


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


def _create_katalog_db(conn: sqlite3.Connection) -> None:
    """Create the AgHarvestedExifMetadata table in the given connection."""
    conn.execute(
        """\
        CREATE TABLE AgHarvestedExifMetadata (
            image INTEGER PRIMARY KEY,
            gpsLatitude REAL,
            gpsLongitude REAL,
            hasGps REAL
        )
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Property 1: DMS-zu-Dezimalgrad-Konvertierung
# ---------------------------------------------------------------------------


class TestProperty1DmsZuDezimal:
    """**Validates: Requirements 1.1**

    Property 1: Für alle gültigen EXIF-GPS-Werte in DMS-Format
    (Grad 0–90/180, Minuten 0–59, Sekunden 0.0–59.999) mit Referenz
    N/S/E/W soll die Konvertierung in Dezimalgrad den mathematisch
    korrekten Wert ergeben: dezimal = grad + minuten/60 + sekunden/3600,
    negiert bei S oder W. Ergebnis in [-90, 90] für Breitengrad und
    [-180, 180] für Längengrad.
    """

    @given(
        grad=_valid_lat_degrees,
        minuten=_valid_minutes,
        sekunden=_valid_seconds,
        ref=_lat_ref,
    )
    @settings(max_examples=100)
    def test_latitude_conversion(
        self, grad: int, minuten: int, sekunden: float, ref: str
    ) -> None:
        dms = [Ratio(grad, 1), Ratio(minuten, 1), _seconds_to_ratio(sekunden)]

        result = GpsLeser._dms_zu_dezimal(dms, ref)

        # Recompute expected from the Ratio float values to match precision
        expected_sek = float(_seconds_to_ratio(sekunden))
        expected = grad + minuten / 60.0 + expected_sek / 3600.0
        if ref == "S":
            expected = -expected

        assert abs(result - expected) < 1e-9
        assert -90.0 <= result <= 90.0

    @given(
        grad=_valid_lon_degrees,
        minuten=_valid_minutes,
        sekunden=_valid_seconds,
        ref=_lon_ref,
    )
    @settings(max_examples=100)
    def test_longitude_conversion(
        self, grad: int, minuten: int, sekunden: float, ref: str
    ) -> None:
        dms = [Ratio(grad, 1), Ratio(minuten, 1), _seconds_to_ratio(sekunden)]

        result = GpsLeser._dms_zu_dezimal(dms, ref)

        expected_sek = float(_seconds_to_ratio(sekunden))
        expected = grad + minuten / 60.0 + expected_sek / 3600.0
        if ref == "W":
            expected = -expected

        assert abs(result - expected) < 1e-9
        assert -180.0 <= result <= 180.0


# ---------------------------------------------------------------------------
# Property 2: Katalog-GPS Round-Trip
# ---------------------------------------------------------------------------


class TestProperty2KatalogGpsRoundTrip:
    """**Validates: Requirements 2.1**

    Property 2: Für alle gültigen GPS-Koordinatenpaare (lat ∈ [-90, 90],
    lon ∈ [-180, 180]) soll das Schreiben in eine Test-SQLite-Datenbank
    (AgHarvestedExifMetadata-Schema) und Lesen via gps_aus_katalog ein
    äquivalentes Koordinatenpaar zurückgeben.
    """

    @given(lat=_valid_lat, lon=_valid_lon)
    @settings(max_examples=100)
    def test_round_trip(self, lat: float, lon: float) -> None:
        conn = sqlite3.connect(":memory:")
        _create_katalog_db(conn)

        conn.execute(
            "INSERT INTO AgHarvestedExifMetadata (image, gpsLatitude, gpsLongitude, hasGps) "
            "VALUES (?, ?, ?, 1.0)",
            (1, lat, lon),
        )
        conn.commit()

        leser = GpsLeser()
        result = leser.gps_aus_katalog(conn, image_id=1)

        assert result is not None
        assert result[0] == lat
        assert result[1] == lon

        conn.close()


# ---------------------------------------------------------------------------
# Property 3: Katalog-GPS hat Vorrang vor EXIF-GPS
# ---------------------------------------------------------------------------


class TestProperty3KatalogGpsVorrang:
    """**Validates: Requirements 2.3**

    Property 3: Für alle Paare von unterschiedlichen GPS-Koordinaten
    (exif_gps ≠ katalog_gps) soll gps_ermitteln mit beiden Quellen
    immer die Katalog-GPS-Koordinaten zurückgeben.
    """

    @given(
        katalog_lat=_valid_lat,
        katalog_lon=_valid_lon,
        exif_lat=_valid_lat,
        exif_lon=_valid_lon,
    )
    @settings(max_examples=100)
    def test_katalog_has_priority(
        self,
        katalog_lat: float,
        katalog_lon: float,
        exif_lat: float,
        exif_lon: float,
    ) -> None:
        from hypothesis import assume

        assume((katalog_lat, katalog_lon) != (exif_lat, exif_lon))

        # Set up in-memory catalog DB with katalog coordinates
        conn = sqlite3.connect(":memory:")
        _create_katalog_db(conn)
        conn.execute(
            "INSERT INTO AgHarvestedExifMetadata (image, gpsLatitude, gpsLongitude, hasGps) "
            "VALUES (?, ?, ?, 1.0)",
            (42, katalog_lat, katalog_lon),
        )
        conn.commit()

        leser = GpsLeser()

        # Mock gps_aus_exif to return the exif coordinates
        with patch.object(leser, "gps_aus_exif", return_value=(exif_lat, exif_lon)):
            result = leser.gps_ermitteln(
                image_path="dummy.jpg",
                katalog_conn=conn,
                image_id=42,
            )

        assert result is not None
        assert result[0] == katalog_lat
        assert result[1] == katalog_lon

        conn.close()
