from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import sys


RUNNING_REPORT_NAME = "conversion_report_running"


@dataclass
class ConversionStats:
    scanned_items: int = 0
    matched_files: int = 0
    converted: int = 0
    partial: int = 0
    failed: int = 0
    skipped: int = 0
    skipped_unchanged: int = 0
    skipped_unstable: int = 0
    skipped_unsupported: int = 0
    skipped_excluded: int = 0
    manifest_missing: int = 0
    renamed_output_files: int = 0
    blank_output: int = 0
    url_found: int = 0
    url_fetch_success: int = 0
    url_fetch_failed: int = 0
    session_url_fetch_success: int = 0
    session_url_fetch_failed: int = 0
    public_url_scrapling_static_success: int = 0
    public_url_scrapling_dynamic_success: int = 0
    public_url_scrapling_stealthy_success: int = 0
    public_url_markitdown_success: int = 0
    public_url_playwright_success: int = 0
    public_url_quality_retry: int = 0
    public_url_blocked: int = 0
    public_url_blank: int = 0


@dataclass
class ConversionReport:
    stats: ConversionStats = field(default_factory=ConversionStats)
    lines: list[str] = field(default_factory=list)
    _running_md_path: Path | None = field(default=None, init=False, repr=False)
    _running_json_path: Path | None = field(default=None, init=False, repr=False)

    def log(self, message: str) -> None:
        try:
            print(message, flush=True)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or "utf-8"
            sys.stdout.flush()
            sys.stdout.buffer.write((message + "\n").encode(encoding, errors="replace"))
            sys.stdout.buffer.flush()
        self.lines.append(message)
        self.flush_running()

    def enable_running_report(self, report_dir: Path) -> tuple[Path, Path]:
        report_dir.mkdir(parents=True, exist_ok=True)
        self._running_md_path = report_dir / f"{RUNNING_REPORT_NAME}.md"
        self._running_json_path = report_dir / f"{RUNNING_REPORT_NAME}.json"
        self.flush_running()
        return self._running_md_path, self._running_json_path

    def flush_running(self) -> tuple[Path, Path] | None:
        if self._running_md_path is None or self._running_json_path is None:
            return None
        _write_report_paths(
            self.stats,
            self.lines,
            md_path=self._running_md_path,
            json_path=self._running_json_path,
        )
        return self._running_md_path, self._running_json_path

    def clear_running_report(self) -> None:
        for path in (self._running_md_path, self._running_json_path):
            if path is None:
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self._running_md_path = None
        self._running_json_path = None

    def write(self, report_dir: Path) -> tuple[Path, Path]:
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        md_path = report_dir / f"conversion_report_{timestamp}.md"
        json_path = report_dir / f"conversion_report_{timestamp}.json"
        _write_report_paths(self.stats, self.lines, md_path=md_path, json_path=json_path)
        return md_path, json_path


@dataclass(frozen=True)
class LoadedReport:
    path: Path
    stats: dict[str, Any]
    log: list[str]


@dataclass(frozen=True)
class ReportDiagnostics:
    failed: list[str]
    partial: list[str]
    blocked: list[str]
    session_expired: list[str]
    login_required: list[str]
    blank: list[str]
    url_fetch_failed: list[str]
    missing: list[str]

    @property
    def has_issues(self) -> bool:
        return any(
            [
                self.failed,
                self.partial,
                self.blocked,
                self.session_expired,
                self.login_required,
                self.blank,
                self.url_fetch_failed,
                self.missing,
            ]
        )

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "failed": self.failed,
            "partial": self.partial,
            "blocked": self.blocked,
            "session_expired": self.session_expired,
            "login_required": self.login_required,
            "blank": self.blank,
            "url_fetch_failed": self.url_fetch_failed,
            "missing": self.missing,
        }


SUMMARY_STATS = [
    "scanned_items",
    "matched_files",
    "converted",
    "partial",
    "failed",
    "skipped",
    "skipped_unchanged",
    "skipped_unstable",
    "skipped_unsupported",
    "skipped_excluded",
    "manifest_missing",
    "blank_output",
    "url_found",
    "url_fetch_success",
    "url_fetch_failed",
    "session_url_fetch_success",
    "session_url_fetch_failed",
    "public_url_scrapling_static_success",
    "public_url_scrapling_dynamic_success",
    "public_url_scrapling_stealthy_success",
    "public_url_markitdown_success",
    "public_url_playwright_success",
    "public_url_quality_retry",
    "public_url_blocked",
    "public_url_blank",
]


def latest_report_path(report_dir: Path) -> Path:
    candidates = sorted(
        (
            path
            for path in report_dir.glob("conversion_report_*.json")
            if path.stem != RUNNING_REPORT_NAME
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"no conversion report JSON files found in {report_dir}")
    return candidates[0]


def load_report(path: Path) -> LoadedReport:
    data = json.loads(path.read_text(encoding="utf-8"))
    return LoadedReport(
        path=path.resolve(),
        stats=dict(data.get("stats", {})),
        log=[str(line) for line in data.get("log", [])],
    )


def load_latest_report(report_dir: Path) -> LoadedReport:
    return load_report(latest_report_path(report_dir))


def diagnose_report(report: LoadedReport) -> ReportDiagnostics:
    failed: list[str] = []
    partial: list[str] = []
    blocked: list[str] = []
    session_expired: list[str] = []
    login_required: list[str] = []
    blank: list[str] = []
    url_fetch_failed: list[str] = []
    missing: list[str] = []

    for line in report.log:
        upper = line.upper()
        if line.startswith("[FAIL]"):
            failed.append(line)
        if line.startswith("[PARTIAL]"):
            partial.append(line)
        if "CONTENT-BLOCKED" in upper or "CONTENT_BLOCKED" in upper:
            blocked.append(line)
        if "SESSION-EXPIRED" in upper:
            session_expired.append(line)
        if "LOGIN-REQUIRED" in upper:
            login_required.append(line)
        if "BLANK" in upper:
            blank.append(line)
        if "URL_FETCH_FAILED" in upper:
            url_fetch_failed.append(line)
        if line.startswith("[MISSING]"):
            missing.append(line)

    if int(report.stats.get("blank_output", 0) or 0) > 0 and not blank:
        blank.append(f"blank_output: {report.stats['blank_output']}")
    if int(report.stats.get("partial", 0) or 0) > 0 and not partial:
        partial.append(f"partial: {report.stats['partial']}")
    if int(report.stats.get("failed", 0) or 0) > 0 and not failed:
        failed.append(f"failed: {report.stats['failed']}")
    if int(report.stats.get("url_fetch_failed", 0) or 0) > 0 and not url_fetch_failed:
        url_fetch_failed.append(f"url_fetch_failed: {report.stats['url_fetch_failed']}")
    session_failures = int(report.stats.get("session_url_fetch_failed", 0) or 0)
    if session_failures > 0 and not any("SESSION_URL_FETCH_FAILED" in item for item in url_fetch_failed):
        url_fetch_failed.append(f"session_url_fetch_failed: {session_failures}")
    if int(report.stats.get("manifest_missing", 0) or 0) > 0 and not missing:
        missing.append(f"manifest_missing: {report.stats['manifest_missing']}")

    return ReportDiagnostics(
        failed=failed,
        partial=partial,
        blocked=blocked,
        session_expired=session_expired,
        login_required=login_required,
        blank=blank,
        url_fetch_failed=url_fetch_failed,
        missing=missing,
    )


def render_report(
    report: LoadedReport,
    *,
    summary_only: bool = False,
    failed_only: bool = False,
    log_limit: int = 20,
) -> str:
    diagnostics = diagnose_report(report)
    lines = [
        f"Report: {report.path}",
        "",
        "Stats:",
    ]
    for key in SUMMARY_STATS:
        if key in report.stats:
            lines.append(f"- {key}: {report.stats[key]}")
    extra_keys = sorted(key for key in report.stats if key not in SUMMARY_STATS)
    for key in extra_keys:
        lines.append(f"- {key}: {report.stats[key]}")

    lines.extend(["", "Diagnostics:"])
    lines.extend(_render_diagnostic_counts(diagnostics))

    if failed_only:
        lines.extend(["", "Issue Details:"])
        lines.extend(_render_diagnostic_details(diagnostics))
        return "\n".join(lines).rstrip() + "\n"

    if summary_only:
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(["", "Issue Details:"])
    detail_lines = _render_diagnostic_details(diagnostics)
    if detail_lines:
        lines.extend(detail_lines)
    else:
        lines.append("- none")

    recent_log = report.log[-max(0, log_limit) :] if log_limit else []
    lines.extend(["", f"Recent Log ({len(recent_log)}):"])
    if recent_log:
        lines.extend(f"- {line}" for line in recent_log)
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def report_payload(report: LoadedReport) -> dict[str, Any]:
    diagnostics = diagnose_report(report)
    return {
        "path": str(report.path),
        "stats": report.stats,
        "diagnostics": diagnostics.as_dict(),
        "log": report.log,
    }


def render_report_json(report: LoadedReport) -> str:
    return json.dumps(report_payload(report), ensure_ascii=False, indent=2) + "\n"


def _render_diagnostic_counts(diagnostics: ReportDiagnostics) -> list[str]:
    data = diagnostics.as_dict()
    lines = [f"- {name}: {len(items)}" for name, items in data.items()]
    if not diagnostics.has_issues:
        lines.append("- status: no issues detected")
    return lines


def _render_diagnostic_details(diagnostics: ReportDiagnostics) -> list[str]:
    lines: list[str] = []
    for name, items in diagnostics.as_dict().items():
        if not items:
            continue
        lines.append(f"- {name}:")
        lines.extend(f"  - {item}" for item in items)
    return lines


def _write_report_paths(
    stats: ConversionStats,
    lines: list[str],
    *,
    md_path: Path,
    json_path: Path,
) -> None:
    md_path.write_text(_render_markdown(stats, lines), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {"stats": asdict(stats), "log": lines},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _render_markdown(stats: ConversionStats, lines: list[str]) -> str:
    md_lines = [
        "# Conversion Report",
        "",
        f"- Generated at UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Stats",
        "",
    ]
    for key, value in asdict(stats).items():
        md_lines.append(f"- {key}: {value}")
    md_lines.extend(["", "## Log", ""])
    md_lines.extend(f"- {line}" for line in lines)
    return "\n".join(md_lines) + "\n"
