from __future__ import annotations

from fnmatch import fnmatch

from lmit.scanner import ScannedFile


def filter_scanned_files(
    files: list[ScannedFile],
    patterns: tuple[str, ...],
) -> list[ScannedFile]:
    normalized_patterns = [pattern.replace("\\", "/") for pattern in patterns]
    return [
        scanned
        for scanned in files
        if any(matches_scanned_file(scanned, pattern) for pattern in normalized_patterns)
    ]


def matches_scanned_file(scanned: ScannedFile, pattern: str) -> bool:
    candidates = {
        scanned.manifest_key,
        scanned.relative_path.as_posix(),
        scanned.path.name,
    }
    return any(fnmatch(candidate, pattern) for candidate in candidates)
