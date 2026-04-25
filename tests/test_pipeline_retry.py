from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from lmit.config import PublicFetchConfig, default_config, with_overrides
from lmit.manifest import Manifest
from lmit import pipeline
from lmit.pipeline import run_convert
from lmit.scanner import ScannedFile


def _cfg(tmp_path: Path):
    cfg = default_config(cwd=tmp_path)
    return with_overrides(
        cfg,
        input_dirs=[str(tmp_path / "input")],
        output_dir=str(tmp_path / "output" / "raw"),
        work_dir=str(tmp_path / "work"),
        fetch_urls=False,
    )


def test_run_convert_marks_missing_manifest_records(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output = tmp_path / "output" / "raw" / "gone.md"
    output.parent.mkdir(parents=True)
    output.write_text("old", encoding="utf-8")
    manifest_path = tmp_path / "work" / "manifest.json"
    manifest = Manifest(manifest_path)
    manifest.update(
        ScannedFile(
            path=(input_dir / "gone.txt").resolve(),
            relative_path=Path("gone.txt"),
            suffix=".txt",
            size=3,
            mtime_ns=1,
            sha256="abc",
        ),
        output,
        status="success",
    )
    manifest.save()

    code = run_convert(_cfg(tmp_path))

    updated = Manifest.load(manifest_path)
    assert code == 0
    assert updated.records["gone.txt"].status == "missing"
    assert updated.records["gone.txt"].last_error_type == "source_missing"
    assert updated.records["gone.txt"].retryable is False
    assert output.exists()


def test_run_convert_retry_failed_filters_manifest_candidates(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    failed = input_dir / "failed.md"
    skipped = input_dir / "skipped.md"
    failed.write_text("retry me", encoding="utf-8")
    skipped.write_text("leave me", encoding="utf-8")

    cfg = with_overrides(_cfg(tmp_path), retry_failed=True, overwrite=True)
    manifest_path = tmp_path / "work" / "manifest.json"
    manifest = Manifest(manifest_path)
    manifest.update(
        ScannedFile(
            path=failed.resolve(),
            relative_path=Path("failed.md"),
            suffix=".md",
            size=failed.stat().st_size,
            mtime_ns=failed.stat().st_mtime_ns,
            sha256="x",
        ),
        tmp_path / "output" / "raw" / "failed.md",
        status="failed",
        retryable=True,
    )
    manifest.update(
        ScannedFile(
            path=skipped.resolve(),
            relative_path=Path("skipped.md"),
            suffix=".md",
            size=skipped.stat().st_size,
            mtime_ns=skipped.stat().st_mtime_ns,
            sha256="y",
        ),
        tmp_path / "output" / "raw" / "skipped.md",
        status="success",
    )
    manifest.save()

    code = run_convert(cfg)

    assert code == 0
    assert (tmp_path / "output" / "raw" / "failed.md").exists()
    assert not (tmp_path / "output" / "raw" / "skipped.md").exists()


def test_run_convert_does_not_mark_unstable_source_missing(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / "syncing.md"
    source.write_text("still syncing", encoding="utf-8")
    output = tmp_path / "output" / "raw" / "syncing.md"
    output.parent.mkdir(parents=True)
    output.write_text("old", encoding="utf-8")

    cfg = _cfg(tmp_path)
    cfg = replace(cfg, polling=replace(cfg.polling, enabled=True, stable_seconds=60))
    manifest_path = tmp_path / "work" / "manifest.json"
    manifest = Manifest(manifest_path)
    manifest.update(
        ScannedFile(
            path=source.resolve(),
            relative_path=Path("syncing.md"),
            suffix=".md",
            size=source.stat().st_size,
            mtime_ns=source.stat().st_mtime_ns,
            sha256="abc",
        ),
        output,
        status="success",
    )
    manifest.save()

    code = run_convert(cfg)

    updated = Manifest.load(manifest_path)
    assert code == 0
    assert updated.records["syncing.md"].status == "success"


def test_run_convert_passes_public_fetch_config_to_public_url_fetcher(
    tmp_path: Path,
    monkeypatch,
):
    captured: dict[str, object] = {}

    class FakePublicUrlFetcher:
        def __init__(self, adapter, *, work_dir=None, report=None, public_fetch=None, **kwargs):
            captured["adapter"] = adapter
            captured["work_dir"] = work_dir
            captured["report"] = report
            captured["public_fetch"] = public_fetch

        def fetch(self, url: str) -> str:
            raise AssertionError("public fetch should not run in this test")

    monkeypatch.setattr(pipeline, "PublicUrlFetcher", FakePublicUrlFetcher)

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    cfg = _cfg(tmp_path)
    cfg = replace(
        cfg,
        public_fetch=PublicFetchConfig(
            provider="legacy",
            enable_scrapling=False,
            enable_scrapling_dynamic=False,
            scrapling_cleanup="none",
            scrapling_block_ads=False,
            request_timeout_seconds=12,
            navigation_timeout_ms=15000,
            min_meaningful_chars=123,
        ),
    )

    code = run_convert(cfg)

    assert code == 0
    assert captured["work_dir"] == cfg.paths.work_dir
    assert captured["public_fetch"] == cfg.public_fetch
