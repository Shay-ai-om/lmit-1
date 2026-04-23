from pathlib import Path

from lmit.file_selection import filter_scanned_files
from lmit.scanner import ScannedFile


def _scanned(relative: str) -> ScannedFile:
    return ScannedFile(
        path=(Path("input") / relative).resolve(),
        relative_path=Path(relative),
        suffix=Path(relative).suffix,
        size=1,
        mtime_ns=1,
        sha256="abc",
    )


def test_filter_scanned_files_matches_relative_path_glob():
    files = [
        _scanned("AI/20260413_072753.txt"),
        _scanned("AI/other.txt"),
        _scanned("root.txt"),
    ]

    filtered = filter_scanned_files(files, ("AI/20260413_*.txt",))

    assert [item.relative_path.as_posix() for item in filtered] == ["AI/20260413_072753.txt"]


def test_filter_scanned_files_matches_filename():
    files = [_scanned("AI/20260418_162909.txt"), _scanned("AI/other.txt")]

    filtered = filter_scanned_files(files, ("20260418_162909.txt",))

    assert [item.relative_path.as_posix() for item in filtered] == ["AI/20260418_162909.txt"]
