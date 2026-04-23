from __future__ import annotations

from pathlib import Path
from time import sleep
from typing import Callable

from lmit.config import SessionSiteConfig
from lmit.converters.markitdown_adapter import MarkItDownAdapter
from lmit.reports import ConversionReport
from lmit.sessions.browser_provider import (
    BrowserProvider,
    PlaywrightBrowserProvider,
    SessionLoginRequired,
)
from lmit.sessions.login import capture_session_state


CaptureSession = Callable[[SessionSiteConfig, ConversionReport], None]


class SessionUrlFetcher:
    def __init__(
        self,
        *,
        adapter: MarkItDownAdapter,
        work_dir: Path,
        report: ConversionReport,
        provider: BrowserProvider | None = None,
        capture_session: CaptureSession = capture_session_state,
        playwright_api: tuple[type[Exception], type[Exception], object] | None = None,
    ):
        self.adapter = adapter
        self.work_dir = work_dir
        self.report = report
        self.provider = provider or PlaywrightBrowserProvider(
            adapter=adapter,
            work_dir=work_dir,
            report=report,
        )
        self.capture_session = capture_session
        self.playwright_api = playwright_api

    def fetch(self, url: str, site: SessionSiteConfig) -> str:
        playwright_error, playwright_timeout_error, sync_playwright = self._load_playwright_api()

        if not site.state_file.exists():
            self.capture_session(site, self.report)

        try:
            return self._fetch_with_retries(
                url,
                site,
                sync_playwright=sync_playwright,
                playwright_error=playwright_error,
                playwright_timeout_error=playwright_timeout_error,
            )
        except SessionLoginRequired as exc:
            self.report.log(f"[SESSION-EXPIRED] {site.name}: {exc}")
            self.capture_session(site, self.report)
            return self._fetch_with_retries(
                url,
                site,
                sync_playwright=sync_playwright,
                playwright_error=playwright_error,
                playwright_timeout_error=playwright_timeout_error,
            )

    def _load_playwright_api(self) -> tuple[type[Exception], type[Exception], object]:
        if self.playwright_api is not None:
            return self.playwright_api
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for session URLs. Install with "
                "`pip install -e .[session]` and run `playwright install chromium`."
            ) from exc
        return PlaywrightError, PlaywrightTimeoutError, sync_playwright

    def _fetch_with_retries(
        self,
        url: str,
        site: SessionSiteConfig,
        *,
        sync_playwright,
        playwright_error,
        playwright_timeout_error,
    ) -> str:
        attempts = max(1, site.retry_count + 1)
        last_exc: Exception | None = None
        retry_errors = (playwright_error, playwright_timeout_error, TimeoutError)
        for attempt in range(1, attempts + 1):
            try:
                result = self.provider.fetch_once(
                    url,
                    site,
                    sync_playwright=sync_playwright,
                    playwright_timeout_error=playwright_timeout_error,
                )
                self.report.log(
                    f"[SESSION-FETCHED] site={site.name} provider={result.provider} "
                    f"render_mode={result.render_mode} final_url={result.final_url}"
                )
                return result.markdown
            except SessionLoginRequired:
                raise
            except retry_errors as exc:
                last_exc = exc
                if attempt >= attempts:
                    break
                self.report.log(
                    f"[SESSION-RETRY] {site.name} {attempt}/{attempts - 1} "
                    f"provider={self.provider.name} for {url}: {exc!r}"
                )
                sleep(max(0, site.retry_backoff_ms) / 1000 * attempt)
        assert last_exc is not None
        raise last_exc
