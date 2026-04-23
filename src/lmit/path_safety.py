from __future__ import annotations

from pathlib import Path


class PathSafetyError(ValueError):
    """Raised when a computed output path escapes the allowed root."""


def ensure_within_root(path: Path, root: Path) -> Path:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path == resolved_root:
        return resolved_path
    if resolved_root not in resolved_path.parents:
        raise PathSafetyError(f"path escapes root: {resolved_path} not under {resolved_root}")
    return resolved_path


def output_path_for(
    input_root: Path,
    output_root: Path,
    source_path: Path,
    output_relative_path: Path | None = None,
) -> Path:
    relative = output_relative_path or source_path.resolve().relative_to(input_root.resolve())
    target = output_root / relative.with_suffix(".md")
    return ensure_within_root(target, output_root)


def safe_write_text(path: Path, root: Path, text: str) -> None:
    safe_path = ensure_within_root(path, root)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(text, encoding="utf-8")


def safe_unlink_file(path: Path, root: Path) -> None:
    safe_path = ensure_within_root(path, root)
    if safe_path.exists() and safe_path.is_file():
        safe_path.unlink()
