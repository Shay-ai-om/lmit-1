from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from lmit.cancellation import CancelCheck, ConversionCancelled, noop_cancel_check
from lmit.fetchers.public_url import PublicUrlFetcher
from lmit.fetchers.public_url_blocked import is_blocked_public_url_text
from lmit.fetchers.session_url import SessionUrlFetcher
from lmit.reports import ConversionReport
from lmit.sessions.manager import SessionManager

URL_PATTERN = re.compile(r"https?://[^\s<>\"'\]\)}，。！？、；：]+")


@dataclass(frozen=True)
class TxtUrlConversionResult:
    markdown: str
    blank_count: int
    failed_count: int
    cancelled: bool = False


def extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for url in URL_PATTERN.findall(text):
        cleaned = url.rstrip(".,;:!?)]}'\"")
        if cleaned not in seen:
            seen.add(cleaned)
            urls.append(cleaned)
    return urls


def convert_txt_with_urls(
    file_path: Path,
    *,
    fetch_urls: bool,
    public_fetcher: PublicUrlFetcher,
    session_fetcher: SessionUrlFetcher,
    session_manager: SessionManager,
    report: ConversionReport,
    cancel_check: CancelCheck = noop_cancel_check,
) -> TxtUrlConversionResult:
    raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
    urls = extract_urls(raw_text)
    _increment_report_stat(report, "url_found", amount=len(urls))

    parts: list[str] = [
        "# TXT Source",
        "",
        f"Source file: {file_path.name}",
        "",
        "## Original Text",
        "",
        raw_text.strip(),
        "",
        "## Extracted URLs",
        "",
    ]

    if urls:
        parts.extend(f"- {url}" for url in urls)
    else:
        parts.append("[No URLs found]")

    if not fetch_urls:
        parts.extend(["", "## URL Fetched Content", "", "[URL fetching disabled]"])
        return TxtUrlConversionResult("\n".join(parts).rstrip() + "\n", 0, 0)

    parts.extend(["", "---", "", "## URL Fetched Content", ""])
    blank_count = 0
    failed_count = 0
    cancelled = False

    for index, url in enumerate(urls, start=1):
        try:
            cancel_check()
        except ConversionCancelled:
            cancelled = True
            report.log(f"[CANCELLED] txt url fetch aborted at {url}")
            parts.extend(
                [
                    f"### URL {index}",
                    "",
                    f"Source URL: {url}",
                    "",
                    "[URL_FETCH_CANCELLED]",
                    "",
                    "---",
                    "",
                ]
            )
            break
        parts.extend([f"### URL {index}", "", f"Source URL: {url}", ""])
        site = session_manager.site_for_url(url)
        try:
            if site is None:
                text = public_fetcher.fetch(url)
                if _blank(text):
                    text = "[BLANK_URL_OUTPUT]\n"
                    blank_count += 1
                    failed_count += 1
                    _increment_report_stat(report, "url_fetch_failed")
                elif _blocked_content(text):
                    failed_count += 1
                    _increment_report_stat(report, "url_fetch_failed")
                    report.log(f"[URL-CONTENT-BLOCKED] {url}")
                    text = (
                        "[URL_CONTENT_BLOCKED]\n\n"
                        "Fetched page appears to be a bot check, login wall, or "
                        "verification page rather than the target content.\n\n"
                        + text
                    )
                else:
                    _increment_report_stat(report, "url_fetch_success")
            else:
                text = session_fetcher.fetch(url, site)
                if _blank(text):
                    text = "[BLANK_SESSION_URL_OUTPUT]\n"
                    blank_count += 1
                    failed_count += 1
                    _increment_report_stat(report, "session_url_fetch_failed")
                elif _blocked_content(text):
                    failed_count += 1
                    _increment_report_stat(report, "session_url_fetch_failed")
                    report.log(f"[SESSION-URL-CONTENT-BLOCKED] {url}")
                    text = (
                        "[SESSION_URL_CONTENT_BLOCKED]\n\n"
                        "Fetched page appears to be a bot check, login wall, or "
                        "verification page rather than the target content.\n\n"
                        + text
                    )
                else:
                    _increment_report_stat(report, "session_url_fetch_success")
            parts.extend([text.rstrip(), "", "---", ""])
        except ConversionCancelled:
            cancelled = True
            report.log(f"[CANCELLED] txt url fetch aborted at {url}")
            parts.extend(["[URL_FETCH_CANCELLED]", "", "---", ""])
            break
        except Exception as exc:
            if site is None:
                _increment_report_stat(report, "url_fetch_failed")
                marker = "URL_FETCH_FAILED"
            else:
                _increment_report_stat(report, "session_url_fetch_failed")
                marker = "SESSION_URL_FETCH_FAILED"
            report.log(f"[{marker}] {url}: {exc!r}")
            failed_count += 1
            parts.extend([f"[{marker}] {exc!r}", "", "---", ""])

    return TxtUrlConversionResult(
        "\n".join(parts).rstrip() + "\n",
        blank_count,
        failed_count,
        cancelled=cancelled,
    )


def _blank(text: str | None) -> bool:
    return text is None or text.strip() == ""


def _blocked_content(text: str) -> bool:
    return is_blocked_public_url_text(text)


def _increment_report_stat(
    report: ConversionReport,
    stat_name: str,
    *,
    amount: int = 1,
) -> None:
    setattr(report.stats, stat_name, getattr(report.stats, stat_name) + amount)
    report.flush_running()


