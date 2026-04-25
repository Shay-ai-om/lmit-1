from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from lmit.config import PublicFetchConfig
from lmit.converters.markitdown_adapter import MarkItDownAdapter
from lmit.fetchers.npm_registry import fetch_npm_package_markdown, parse_npm_package_url
from lmit.fetchers.public_url_quality import (
    count_meaningful_visible_chars,
    is_blank_public_url_text,
    is_blocked_public_url_text,
    is_too_short_public_url_text,
)
from lmit.fetchers.public_url_scrapling import PublicUrlScraplingFetcher
from lmit.reports import ConversionReport

PUBLIC_BROWSER_NAVIGATION_TIMEOUT_MS = 45000


class PublicUrlFetcher:
    def __init__(
        self,
        adapter: MarkItDownAdapter,
        *,
        work_dir: Path | None = None,
        report: ConversionReport | None = None,
        public_fetch: PublicFetchConfig | None = None,
        scrapling_fetcher: object | None = None,
        navigation_timeout_ms: int | None = None,
    ):
        self.adapter = adapter
        self.work_dir = work_dir
        self.report = report
        self.public_fetch = public_fetch or PublicFetchConfig()
        self._scrapling_fetcher = scrapling_fetcher
        self.navigation_timeout_ms = (
            navigation_timeout_ms
            if navigation_timeout_ms is not None
            else self.public_fetch.navigation_timeout_ms
        )

    def fetch(self, url: str) -> str:
        self._log(f"[URL-FETCH-START] {url}")
        npm_package_url = parse_npm_package_url(url)
        if npm_package_url is not None:
            self._log(f"[NPM-REGISTRY-FETCH] {npm_package_url.package_name}")
            return fetch_npm_package_markdown(npm_package_url)

        provider = self.public_fetch.provider.strip().lower() or "auto"
        self._log(
            "[PUBLIC-FETCH-PROVIDER] "
            f"url={url} provider={provider} "
            f"scrapling={self.public_fetch.enable_scrapling} "
            f"dynamic={self.public_fetch.enable_scrapling_dynamic}"
        )
        if provider == "legacy":
            result, stage_name = self._fetch_legacy(url)
            self._log(f"[PUBLIC-FETCH-DONE] url={url} stage={stage_name}")
            return result

        result, stage_name = self._fetch_with_public_pipeline(url)
        self._log(f"[PUBLIC-FETCH-DONE] url={url} stage={stage_name}")
        return result

    def _fetch_with_public_pipeline(self, url: str) -> tuple[str, str]:
        if self.public_fetch.enable_scrapling:
            scrapling_fetcher = self._get_scrapling_fetcher()
            static_result = self._try_stage(
                "scrapling_static",
                url,
                scrapling_fetcher.fetch_static,
            )
            if static_result.text is not None and static_result.quality is None:
                return static_result.text, "scrapling_static"
            if self.public_fetch.enable_scrapling_dynamic:
                reason = static_result.quality or static_result.failure_reason or "needed"
                self._log(
                    "[PUBLIC-FETCH-UPGRADE] "
                    f"url={url} from_stage=scrapling_static "
                    f"upgrade=scrapling_dynamic reason={reason}"
                )
                dynamic_result = self._try_stage(
                    "scrapling_dynamic",
                    url,
                    scrapling_fetcher.fetch_dynamic,
                )
                if dynamic_result.text is not None and dynamic_result.quality is None:
                    return dynamic_result.text, "scrapling_dynamic"
                reason = dynamic_result.quality or dynamic_result.failure_reason or "needed"
            else:
                reason = static_result.quality or static_result.failure_reason or "needed"
        else:
            reason = "scrapling_disabled"

        self._log(
            "[PUBLIC-FETCH-UPGRADE] "
            f"url={url} from_stage=scrapling "
            f"upgrade=legacy_markitdown reason={reason}"
        )
        return self._fetch_legacy_with_quality_upgrade(url)

    def _fetch_legacy_with_quality_upgrade(self, url: str) -> tuple[str, str]:
        try:
            text = self.adapter.convert_url(url)
        except Exception as original_exc:
            self._log(
                "[PUBLIC-FETCH-STAGE] "
                f"url={url} stage=legacy_markitdown status=failed error={original_exc!r}"
            )
            if self.work_dir is None:
                raise
            self._log(
                "[PUBLIC-FETCH-UPGRADE] "
                f"url={url} from_stage=legacy_markitdown "
                "upgrade=legacy_playwright_html reason=failed"
            )
            try:
                return self._fetch_browser_stage(url)
            except Exception as fallback_exc:
                self._log(f"[PUBLIC-BROWSER-FALLBACK-FAILED] {url}: {fallback_exc!r}")
                raise original_exc from fallback_exc

        quality = self._quality_reason(text)
        if quality is None:
            self._log_stage_success("legacy_markitdown", url, text)
            return text, "legacy_markitdown"

        self._log_stage_quality("legacy_markitdown", url, text, quality)
        if self.work_dir is None:
            return text, "legacy_markitdown"

        self._log(
            "[PUBLIC-FETCH-UPGRADE] "
            f"url={url} from_stage=legacy_markitdown "
            f"upgrade=legacy_playwright_html reason={quality}"
        )
        try:
            return self._fetch_browser_stage(url)
        except Exception as fallback_exc:
            self._log(
                "[PUBLIC-BROWSER-FALLBACK-FAILED] "
                f"{url}: {fallback_exc!r}; returning legacy_markitdown result"
            )
            return text, "legacy_markitdown"

    def _fetch_legacy(self, url: str) -> tuple[str, str]:
        try:
            text = self.adapter.convert_url(url)
            self._log_stage_success("legacy_markitdown", url, text)
            return text, "legacy_markitdown"
        except Exception as original_exc:
            if self.work_dir is None:
                raise
            try:
                return self._fetch_browser_stage(url)
            except Exception as fallback_exc:
                self._log(f"[PUBLIC-BROWSER-FALLBACK-FAILED] {url}: {fallback_exc!r}")
                raise original_exc from fallback_exc

    def _fetch_browser_stage(self, url: str) -> tuple[str, str]:
        text = self._fetch_with_browser(url)
        quality = self._quality_reason(text)
        if quality is None:
            self._log_stage_success("legacy_playwright_html", url, text)
        else:
            self._log_stage_quality("legacy_playwright_html", url, text, quality)
        return text, "legacy_playwright_html"

    def _fetch_with_browser(self, url: str) -> str:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise

        self._log(f"[PUBLIC-BROWSER-FALLBACK] {url}")

        tmp_dir = self.work_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        temp_html = tmp_dir / f"public_{sha256(url.encode('utf-8')).hexdigest()[:16]}.html"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.navigation_timeout_ms,
            )
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                self._log(f"[WARN] networkidle timeout for public URL: {url}")
            page.wait_for_timeout(3000)
            temp_html.write_text(page.content(), encoding="utf-8")
            browser.close()

        return self.adapter.convert_path(temp_html)

    def _get_scrapling_fetcher(self):
        if self._scrapling_fetcher is None:
            self._scrapling_fetcher = PublicUrlScraplingFetcher(self.public_fetch)
        return self._scrapling_fetcher

    def _try_stage(self, stage_name: str, url: str, fetcher) -> _StageResult:
        try:
            text = fetcher(url)
        except Exception as exc:
            self._log(
                "[PUBLIC-FETCH-STAGE] "
                f"url={url} stage={stage_name} status=failed error={exc!r}"
            )
            return _StageResult(text=None, quality=None, failure_reason="failed")

        quality = self._quality_reason(text)
        if quality is None:
            self._log_stage_success(stage_name, url, text)
            return _StageResult(text=text, quality=None, failure_reason=None)

        self._log_stage_quality(stage_name, url, text, quality)
        return _StageResult(text=text, quality=quality, failure_reason=None)

    def _quality_reason(self, text: str | None) -> str | None:
        if is_blank_public_url_text(text):
            return "blank"
        if is_blocked_public_url_text(text):
            return "blocked"
        if is_too_short_public_url_text(
            text,
            min_meaningful_chars=self.public_fetch.min_meaningful_chars,
        ):
            return "too_short"
        return None

    def _log_stage_success(self, stage_name: str, url: str, text: str | None) -> None:
        self._log(
            "[PUBLIC-FETCH-STAGE] "
            f"url={url} stage={stage_name} status=ok "
            f"chars={count_meaningful_visible_chars(text)}"
        )

    def _log_stage_quality(
        self,
        stage_name: str,
        url: str,
        text: str | None,
        quality: str,
    ) -> None:
        self._log(
            "[PUBLIC-FETCH-STAGE] "
            f"url={url} stage={stage_name} status=needs_upgrade "
            f"quality={quality} chars={count_meaningful_visible_chars(text)}"
        )

    def _log(self, message: str) -> None:
        if self.report is not None:
            self.report.log(message)


class _StageResult:
    def __init__(
        self,
        *,
        text: str | None,
        quality: str | None,
        failure_reason: str | None,
    ):
        self.text = text
        self.quality = quality
        self.failure_reason = failure_reason
