from pathlib import Path

import pytest

from lmit.path_safety import PathSafetyError, ensure_within_root, output_path_for


def test_output_path_stays_under_output_root(tmp_path: Path):
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    source = input_root / "nested" / "note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("hello", encoding="utf-8")

    assert output_path_for(input_root, output_root, source) == (
        output_root / "nested" / "note.md"
    ).resolve()


def test_output_path_can_use_namespaced_relative_path(tmp_path: Path):
    input_root = tmp_path / "input_a"
    output_root = tmp_path / "output"
    source = input_root / "note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("hello", encoding="utf-8")

    assert output_path_for(
        input_root,
        output_root,
        source,
        Path("input_a") / "note.txt",
    ) == (output_root / "input_a" / "note.md").resolve()


def test_ensure_within_root_rejects_escape(tmp_path: Path):
    with pytest.raises(PathSafetyError):
        ensure_within_root(tmp_path / "elsewhere" / "x.md", tmp_path / "output")
