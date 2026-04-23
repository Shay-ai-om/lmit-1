from __future__ import annotations

import json
import os
from pathlib import Path

from lmit.cli import main
from lmit.reports import (
    diagnose_report,
    latest_report_path,
    load_report,
    render_report,
    render_report_json,
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
