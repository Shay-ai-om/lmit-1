from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
import hashlib
import re
import time

from .config import AppConfig


@dataclass(frozen=True)
class ScannedFile:
    path: Path
    relative_path: Path
    suffix: str
    size: int
    mtime_ns: int
    sha256: str
    source_root: Path | None = None
    source_id: str | None = None

    @property
    def output_relative_path(self) -> Path:
        if self.source_id:
            return Path(self.source_id) / self.relative_path
        return self.relative_path

    @property
    def manifest_key(self) -> str:
        return self.output_relative_path.as_posix()


@dataclass
class ScanSummary:
    input_roots: int = 0
    scanned_items: int = 0
    matched_files: int = 0
    skipped_dirs: int = 0
    skipped_unsupported: int = 0
    skipped_excluded: int = 0
    skipped_unstable: int = 0
    present_manifest_keys: set[str] = field(default_factory=set)


def scan_input(cfg: AppConfig) -> tuple[list[ScannedFile], ScanSummary]:
    summary = ScanSummary()
    files: list[ScannedFile] = []
    roots = tuple(path.resolve() for path in cfg.paths.input_dirs)
    source_ids = _source_ids_for_roots(roots)
    summary.input_roots = len(roots)
    now_ns = time.time_ns()

    for root, source_id in zip(roots, source_ids, strict=True):
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"input_dir does not exist or is not a directory: {root}")

        iterator = root.rglob("*") if cfg.scan.recursive else root.glob("*")
        for path in iterator:
            summary.scanned_items += 1
            relative = path.resolve().relative_to(root)

            if path.is_dir():
                summary.skipped_dirs += 1
                continue

            rel_posix = relative.as_posix()
            if _is_excluded(rel_posix, cfg.scan.exclude_globs):
                summary.skipped_excluded += 1
                continue

            suffix = path.suffix.lower()
            if suffix not in cfg.scan.supported_exts:
                summary.skipped_unsupported += 1
                continue

            stat = path.stat()
            summary.present_manifest_keys.add(_manifest_key(relative, source_id))
            if _is_unstable(stat.st_mtime_ns, now_ns, cfg.polling.stable_seconds, cfg.polling.enabled):
                summary.skipped_unstable += 1
                continue

            files.append(
                ScannedFile(
                    path=path.resolve(),
                    relative_path=relative,
                    suffix=suffix,
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    sha256=_sha256(path),
                    source_root=root,
                    source_id=source_id,
                )
            )
            summary.matched_files += 1

    return files, summary


def _is_excluded(relative_posix: str, patterns: list[str]) -> bool:
    return any(
        fnmatch(relative_posix, pattern) or fnmatch(Path(relative_posix).name, pattern)
        for pattern in patterns
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_unstable(
    mtime_ns: int,
    now_ns: int,
    stable_seconds: int,
    polling_enabled: bool,
) -> bool:
    if not polling_enabled or stable_seconds <= 0:
        return False
    return now_ns - mtime_ns < stable_seconds * 1_000_000_000


def _manifest_key(relative_path: Path, source_id: str | None) -> str:
    if source_id:
        return (Path(source_id) / relative_path).as_posix()
    return relative_path.as_posix()


def _source_ids_for_roots(roots: tuple[Path, ...]) -> list[str | None]:
    if len(roots) == 1:
        return [None]

    used: dict[str, int] = {}
    source_ids: list[str] = []
    for root in roots:
        base = _safe_source_id(root.name or "input")
        count = used.get(base, 0) + 1
        used[base] = count
        source_ids.append(base if count == 1 else f"{base}-{count}")
    return source_ids


def _safe_source_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-_")
    return normalized or "input"
