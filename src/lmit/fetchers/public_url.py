from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from lmit.converters.markitdown_adapter import MarkItDownAdapter
from lmit.fetchers.npm_registry import fetch_npm_package_markdown, parse_npm_package_url
from lmit.reports import ConversionReport


class PublicUrlFetcher:
    def __init__(
        self,
        adapter: MarkItDownAdapter,
        *,
        work_dir: Path | None = None,
        report: ConversionReport | None = None,
    ):
        self.adapter = adapter
        self.work_dir = work_dir
        self.report = report

    def fetch(self, url: str) -> str:
        npm_package_url = parse_npm_package_url(url)
        if npm_package_url is not None:
            if self.report is not None:
                self.report.log(f"[NPM-REGISTRY-FETCH] {npm_package_url.package_name}")
            return fetch_npm_package_markdown(npm_package_url)

        try:
            return self.adapter.convert_url(url)
        except Exception as original_exc:
            if self.work_dir is None:
                raise
            try:
                return self._fetch_with_browser(url)
            except Exception:
                raise original_exc

    def _fetch_with_browser(self, url: str) -> str:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise

        if self.report is not None:
            self.report.log(f"[PUBLIC-BROWSER-FALLBACK] {url}")

        tmp_dir = self.work_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        temp_html = tmp_dir / f"public_{sha256(url.encode('utf-8')).hexdigest()[:16]}.html"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                if self.report is not None:
                    self.report.log(f"[WARN] networkidle timeout for public URL: {url}")
            page.wait_for_timeout(3000)
            temp_html.write_text(page.content(), encoding="utf-8")
            browser.close()

        return self.adapter.convert_path(temp_html)
