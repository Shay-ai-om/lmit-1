from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from lmit.config import SessionSiteConfig
from lmit.converters.markitdown_adapter import MarkItDownAdapter
from lmit.reports import ConversionReport


class SessionLoginRequired(RuntimeError):
    """Raised when the stored browser session is missing or no longer valid."""


@dataclass(frozen=True)
class BrowserFetchResult:
    markdown: str
    provider: str
    render_mode: str
    target_url: str
    final_url: str


class BrowserProvider(Protocol):
    name: str

    def fetch_once(
        self,
        url: str,
        site: SessionSiteConfig,
        *,
        sync_playwright,
        playwright_timeout_error,
    ) -> BrowserFetchResult:
        """Fetch a session URL once with an existing storage state."""


class PlaywrightBrowserProvider:
    name = "playwright"

    def __init__(
        self,
        *,
        adapter: MarkItDownAdapter,
        work_dir: Path,
        report: ConversionReport,
    ):
        self.adapter = adapter
        self.work_dir = work_dir
        self.report = report

    def fetch_once(
        self,
        url: str,
        site: SessionSiteConfig,
        *,
        sync_playwright,
        playwright_timeout_error,
    ) -> BrowserFetchResult:
        from lmit.sessions.strategies import strategy_for_site

        strategy = strategy_for_site(site)
        target_url = strategy.target_url(url)
        temp_html = strategy.temp_html_path(self.work_dir, site, url)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=site.headless)
            try:
                context_kwargs = {"storage_state": str(site.state_file)}
                context_kwargs.update(strategy.context_options())
                context = browser.new_context(**context_kwargs)
                page = context.new_page()
                page.goto(
                    target_url,
                    wait_until="domcontentloaded",
                    timeout=site.navigation_timeout_ms,
                )
                if strategy.wait_for_networkidle:
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except playwright_timeout_error:
                        self.report.log(f"[WARN] networkidle timeout for session URL: {url}")

                page.wait_for_timeout(site.wait_ms)
                strategy.after_load(page, self.report)

                final_url = page.url
                if "login" in final_url.lower():
                    raise SessionLoginRequired(f"redirected to login while fetching {url}")

                markdown = strategy.extract_markdown(
                    page,
                    adapter=self.adapter,
                    temp_html=temp_html,
                    target_url=target_url,
                    final_url=final_url,
                )
                return BrowserFetchResult(
                    markdown=markdown,
                    provider=self.name,
                    render_mode=strategy.render_mode,
                    target_url=target_url,
                    final_url=final_url,
                )
            finally:
                browser.close()
