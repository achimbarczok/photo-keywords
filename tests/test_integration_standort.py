"""Integrationstests: GPS → Standort → Keywords (Task 9.1) und Batch mit Standort (Task 9.2).

Task 9.1: Vollständiger Pfad: EXIF-GPS lesen → Reverse-Geocoding → Standort-Stichwörter in Keyword-Liste.
Task 9.2: BatchProcessor mit aktivierter Standort-Funktion, Mock-Ollama, echte GpsLeser/StandortResolver.

Verwendet echte Instanzen von GpsLeser, StandortResolver und BatchProcessor,
mockt aber externe Abhängigkeiten (exifread, reverse_geocoder, OllamaClient, StichwortSchreiber, VerarbeitungsTracker).

Requirements: 1.1, 3.1, 4.1, 4.2, 5.1, 7.5
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from photo_keywords.batch_processor import BatchProcessor
from photo_keywords.gps_leser import GpsLeser
from photo_keywords.models import FotoEintrag, StandortDaten
from photo_keywords.standort_resolver import StandortResolver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exif_ratio(value: float) -> MagicMock:
    """Create a mock exifread Ratio that converts to float."""
    r = MagicMock()
    r.__float__ = MagicMock(return_value=value)
    return r


def _make_gps_tags(
    lat_deg: float = 52.0,
    lat_min: float = 31.0,
    lat_sec: float = 12.0,
    lat_ref: str = "N",
    lon_deg: float = 13.0,
    lon_min: float = 24.0,
    lon_sec: float = 17.0,
    lon_ref: str = "E",
) -> dict:
    """Build a mock exifread tag dict with GPS tags."""
    lat_tag = MagicMock()
    lat_tag.values = [_make_exif_ratio(lat_deg), _make_exif_ratio(lat_min), _make_exif_ratio(lat_sec)]

    lon_tag = MagicMock()
    lon_tag.values = [_make_exif_ratio(lon_deg), _make_exif_ratio(lon_min), _make_exif_ratio(lon_sec)]

    lat_ref_tag = MagicMock()
    lat_ref_tag.__str__ = MagicMock(return_value=lat_ref)

    lon_ref_tag = MagicMock()
    lon_ref_tag.__str__ = MagicMock(return_value=lon_ref)

    return {
        "GPS GPSLatitude": lat_tag,
        "GPS GPSLatitudeRef": lat_ref_tag,
        "GPS GPSLongitude": lon_tag,
        "GPS GPSLongitudeRef": lon_ref_tag,
    }


def _make_mock_rg(rg_result: list[dict]) -> MagicMock:
    """Create a mock reverse_geocoder module with search() returning rg_result."""
    mock_rg = MagicMock()
    mock_rg.search.return_value = rg_result
    return mock_rg


# ---------------------------------------------------------------------------
# Integration Test: GPS → Standort → Keywords
# ---------------------------------------------------------------------------

class TestGpsStandortKeywordsIntegration:
    """Integration test: Full pipeline from EXIF GPS to merged keyword list.

    Validates: Requirements 1.1, 3.1, 4.1
    """

    def test_full_pipeline_berlin(self, tmp_path):
        """EXIF GPS → StandortResolver → merged keywords contain Berlin + DE + KI keywords."""
        image_path = str(tmp_path / "foto_berlin.jpg")
        (tmp_path / "foto_berlin.jpg").write_bytes(b"\xff\xd8dummy")

        gps_tags = _make_gps_tags(
            lat_deg=52.0, lat_min=31.0, lat_sec=12.0, lat_ref="N",
            lon_deg=13.0, lon_min=24.0, lon_sec=17.0, lon_ref="E",
        )

        rg_result = [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
        mock_rg = _make_mock_rg(rg_result)

        gps_leser = GpsLeser()
        standort_resolver = StandortResolver()

        with (
            patch("exifread.process_file", return_value=gps_tags),
            patch.dict("sys.modules", {"reverse_geocoder": mock_rg}),
        ):
            # Step 1: Read GPS from EXIF (Req 1.1)
            gps = gps_leser.gps_aus_exif(image_path)

            assert gps is not None
            breitengrad, laengengrad = gps
            # 52 + 31/60 + 12/3600 ≈ 52.52
            assert pytest.approx(breitengrad, abs=0.01) == 52.52
            assert pytest.approx(laengengrad, abs=0.01) == 13.40

            # Step 2: Resolve standort (Req 3.1)
            standort = standort_resolver.standort_aufloesen(breitengrad, laengengrad)

            assert standort is not None
            assert standort.stadt == "Berlin"
            assert standort.land == "DE"
            mock_rg.search.assert_called_once()

            # Step 3: Merge keywords (Req 4.1)
            ki_keywords = ["Architektur", "Brandenburger Tor", "Nacht"]
            merged = BatchProcessor._keywords_zusammenfuehren(ki_keywords, standort)

            # Standort keywords come first
            assert merged[0] == "Berlin"
            assert "DE" in merged
            # All KI keywords present
            for kw in ki_keywords:
                assert kw in merged
            # No duplicates
            assert len(merged) == len(set(merged))
            # No empty strings
            assert "" not in merged

    def test_full_pipeline_muenchen_with_region(self, tmp_path):
        """Pipeline with distinct region (München, Bayern, DE)."""
        image_path = str(tmp_path / "foto_muenchen.jpg")
        (tmp_path / "foto_muenchen.jpg").write_bytes(b"\xff\xd8dummy")

        gps_tags = _make_gps_tags(
            lat_deg=48.0, lat_min=8.0, lat_sec=0.0, lat_ref="N",
            lon_deg=11.0, lon_min=34.0, lon_sec=0.0, lon_ref="E",
        )

        rg_result = [{"name": "München", "admin1": "Bayern", "cc": "DE"}]
        mock_rg = _make_mock_rg(rg_result)

        gps_leser = GpsLeser()
        standort_resolver = StandortResolver()

        with (
            patch("exifread.process_file", return_value=gps_tags),
            patch.dict("sys.modules", {"reverse_geocoder": mock_rg}),
        ):
            gps = gps_leser.gps_aus_exif(image_path)
            assert gps is not None

            standort = standort_resolver.standort_aufloesen(gps[0], gps[1])
            assert standort is not None
            assert standort.stadt == "München"
            assert standort.region == "Bayern"
            assert standort.land == "DE"

            ki_keywords = ["Alpen", "Kirche"]
            merged = BatchProcessor._keywords_zusammenfuehren(ki_keywords, standort)

            assert "München" in merged
            assert "Bayern" in merged
            assert "DE" in merged
            assert "Alpen" in merged
            assert "Kirche" in merged
            assert len(merged) == len(set(merged))

    def test_pipeline_no_gps_in_exif(self, tmp_path):
        """No GPS tags in EXIF → no standort → only KI keywords."""
        image_path = str(tmp_path / "foto_no_gps.jpg")
        (tmp_path / "foto_no_gps.jpg").write_bytes(b"\xff\xd8dummy")

        tags_without_gps = {"EXIF ExifImageWidth": MagicMock()}

        gps_leser = GpsLeser()

        with patch("exifread.process_file", return_value=tags_without_gps):
            gps = gps_leser.gps_aus_exif(image_path)
            assert gps is None

            ki_keywords = ["Landschaft", "Sonnenuntergang"]
            merged = BatchProcessor._keywords_zusammenfuehren(ki_keywords, None)
            assert merged == ["Landschaft", "Sonnenuntergang"]

    def test_pipeline_duplicate_keyword_between_standort_and_ki(self, tmp_path):
        """KI keyword that matches a standort keyword is deduplicated."""
        image_path = str(tmp_path / "foto_dup.jpg")
        (tmp_path / "foto_dup.jpg").write_bytes(b"\xff\xd8dummy")

        gps_tags = _make_gps_tags()
        rg_result = [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
        mock_rg = _make_mock_rg(rg_result)

        gps_leser = GpsLeser()
        standort_resolver = StandortResolver()

        with (
            patch("exifread.process_file", return_value=gps_tags),
            patch.dict("sys.modules", {"reverse_geocoder": mock_rg}),
        ):
            gps = gps_leser.gps_aus_exif(image_path)
            assert gps is not None

            standort = standort_resolver.standort_aufloesen(gps[0], gps[1])
            assert standort is not None

            # KI returns "Berlin" as a keyword too
            ki_keywords = ["Berlin", "Fernsehturm", "Nacht"]
            merged = BatchProcessor._keywords_zusammenfuehren(ki_keywords, standort)

            # Berlin appears only once
            assert merged.count("Berlin") == 1
            assert "Fernsehturm" in merged
            assert "Nacht" in merged
            assert "DE" in merged

    def test_pipeline_southern_hemisphere(self, tmp_path):
        """GPS coordinates in southern/western hemisphere (negative values)."""
        image_path = str(tmp_path / "foto_sydney.jpg")
        (tmp_path / "foto_sydney.jpg").write_bytes(b"\xff\xd8dummy")

        gps_tags = _make_gps_tags(
            lat_deg=33.0, lat_min=52.0, lat_sec=10.0, lat_ref="S",
            lon_deg=151.0, lon_min=12.0, lon_sec=30.0, lon_ref="E",
        )

        rg_result = [{"name": "Sydney", "admin1": "New South Wales", "cc": "AU"}]
        mock_rg = _make_mock_rg(rg_result)

        gps_leser = GpsLeser()
        standort_resolver = StandortResolver()

        with (
            patch("exifread.process_file", return_value=gps_tags),
            patch.dict("sys.modules", {"reverse_geocoder": mock_rg}),
        ):
            gps = gps_leser.gps_aus_exif(image_path)
            assert gps is not None
            # Southern hemisphere → negative latitude
            assert gps[0] < 0

            standort = standort_resolver.standort_aufloesen(gps[0], gps[1])
            assert standort is not None
            assert standort.stadt == "Sydney"
            assert standort.land == "AU"

            ki_keywords = ["Opera House", "Harbour"]
            merged = BatchProcessor._keywords_zusammenfuehren(ki_keywords, standort)

            assert "Sydney" in merged
            assert "New South Wales" in merged
            assert "AU" in merged
            assert "Opera House" in merged
            assert "Harbour" in merged


# ---------------------------------------------------------------------------
# Integration Test: Batch mit Standort (Task 9.2)
# ---------------------------------------------------------------------------

class TestBatchMitStandortIntegration:
    """Integration test: BatchProcessor with real GpsLeser + StandortResolver.

    Uses real BatchProcessor, GpsLeser, StandortResolver instances but mocks
    external dependencies (exifread, reverse_geocoder, OllamaClient,
    StichwortSchreiber, VerarbeitungsTracker).

    Validates: Requirements 4.1, 4.2, 5.1, 7.5
    """

    @staticmethod
    def _create_foto_files(tmp_path, names: list[str]) -> list[FotoEintrag]:
        """Create dummy photo files and return FotoEintrag list."""
        fotos = []
        for idx, name in enumerate(names, start=1):
            path = tmp_path / name
            path.write_bytes(b"\xff\xd8dummy")
            fotos.append(FotoEintrag(image_id=idx, file_path=str(path)))
        return fotos

    def test_batch_with_gps_photos(self, tmp_path):
        """Batch processes photos with GPS: standort keywords merged with KI keywords.

        Validates: Req 4.1 (standort keywords added), 4.2 (no duplicates), 5.1 (standort in prompt)
        """
        fotos = self._create_foto_files(tmp_path, ["berlin.jpg", "muenchen.jpg"])

        # GPS tags for Berlin
        berlin_tags = _make_gps_tags(
            lat_deg=52.0, lat_min=31.0, lat_sec=12.0, lat_ref="N",
            lon_deg=13.0, lon_min=24.0, lon_sec=17.0, lon_ref="E",
        )
        # GPS tags for München
        muenchen_tags = _make_gps_tags(
            lat_deg=48.0, lat_min=8.0, lat_sec=0.0, lat_ref="N",
            lon_deg=11.0, lon_min=34.0, lon_sec=0.0, lon_ref="E",
        )

        # Map file paths to their GPS tags
        exif_tags_map = {
            fotos[0].file_path: berlin_tags,
            fotos[1].file_path: muenchen_tags,
        }

        def mock_process_file(f, details=False):
            path = f.name
            return exif_tags_map.get(path, {})

        # Reverse geocoder results per coordinate
        def mock_rg_search(coords):
            lat, lon = coords[0]
            if lat > 50:  # Berlin area
                return [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
            else:  # München area
                return [{"name": "München", "admin1": "Bayern", "cc": "DE"}]

        mock_rg = MagicMock()
        mock_rg.search.side_effect = mock_rg_search

        # Mock OllamaClient
        mock_ollama = MagicMock()
        mock_ollama.analyse_bild.side_effect = [
            ["Architektur", "Nacht"],       # Berlin photo
            ["Alpen", "Kirche"],            # München photo
        ]

        mock_schreiber = MagicMock()
        mock_tracker = MagicMock()

        gps_leser = GpsLeser()
        standort_resolver = StandortResolver()

        processor = BatchProcessor(
            ollama=mock_ollama,
            schreiber=mock_schreiber,
            tracker=mock_tracker,
            model_name="llava",
            model_version="1.0",
            gps_leser=gps_leser,
            standort_resolver=standort_resolver,
        )

        with (
            patch("exifread.process_file", side_effect=mock_process_file),
            patch.dict("sys.modules", {"reverse_geocoder": mock_rg}),
        ):
            ergebnis = processor.batch_verarbeiten(fotos)

        # Both photos processed successfully
        assert ergebnis.verarbeitet == 2
        assert ergebnis.fehler == 0

        # Verify OllamaClient.analyse_bild was called with standort_daten (Req 5.1)
        assert mock_ollama.analyse_bild.call_count == 2
        berlin_call_standort = mock_ollama.analyse_bild.call_args_list[0][0][1]
        assert isinstance(berlin_call_standort, StandortDaten)
        assert berlin_call_standort.stadt == "Berlin"

        muenchen_call_standort = mock_ollama.analyse_bild.call_args_list[1][0][1]
        assert isinstance(muenchen_call_standort, StandortDaten)
        assert muenchen_call_standort.stadt == "München"

        # Verify StichwortSchreiber received merged keywords (Req 4.1, 4.2)
        assert mock_schreiber.stichwörter_schreiben.call_count == 2

        berlin_keywords = mock_schreiber.stichwörter_schreiben.call_args_list[0][0][1]
        assert "Berlin" in berlin_keywords
        assert "DE" in berlin_keywords
        assert "Architektur" in berlin_keywords
        assert "Nacht" in berlin_keywords
        # Standort first (Req 4.1)
        assert berlin_keywords.index("Berlin") < berlin_keywords.index("Architektur")
        # No duplicates (Req 4.2)
        assert len(berlin_keywords) == len(set(berlin_keywords))

        muenchen_keywords = mock_schreiber.stichwörter_schreiben.call_args_list[1][0][1]
        assert "München" in muenchen_keywords
        assert "Bayern" in muenchen_keywords
        assert "DE" in muenchen_keywords
        assert "Alpen" in muenchen_keywords
        assert "Kirche" in muenchen_keywords
        assert len(muenchen_keywords) == len(set(muenchen_keywords))

        # Tracker called for each photo
        assert mock_tracker.verarbeitung_speichern.call_count == 2

    def test_batch_mixed_gps_and_no_gps(self, tmp_path):
        """Batch with some photos having GPS and some without.

        Validates: Req 7.5 (photos without GPS processed without standort keywords)
        """
        fotos = self._create_foto_files(
            tmp_path, ["with_gps.jpg", "no_gps.jpg", "also_gps.jpg"]
        )

        berlin_tags = _make_gps_tags(
            lat_deg=52.0, lat_min=31.0, lat_sec=12.0, lat_ref="N",
            lon_deg=13.0, lon_min=24.0, lon_sec=17.0, lon_ref="E",
        )
        sydney_tags = _make_gps_tags(
            lat_deg=33.0, lat_min=52.0, lat_sec=10.0, lat_ref="S",
            lon_deg=151.0, lon_min=12.0, lon_sec=30.0, lon_ref="E",
        )

        exif_tags_map = {
            fotos[0].file_path: berlin_tags,       # with GPS
            fotos[1].file_path: {},                 # no GPS
            fotos[2].file_path: sydney_tags,        # with GPS
        }

        def mock_process_file(f, details=False):
            path = f.name
            return exif_tags_map.get(path, {})

        def mock_rg_search(coords):
            lat, lon = coords[0]
            if lat > 50:
                return [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
            else:
                return [{"name": "Sydney", "admin1": "New South Wales", "cc": "AU"}]

        mock_rg = MagicMock()
        mock_rg.search.side_effect = mock_rg_search

        mock_ollama = MagicMock()
        mock_ollama.analyse_bild.side_effect = [
            ["Architektur"],     # with_gps.jpg
            ["Portrait"],        # no_gps.jpg
            ["Opera House"],     # also_gps.jpg
        ]

        mock_schreiber = MagicMock()
        mock_tracker = MagicMock()

        gps_leser = GpsLeser()
        standort_resolver = StandortResolver()

        processor = BatchProcessor(
            ollama=mock_ollama,
            schreiber=mock_schreiber,
            tracker=mock_tracker,
            model_name="llava",
            model_version="1.0",
            gps_leser=gps_leser,
            standort_resolver=standort_resolver,
        )

        with (
            patch("exifread.process_file", side_effect=mock_process_file),
            patch.dict("sys.modules", {"reverse_geocoder": mock_rg}),
        ):
            ergebnis = processor.batch_verarbeiten(fotos)

        # All 3 photos processed
        assert ergebnis.verarbeitet == 3
        assert ergebnis.fehler == 0

        # Photo 1 (with GPS): standort keywords present
        kw_with_gps = mock_schreiber.stichwörter_schreiben.call_args_list[0][0][1]
        assert "Berlin" in kw_with_gps
        assert "DE" in kw_with_gps
        assert "Architektur" in kw_with_gps

        # Photo 2 (no GPS): only KI keywords, no standort (Req 7.5)
        kw_no_gps = mock_schreiber.stichwörter_schreiben.call_args_list[1][0][1]
        assert kw_no_gps == ["Portrait"]

        # Photo 3 (with GPS): standort keywords present
        kw_also_gps = mock_schreiber.stichwörter_schreiben.call_args_list[2][0][1]
        assert "Sydney" in kw_also_gps
        assert "New South Wales" in kw_also_gps
        assert "AU" in kw_also_gps
        assert "Opera House" in kw_also_gps

        # OllamaClient called with standort_daten for GPS photos, None for no-GPS
        calls = mock_ollama.analyse_bild.call_args_list
        assert isinstance(calls[0][0][1], StandortDaten)  # with_gps → StandortDaten
        assert calls[1][0][1] is None                      # no_gps → None
        assert isinstance(calls[2][0][1], StandortDaten)  # also_gps → StandortDaten

    def test_batch_gps_read_for_each_photo(self, tmp_path):
        """GPS is read individually for each photo in the batch."""
        fotos = self._create_foto_files(tmp_path, ["a.jpg", "b.jpg"])

        tags_a = _make_gps_tags(
            lat_deg=52.0, lat_min=0.0, lat_sec=0.0, lat_ref="N",
            lon_deg=13.0, lon_min=0.0, lon_sec=0.0, lon_ref="E",
        )
        tags_b = _make_gps_tags(
            lat_deg=48.0, lat_min=0.0, lat_sec=0.0, lat_ref="N",
            lon_deg=11.0, lon_min=0.0, lon_sec=0.0, lon_ref="E",
        )

        exif_tags_map = {
            fotos[0].file_path: tags_a,
            fotos[1].file_path: tags_b,
        }

        def mock_process_file(f, details=False):
            return exif_tags_map.get(f.name, {})

        def mock_rg_search(coords):
            return [{"name": "City", "admin1": "Region", "cc": "XX"}]

        mock_rg = MagicMock()
        mock_rg.search.side_effect = mock_rg_search

        mock_ollama = MagicMock()
        mock_ollama.analyse_bild.return_value = ["keyword"]
        mock_schreiber = MagicMock()
        mock_tracker = MagicMock()

        gps_leser = GpsLeser()
        standort_resolver = StandortResolver()

        processor = BatchProcessor(
            ollama=mock_ollama,
            schreiber=mock_schreiber,
            tracker=mock_tracker,
            model_name="llava",
            model_version="1.0",
            gps_leser=gps_leser,
            standort_resolver=standort_resolver,
        )

        with (
            patch("exifread.process_file", side_effect=mock_process_file),
            patch.dict("sys.modules", {"reverse_geocoder": mock_rg}),
        ):
            ergebnis = processor.batch_verarbeiten(fotos)

        assert ergebnis.verarbeitet == 2

        # reverse_geocoder.search called twice (once per photo with GPS)
        assert mock_rg.search.call_count == 2

        # Each photo got different GPS coordinates resolved
        first_coords = mock_rg.search.call_args_list[0][0][0][0]
        second_coords = mock_rg.search.call_args_list[1][0][0][0]
        assert first_coords != second_coords

    def test_batch_standort_keywords_no_empty_strings(self, tmp_path):
        """Empty standort fields are filtered from merged keywords (Req 4.4)."""
        fotos = self._create_foto_files(tmp_path, ["foto.jpg"])

        gps_tags = _make_gps_tags(
            lat_deg=52.0, lat_min=31.0, lat_sec=12.0, lat_ref="N",
            lon_deg=13.0, lon_min=24.0, lon_sec=17.0, lon_ref="E",
        )

        exif_tags_map = {fotos[0].file_path: gps_tags}

        def mock_process_file(f, details=False):
            return exif_tags_map.get(f.name, {})

        # Reverse geocoder returns empty region
        mock_rg = MagicMock()
        mock_rg.search.return_value = [{"name": "Berlin", "admin1": "", "cc": "DE"}]

        mock_ollama = MagicMock()
        mock_ollama.analyse_bild.return_value = ["Nacht"]
        mock_schreiber = MagicMock()
        mock_tracker = MagicMock()

        gps_leser = GpsLeser()
        standort_resolver = StandortResolver()

        processor = BatchProcessor(
            ollama=mock_ollama,
            schreiber=mock_schreiber,
            tracker=mock_tracker,
            model_name="llava",
            model_version="1.0",
            gps_leser=gps_leser,
            standort_resolver=standort_resolver,
        )

        with (
            patch("exifread.process_file", side_effect=mock_process_file),
            patch.dict("sys.modules", {"reverse_geocoder": mock_rg}),
        ):
            ergebnis = processor.batch_verarbeiten(fotos)

        assert ergebnis.verarbeitet == 1
        written_keywords = mock_schreiber.stichwörter_schreiben.call_args[0][1]
        assert "" not in written_keywords
        assert "Berlin" in written_keywords
        assert "DE" in written_keywords
        assert "Nacht" in written_keywords
