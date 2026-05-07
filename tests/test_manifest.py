from pathlib import Path

from lmit.manifest import Manifest
from lmit.scanner import ScannedFile


def test_manifest_detects_unchanged_success(tmp_path: Path):
    output = tmp_path / "output.md"
    output.write_text("ok", encoding="utf-8")
    scanned = ScannedFile(
        path=(tmp_path / "input.txt").resolve(),
        relative_path=Path("input.txt"),
        suffix=".txt",
        size=3,
        mtime_ns=10,
        sha256="abc",
    )
    manifest = Manifest(tmp_path / "manifest.json")

    manifest.update(scanned, output, status="success")

    assert manifest.is_unchanged_success(scanned)


def test_manifest_treats_conversion_key_change_as_changed(tmp_path: Path):
    output = tmp_path / "output.md"
    output.write_text("ok", encoding="utf-8")
    scanned = ScannedFile(
        path=(tmp_path / "input.txt").resolve(),
        relative_path=Path("input.txt"),
        suffix=".txt",
        size=3,
        mtime_ns=10,
        sha256="abc",
    )
    manifest = Manifest(tmp_path / "manifest.json")

    manifest.update(scanned, output, status="success", conversion_key="without-url-fetch")

    assert not manifest.is_unchanged_success(
        scanned,
        conversion_key="with-url-fetch",
    )


def test_manifest_uses_namespaced_key_for_multiple_roots(tmp_path: Path):
    output = tmp_path / "output" / "input_a" / "note.md"
    output.parent.mkdir(parents=True)
    output.write_text("ok", encoding="utf-8")
    scanned = ScannedFile(
        path=(tmp_path / "input_a" / "note.txt").resolve(),
        relative_path=Path("note.txt"),
        suffix=".txt",
        size=3,
        mtime_ns=10,
        sha256="abc",
        source_root=(tmp_path / "input_a").resolve(),
        source_id="input_a",
    )
    manifest = Manifest(tmp_path / "manifest.json")

    manifest.update(scanned, output, status="success")

    assert "input_a/note.txt" in manifest.records
    assert manifest.is_unchanged_completed(scanned)


def test_manifest_treats_unchanged_partial_as_completed(tmp_path: Path):
    output = tmp_path / "output.md"
    output.write_text("partial", encoding="utf-8")
    scanned = ScannedFile(
        path=(tmp_path / "input.txt").resolve(),
        relative_path=Path("input.txt"),
        suffix=".txt",
        size=3,
        mtime_ns=10,
        sha256="abc",
    )
    manifest = Manifest(tmp_path / "manifest.json")

    manifest.update(scanned, output, status="partial")

    assert not manifest.is_unchanged_success(scanned)
    assert manifest.is_unchanged_completed(scanned)


def test_manifest_returns_unchanged_completed_output_path(tmp_path: Path):
    output = tmp_path / "Title__input.md"
    output.write_text("ok", encoding="utf-8")
    scanned = ScannedFile(
        path=(tmp_path / "input.txt").resolve(),
        relative_path=Path("input.txt"),
        suffix=".txt",
        size=3,
        mtime_ns=10,
        sha256="abc",
    )
    manifest = Manifest(tmp_path / "manifest.json")

    manifest.update(scanned, output, status="success", conversion_key="key")

    assert manifest.unchanged_completed_output_path(
        scanned,
        conversion_key="key",
    ) == output.resolve()


def test_manifest_treats_missing_output_as_unchanged_completed(tmp_path: Path):
    output = tmp_path / "moved-output.md"
    scanned = ScannedFile(
        path=(tmp_path / "input.txt").resolve(),
        relative_path=Path("input.txt"),
        suffix=".txt",
        size=3,
        mtime_ns=10,
        sha256="abc",
    )
    manifest = Manifest(tmp_path / "manifest.json")

    manifest.update(scanned, output, status="success", conversion_key="key")

    assert manifest.is_unchanged_completed(scanned, conversion_key="key")
    assert manifest.unchanged_completed_output_path(scanned, conversion_key="key") == output.resolve()


def test_manifest_marks_missing_without_deleting_output(tmp_path: Path):
    output = tmp_path / "output.md"
    output.write_text("ok", encoding="utf-8")
    scanned = ScannedFile(
        path=(tmp_path / "input.txt").resolve(),
        relative_path=Path("input.txt"),
        suffix=".txt",
        size=3,
        mtime_ns=10,
        sha256="abc",
    )
    manifest = Manifest(tmp_path / "manifest.json")
    manifest.update(scanned, output, status="success")

    missing = manifest.mark_missing(set())

    record = manifest.records["input.txt"]
    assert missing == ["input.txt"]
    assert record.status == "missing"
    assert record.output_path == str(output.resolve())
    assert record.last_error_type == "source_missing"
    assert record.retryable is False
    assert output.exists()


def test_manifest_retry_candidate_respects_retryable_flag(tmp_path: Path):
    output = tmp_path / "output.md"
    output.write_text("ok", encoding="utf-8")
    scanned = ScannedFile(
        path=(tmp_path / "input.txt").resolve(),
        relative_path=Path("input.txt"),
        suffix=".txt",
        size=3,
        mtime_ns=10,
        sha256="abc",
    )
    manifest = Manifest(tmp_path / "manifest.json")

    manifest.update(scanned, output, status="failed", retryable=True)
    assert manifest.is_retry_candidate(scanned)

    manifest.update(scanned, output, status="failed", retryable=False)
    assert not manifest.is_retry_candidate(scanned)

    manifest.update(scanned, output, status="partial", retryable=None)
    assert manifest.is_retry_candidate(scanned)


def test_manifest_loads_older_records_without_new_fields(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        """
{
  "version": 1,
  "records": {
    "input.txt": {
      "relative_path": "input.txt",
      "output_path": "output.md",
      "size": 3,
      "mtime_ns": 10,
      "sha256": "abc",
      "status": "failed",
      "conversion_key": "key",
      "error": "old"
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    manifest = Manifest.load(manifest_path)

    record = manifest.records["input.txt"]
    assert record.last_error_type is None
    assert record.retryable is None
    assert record.missing_at_utc is None
