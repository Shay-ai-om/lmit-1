from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Protocol

from lmit.config import SessionSiteConfig
from lmit.converters.markitdown_adapter import MarkItDownAdapter
from lmit.reports import ConversionReport
from lmit.sessions.launch import (
    apply_stealth,
    browser_executable_for_site,
    browser_launch_options,
    login_cdp_endpoint,
    login_cdp_port,
    login_profile_dir,
    login_uses_cdp,
    wait_for_cdp_endpoint,
)


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

        if login_uses_cdp(site):
            return self._fetch_once_via_cdp(
                url,
                site,
                target_url=target_url,
                temp_html=temp_html,
                strategy=strategy,
                sync_playwright=sync_playwright,
                playwright_timeout_error=playwright_timeout_error,
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(**browser_launch_options(site, headless=site.headless))
            try:
                context_kwargs = {"storage_state": str(site.state_file)}
                context_kwargs.update(strategy.context_options())
                context = browser.new_context(**context_kwargs)
                apply_stealth(context)
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

    def _fetch_once_via_cdp(
        self,
        url: str,
        site: SessionSiteConfig,
        *,
        target_url: str,
        temp_html: Path,
        strategy,
        sync_playwright,
        playwright_timeout_error,
    ) -> BrowserFetchResult:
        endpoint = login_cdp_endpoint(site)
        port = login_cdp_port(site)
        self.report.log(f"[SESSION-BROWSER-ATTACH] {site.name}: endpoint={endpoint}")
        browser_was_launched = self._ensure_cdp_browser(site, port=port, target_url=target_url)
        wait_for_cdp_endpoint(
            endpoint,
            timeout_seconds=max(5, site.navigation_timeout_ms / 1000),
        )

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint)
            try:
                if not browser.contexts:
                    raise RuntimeError(f"{site.name}: no browser context found after CDP connect")
                context = browser.contexts[0]
                apply_stealth(context)
                reuse_existing_page = browser_was_launched and bool(context.pages)
                page = context.pages[-1] if reuse_existing_page else context.new_page()
                try:
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
                        provider="playwright_cdp",
                        render_mode=strategy.render_mode,
                        target_url=target_url,
                        final_url=final_url,
                    )
                finally:
                    if not reuse_existing_page:
                        page.close()
            finally:
                try:
                    browser.disconnect()
                except AttributeError:
                    pass

    def _ensure_cdp_browser(
        self,
        site: SessionSiteConfig,
        *,
        port: int,
        target_url: str,
    ) -> bool:
        endpoint = login_cdp_endpoint(site)
        try:
            wait_for_cdp_endpoint(endpoint, timeout_seconds=1)
            return False
        except TimeoutError:
            pass

        profile_dir = login_profile_dir(site)
        profile_dir.mkdir(parents=True, exist_ok=True)
        executable = browser_executable_for_site(site)
        self.report.log(
            "[SESSION-BROWSER-LAUNCH] "
            f"{site.name}: executable={executable} profile={profile_dir} port={port}"
        )
        subprocess.Popen(
            [
                str(executable),
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-popup-blocking",
                "--new-window",
                target_url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
