"""Property-basierte Tests und Unit-Tests für den KatalogLeser."""

from __future__ import annotations

import sqlite3

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lightroom_ollama_keywords.errors import KatalogError
from lightroom_ollama_keywords.katalog_leser import KatalogLeser


# --- Hypothesis strategies for Lightroom catalog data ---

# Safe text for path segments: letters, digits, underscores — no dots or slashes
_path_segment = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip() == s)

# absolutePath always ends with '/' (Lightroom convention)
_absolute_path = st.builds(
    lambda parts: "/" + "/".join(parts) + "/",
    st.lists(_path_segment, min_size=1, max_size=3),
)

# pathFromRoot always ends with '/' (relative folder path inside root)
_path_from_root = st.builds(
    lambda parts: "/".join(parts) + "/",
    st.lists(_path_segment, min_size=0, max_size=3),
)

_base_name = _path_segment

_extension = st.sampled_from(["jpg", "jpeg", "png", "tiff", "cr2", "nef", "arw", "dng"])


@st.composite
def _catalog_entries(draw):
    """Generate a list of consistent Lightroom catalog entries.

    Each entry is a tuple of (absolutePath, pathFromRoot, baseName, extension).
    Multiple images may share the same folder/root folder.
    """
    n = draw(st.integers(min_value=1, max_value=10))

    # Pre-generate a small pool of root folders and sub-folders for reuse
    num_roots = draw(st.integers(min_value=1, max_value=max(1, n)))
    roots = [draw(_absolute_path) for _ in range(num_roots)]

    num_folders = draw(st.integers(min_value=1, max_value=max(1, n)))
    folders = [
        (draw(st.sampled_from(roots)), draw(_path_from_root))
        for _ in range(num_folders)
    ]

    entries = []
    for _ in range(n):
        root_abs, pfr = draw(st.sampled_from(folders))
        bn = draw(_base_name)
        ext = draw(_extension)
        entries.append((root_abs, pfr, bn, ext))

    return entries


def _create_lightroom_catalog(db_path: str, entries: list[tuple[str, str, str, str]]) -> None:
    """Create a SQLite file with the Lightroom schema and populate it with entries.

    Each entry is (absolutePath, pathFromRoot, baseName, extension).
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE AgLibraryRootFolder (
            id_local INTEGER PRIMARY KEY,
            absolutePath TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE AgLibraryFolder (
            id_local INTEGER PRIMARY KEY,
            pathFromRoot TEXT NOT NULL,
            rootFolder INTEGER NOT NULL REFERENCES AgLibraryRootFolder(id_local)
        )
    """)
    cur.execute("""
        CREATE TABLE AgLibraryFile (
            id_local INTEGER PRIMARY KEY,
            baseName TEXT NOT NULL,
            extension TEXT NOT NULL,
            folder INTEGER NOT NULL REFERENCES AgLibraryFolder(id_local)
        )
    """)
    cur.execute("""
        CREATE TABLE Adobe_images (
            id_local INTEGER PRIMARY KEY,
            rootFile INTEGER NOT NULL REFERENCES AgLibraryFile(id_local)
        )
    """)

    # De-duplicate root folders and folders to build proper relational data
    root_map: dict[str, int] = {}
    folder_map: dict[tuple[int, str], int] = {}

    root_id = 0
    folder_id = 0
    file_id = 0
    image_id = 0

    for abs_path, path_from_root, base_name, extension in entries:
        # Root folder
        if abs_path not in root_map:
            root_id += 1
            root_map[abs_path] = root_id
            cur.execute(
                "INSERT INTO AgLibraryRootFolder (id_local, absolutePath) VALUES (?, ?)",
                (root_id, abs_path),
            )
        rid = root_map[abs_path]

        # Folder
        folder_key = (rid, path_from_root)
        if folder_key not in folder_map:
            folder_id += 1
            folder_map[folder_key] = folder_id
            cur.execute(
                "INSERT INTO AgLibraryFolder (id_local, pathFromRoot, rootFolder) VALUES (?, ?, ?)",
                (folder_id, path_from_root, rid),
            )
        fid = folder_map[folder_key]

        # File
        file_id += 1
        cur.execute(
            "INSERT INTO AgLibraryFile (id_local, baseName, extension, folder) VALUES (?, ?, ?, ?)",
            (file_id, base_name, extension, fid),
        )

        # Image
        image_id += 1
        cur.execute(
            "INSERT INTO Adobe_images (id_local, rootFile) VALUES (?, ?)",
            (image_id, file_id),
        )

    conn.commit()
    conn.close()


class TestKatalogPfadZusammensetzung:
    """Property 1: Katalog-Pfad-Zusammensetzung.

    **Validates: Requirements 1.1**
    """

    @given(entries=_catalog_entries())
    @settings(max_examples=100)
    def test_file_path_equals_concatenation_and_count_matches(
        self, entries: list[tuple[str, str, str, str]], tmp_path_factory
    ):
        """For all valid catalog entries, the file path should equal
        absolutePath + pathFromRoot + baseName + '.' + extension,
        and the number of results should equal the number of Adobe_images entries."""
        tmp_dir = tmp_path_factory.mktemp("catalog")
        db_path = str(tmp_dir / "test.lrcat")

        _create_lightroom_catalog(db_path, entries)

        leser = KatalogLeser(db_path)
        try:
            fotos = leser.alle_fotos_lesen()

            # Count property: number of results == number of Adobe_images entries
            assert len(fotos) == len(entries)

            # Path composition property: each file_path == absolutePath + pathFromRoot + baseName + '.' + extension
            expected_paths = [
                abs_path + path_from_root + base_name + "." + ext
                for abs_path, path_from_root, base_name, ext in entries
            ]

            actual_paths = [f.file_path for f in fotos]

            # Sort both lists since SQL doesn't guarantee order
            assert sorted(actual_paths) == sorted(expected_paths)
        finally:
            leser.close()


class TestKatalogLeserFehler:
    """Unit-Tests für KatalogLeser-Fehlerfälle.

    Anforderungen: 1.4
    """

    def test_katalog_error_bei_nicht_existierender_datei(self):
        """KatalogError should be raised when the catalog file does not exist,
        and the error message should contain the file path."""
        fake_path = "/does/not/exist/catalog.lrcat"
        with pytest.raises(KatalogError, match=fake_path):
            KatalogLeser(fake_path)
