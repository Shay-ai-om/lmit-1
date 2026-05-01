from __future__ import annotations

import json
import os
from pathlib import Path

from lmit.cli import main
from lmit.config import PublicFetchConfig
from lmit.converters.txt_urls import convert_txt_with_urls
from lmit.fetchers.public_url import PublicUrlFetcher
from lmit.reports import (
    ConversionReport,
    diagnose_report,
    latest_report_path,
    load_report,
    render_report,
    render_report_json,
)


LONG_TEXT = "Meaningful public page content. " * 12


class DummyAdapter:
    def __init__(self, *, url_result: str = LONG_TEXT):
        self.url_result = url_result
        self.convert_url_calls: list[str] = []

    def convert_url(self, url: str) -> str:
        self.convert_url_calls.append(url)
        return self.url_result


class DummyScraplingFetcher:
    def __init__(
        self,
        *,
        static_result: str = LONG_TEXT,
        dynamic_result: str = LONG_TEXT,
        stealthy_result: str = LONG_TEXT,
    ):
        self.static_result = static_result
        self.dynamic_result = dynamic_result
        self.stealthy_result = stealthy_result

    def fetch_static(self, url: str) -> str:
        return self.static_result

    def fetch_dynamic(self, url: str) -> str:
        return self.dynamic_result

    def fetch_stealthy(self, url: str) -> str:
        return self.stealthy_result


class BrowserOverrideFetcher(PublicUrlFetcher):
    def __init__(self, *args, browser_result: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.browser_result = browser_result

    def _fetch_with_browser(self, url: str) -> str:
        return self.browser_result


class DummySessionFetcher:
    def fetch(self, url: str, site: str) -> str:
        raise AssertionError("session fetch should not be used in this test")


class DummySessionManager:
    def site_for_url(self, url: str):
        return None


class SnapshottingReport(ConversionReport):
    def __init__(self):
        super().__init__()
        self.snapshots: list[dict] = []

    def log(self, message: str) -> None:
        super().log(message)
        if "[URL-CONTENT-BLOCKED]" in message and self._running_json_path is not None:
            self.snapshots.append(
                json.loads(self._running_json_path.read_text(encoding="utf-8"))
            )


def _write_report(path: Path, *, stats: dict, log: list[str]) -> None:
    path.write_text(
        json.dumps({"stats": stats, "log": log}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_latest_report_path_uses_newest_json(tmp_path: Path):
    old = tmp_path / "conversion_report_20260420_010000.json"
    new = tmp_path / "conversion_report_20260420_020000.json"
    _write_report(old, stats={}, log=[])
    _write_report(new, stats={}, log=[])
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))

    assert latest_report_path(tmp_path) == new


def test_diagnose_report_groups_issue_lines(tmp_path: Path):
    path = tmp_path / "conversion_report_20260420_020000.json"
    _write_report(
        path,
        stats={
            "blank_output": 1,
            "url_fetch_failed": 1,
            "session_url_fetch_failed": 1,
        },
        log=[
            "[FAIL] note.txt: RuntimeError('boom')",
            "[PARTIAL] links.txt -> output.md",
            "[URL-CONTENT-BLOCKED] https://example.com",
            "[SESSION-EXPIRED] facebook: redirected to login",
            "[LOGIN-REQUIRED] facebook: opening login window",
            "[URL_FETCH_FAILED] https://example.com: TimeoutError()",
        ],
    )

    diagnostics = diagnose_report(load_report(path))

    assert diagnostics.failed == ["[FAIL] note.txt: RuntimeError('boom')"]
    assert diagnostics.partial == ["[PARTIAL] links.txt -> output.md"]
    assert diagnostics.blocked == ["[URL-CONTENT-BLOCKED] https://example.com"]
    assert diagnostics.session_expired == ["[SESSION-EXPIRED] facebook: redirected to login"]
    assert diagnostics.login_required == ["[LOGIN-REQUIRED] facebook: opening login window"]
    assert diagnostics.url_fetch_failed == [
        "[URL_FETCH_FAILED] https://example.com: TimeoutError()",
        "session_url_fetch_failed: 1",
    ]
    assert diagnostics.blank == ["blank_output: 1"]


def test_render_report_summary_and_json(tmp_path: Path):
    path = tmp_path / "conversion_report_20260420_020000.json"
    _write_report(
        path,
        stats={"scanned_items": 2, "matched_files": 1, "failed": 0},
        log=["[OK] note.txt -> note.md"],
    )
    report = load_report(path)

    summary = render_report(report, summary_only=True)
    payload = json.loads(render_report_json(report))

    assert "Stats:" in summary
    assert "- scanned_items: 2" in summary
    assert "Recent Log" not in summary
    assert payload["path"] == str(path.resolve())
    assert payload["diagnostics"]["failed"] == []


def test_render_report_summary_includes_public_url_pipeline_counters(tmp_path: Path):
    path = tmp_path / "conversion_report_20260420_020000.json"
    _write_report(
        path,
        stats={
            "public_url_scrapling_static_success": 1,
            "public_url_scrapling_dynamic_success": 2,
            "public_url_scrapling_stealthy_success": 3,
            "public_url_markitdown_success": 3,
            "public_url_playwright_success": 4,
            "public_url_quality_retry": 5,
            "public_url_blocked": 6,
            "public_url_blank": 7,
        },
        log=[],
    )

    summary = render_report(load_report(path), summary_only=True)

    assert "- public_url_scrapling_static_success: 1" in summary
    assert "- public_url_scrapling_dynamic_success: 2" in summary
    assert "- public_url_scrapling_stealthy_success: 3" in summary
    assert "- public_url_markitdown_success: 3" in summary
    assert "- public_url_playwright_success: 4" in summary
    assert "- public_url_quality_retry: 5" in summary
    assert "- public_url_blocked: 6" in summary
    assert "- public_url_blank: 7" in summary


def test_running_report_shows_scrapling_upgrade_counters(tmp_path: Path):
    report = ConversionReport()
    report.enable_running_report(tmp_path)
    fetcher = PublicUrlFetcher(
        DummyAdapter(),
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(provider="auto", enable_scrapling_dynamic=True),
        scrapling_fetcher=DummyScraplingFetcher(static_result="   ", dynamic_result=LONG_TEXT),
    )

    assert fetcher.fetch("https://example.com/article") == LONG_TEXT

    running_json = tmp_path / "conversion_report_running.json"
    running_md = tmp_path / "conversion_report_running.md"
    payload = json.loads(running_json.read_text(encoding="utf-8"))
    markdown = running_md.read_text(encoding="utf-8")

    assert payload["stats"]["public_url_scrapling_static_success"] == 0
    assert payload["stats"]["public_url_scrapling_dynamic_success"] == 1
    assert payload["stats"]["public_url_quality_retry"] == 1
    assert payload["stats"]["public_url_blank"] == 1
    assert payload["stats"]["public_url_blocked"] == 0
    assert "- public_url_scrapling_dynamic_success: 1" in markdown
    assert "- public_url_quality_retry: 1" in markdown
    assert "- [PUBLIC-FETCH-UPGRADE] url=https://example.com/article from_stage=scrapling_static upgrade=scrapling_dynamic reason=blank" in markdown


def test_running_report_shows_legacy_and_playwright_counters(tmp_path: Path):
    report = ConversionReport()
    report.enable_running_report(tmp_path)

    markitdown_fetcher = PublicUrlFetcher(
        DummyAdapter(url_result=LONG_TEXT),
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(provider="auto", enable_scrapling=False),
    )
    assert markitdown_fetcher.fetch("https://example.com/markitdown") == LONG_TEXT

    playwright_fetcher = BrowserOverrideFetcher(
        DummyAdapter(url_result="Checking your browser before accessing this page."),
        browser_result=LONG_TEXT,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(provider="auto", enable_scrapling=False),
    )
    assert playwright_fetcher.fetch("https://example.com/playwright") == LONG_TEXT

    payload = json.loads((tmp_path / "conversion_report_running.json").read_text(encoding="utf-8"))

    assert payload["stats"]["public_url_markitdown_success"] == 1
    assert payload["stats"]["public_url_playwright_success"] == 1
    assert payload["stats"]["public_url_quality_retry"] == 1
    assert payload["stats"]["public_url_blocked"] == 1
    assert payload["stats"]["public_url_blank"] == 0


def test_running_report_stays_coherent_during_txt_url_conversion(tmp_path: Path):
    source = tmp_path / "urls.txt"
    source.write_text("Check this out: https://example.com/article", encoding="utf-8")

    report = ConversionReport()
    report.enable_running_report(tmp_path)
    public_fetcher = PublicUrlFetcher(
        DummyAdapter(),
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(provider="auto", enable_scrapling=False),
    )

    result = convert_txt_with_urls(
        source,
        fetch_urls=True,
        public_fetcher=public_fetcher,
        session_fetcher=DummySessionFetcher(),
        session_manager=DummySessionManager(),
        report=report,
    )

    payload = json.loads((tmp_path / "conversion_report_running.json").read_text(encoding="utf-8"))

    assert result.failed_count == 0
    assert payload["stats"]["url_found"] == 1
    assert payload["stats"]["url_fetch_success"] == 1
    assert payload["stats"]["url_fetch_failed"] == 0
    assert payload["stats"]["public_url_markitdown_success"] == 1


def test_running_report_flushes_url_found_when_fetching_is_disabled(tmp_path: Path):
    source = tmp_path / "urls_disabled.txt"
    source.write_text(
        "Links: https://example.com/one and https://example.com/two",
        encoding="utf-8",
    )

    report = ConversionReport()
    report.enable_running_report(tmp_path)

    result = convert_txt_with_urls(
        source,
        fetch_urls=False,
        public_fetcher=PublicUrlFetcher(
            DummyAdapter(),
            work_dir=tmp_path,
            report=report,
            public_fetch=PublicFetchConfig(provider="auto", enable_scrapling=False),
        ),
        session_fetcher=DummySessionFetcher(),
        session_manager=DummySessionManager(),
        report=report,
    )

    payload = json.loads((tmp_path / "conversion_report_running.json").read_text(encoding="utf-8"))

    assert result.failed_count == 0
    assert payload["stats"]["url_found"] == 2
    assert payload["stats"]["url_fetch_success"] == 0
    assert payload["stats"]["url_fetch_failed"] == 0


def test_running_report_keeps_blocked_and_failed_counters_coherent(tmp_path: Path):
    source = tmp_path / "blocked.txt"
    source.write_text("Blocked link: https://example.com/blocked", encoding="utf-8")

    report = SnapshottingReport()
    report.enable_running_report(tmp_path)
    public_fetcher = PublicUrlFetcher(
        DummyAdapter(url_result="Checking your browser before accessing this page."),
        report=report,
        public_fetch=PublicFetchConfig(provider="auto", enable_scrapling=False),
    )

    result = convert_txt_with_urls(
        source,
        fetch_urls=True,
        public_fetcher=public_fetcher,
        session_fetcher=DummySessionFetcher(),
        session_manager=DummySessionManager(),
        report=report,
    )

    assert result.failed_count == 1
    assert report.snapshots
    blocked_snapshot = report.snapshots[-1]
    assert blocked_snapshot["stats"]["public_url_blocked"] == 1
    assert blocked_snapshot["stats"]["url_fetch_failed"] == 1


def test_report_cli_reads_specific_path(tmp_path: Path, capsys):
    path = tmp_path / "conversion_report_20260420_020000.json"
    _write_report(
        path,
        stats={"scanned_items": 2, "matched_files": 1, "failed": 1},
        log=["[FAIL] bad.txt: ValueError('bad')"],
    )

    code = main(["report", "--path", str(path), "--failed"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Diagnostics:" in captured.out
    assert "[FAIL] bad.txt" in captured.out


def test_report_cli_reads_latest_from_report_dir(tmp_path: Path, capsys):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    path = report_dir / "conversion_report_20260420_020000.json"
    _write_report(
        path,
        stats={"scanned_items": 3, "matched_files": 1, "failed": 0},
        log=[],
    )

    code = main(["report", "--report-dir", str(report_dir), "--summary"])

    captured = capsys.readouterr()
    assert code == 0
    assert str(path.resolve()) in captured.out
    assert "- scanned_items: 3" in captured.out
