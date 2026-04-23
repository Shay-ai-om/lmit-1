from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from lmit.fetchers.public_url import PublicUrlFetcher
from lmit.fetchers.session_url import SessionUrlFetcher
from lmit.reports import ConversionReport
from lmit.sessions.manager import SessionManager

URL_PATTERN = re.compile(r"https?://[^\s<>\"'\]\)}，。！？、；：]+")


@dataclass(frozen=True)
class TxtUrlConversionResult:
    markdown: str
    blank_count: int
    failed_count: int


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
) -> TxtUrlConversionResult:
    raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
    urls = extract_urls(raw_text)
    report.stats.url_found += len(urls)

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

    for index, url in enumerate(urls, start=1):
        parts.extend([f"### URL {index}", "", f"Source URL: {url}", ""])
        site = session_manager.site_for_url(url)
        try:
            if site is None:
                text = public_fetcher.fetch(url)
                if _blank(text):
                    text = "[BLANK_URL_OUTPUT]\n"
                    blank_count += 1
                    failed_count += 1
                    report.stats.url_fetch_failed += 1
                elif _blocked_content(text):
                    report.log(f"[URL-CONTENT-BLOCKED] {url}")
                    text = (
                        "[URL_CONTENT_BLOCKED]\n\n"
                        "Fetched page appears to be a bot check, login wall, or "
                        "verification page rather than the target content.\n\n"
                        + text
                    )
                    failed_count += 1
                    report.stats.url_fetch_failed += 1
                else:
                    report.stats.url_fetch_success += 1
            else:
                text = session_fetcher.fetch(url, site)
                if _blank(text):
                    text = "[BLANK_SESSION_URL_OUTPUT]\n"
                    blank_count += 1
                    failed_count += 1
                    report.stats.session_url_fetch_failed += 1
                elif _blocked_content(text):
                    report.log(f"[SESSION-URL-CONTENT-BLOCKED] {url}")
                    text = (
                        "[SESSION_URL_CONTENT_BLOCKED]\n\n"
                        "Fetched page appears to be a bot check, login wall, or "
                        "verification page rather than the target content.\n\n"
                        + text
                    )
                    failed_count += 1
                    report.stats.session_url_fetch_failed += 1
                else:
                    report.stats.session_url_fetch_success += 1
            parts.extend([text.rstrip(), "", "---", ""])
        except Exception as exc:
            if site is None:
                report.stats.url_fetch_failed += 1
                marker = "URL_FETCH_FAILED"
            else:
                report.stats.session_url_fetch_failed += 1
                marker = "SESSION_URL_FETCH_FAILED"
            report.log(f"[{marker}] {url}: {exc!r}")
            failed_count += 1
            parts.extend([f"[{marker}] {exc!r}", "", "---", ""])

    return TxtUrlConversionResult(
        "\n".join(parts).rstrip() + "\n",
        blank_count,
        failed_count,
    )


def _blank(text: str | None) -> bool:
    return text is None or text.strip() == ""


def _blocked_content(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "performing security verification",
        "enable javascript and cookies to continue",
        "verification successful. waiting for",
        "checking your browser",
        "just a moment...",
        "cloudflare ray id",
        "sign in to continue",
        "log in to continue",
        "目前無法查看此內容",
        "擁有者僅與一小群用戶分享內容",
        "變更了分享對象",
        "刪除了內容",
    ]
    return any(marker in lowered for marker in markers)
