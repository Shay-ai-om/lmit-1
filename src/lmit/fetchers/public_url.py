from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from lmit.cancellation import CancelCheck, noop_cancel_check
from lmit.config import PublicFetchConfig
from lmit.converters.markitdown_adapter import MarkItDownAdapter
from lmit.fetchers.npm_registry import fetch_npm_package_markdown, parse_npm_package_url
from lmit.fetchers.public_url_normalize import normalize_public_url
from lmit.fetchers.public_url_quality import (
    count_meaningful_visible_chars,
    is_blank_public_url_text,
    is_blocked_public_url_text,
    is_too_short_public_url_text,
)
from lmit.fetchers.public_url_scrapling import PublicUrlScraplingFetcher
from lmit.reports import ConversionReport
from lmit.sessions.launch import (
    apply_stealth,
    generic_browser_launch_options,
    wait_for_cdp_endpoint,
)

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
        cancel_check: CancelCheck = noop_cancel_check,
    ):
        self.adapter = adapter
        self.work_dir = work_dir
        self.report = report
        self.public_fetch = public_fetch or PublicFetchConfig()
        self._scrapling_fetcher = scrapling_fetcher
        self.cancel_check = cancel_check
        self.navigation_timeout_ms = (
            navigation_timeout_ms
            if navigation_timeout_ms is not None
            else self.public_fetch.navigation_timeout_ms
        )

    def fetch(self, url: str) -> str:
        self.cancel_check()
        self._log(f"[URL-FETCH-START] {url}")
        normalized_url = normalize_public_url(url)
        fetch_url = normalized_url.url
        if fetch_url != url:
            self._log(
                "[PUBLIC-FETCH-NORMALIZED] "
                f"source={url} target={fetch_url} "
                f"reasons={','.join(normalized_url.reasons) or 'none'}"
            )
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
            result, stage_name = self._fetch_legacy(url, fetch_url=fetch_url)
            self._log(f"[PUBLIC-FETCH-DONE] url={url} stage={stage_name}")
            return result

        result, stage_name = self._fetch_with_public_pipeline(url, fetch_url=fetch_url)
        self._log(f"[PUBLIC-FETCH-DONE] url={url} stage={stage_name}")
        return result

    def _fetch_with_public_pipeline(self, url: str, *, fetch_url: str) -> tuple[str, str]:
        if self.public_fetch.enable_scrapling:
            scrapling_fetcher = self._get_scrapling_fetcher()
            self.cancel_check()
            static_result = self._try_stage(
                "scrapling_static",
                url,
                lambda _: scrapling_fetcher.fetch_static(fetch_url),
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
                self._count_quality_retry(reason)
                self.cancel_check()
                dynamic_result = self._try_stage(
                    "scrapling_dynamic",
                    url,
                    lambda _: scrapling_fetcher.fetch_dynamic(fetch_url),
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
        self._count_quality_retry(reason)
        self.cancel_check()
        return self._fetch_legacy_with_quality_upgrade(url, fetch_url=fetch_url)

    def _fetch_legacy_with_quality_upgrade(self, url: str, *, fetch_url: str) -> tuple[str, str]:
        self.cancel_check()
        try:
            text = self.adapter.convert_url(fetch_url)
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
                return self._fetch_browser_stage(url, fetch_url=fetch_url)
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
        self._count_quality_retry(quality)
        self.cancel_check()
        try:
            return self._fetch_browser_stage(url, fetch_url=fetch_url)
        except Exception as fallback_exc:
            self._log(
                "[PUBLIC-BROWSER-FALLBACK-FAILED] "
                f"{url}: {fallback_exc!r}; returning legacy_markitdown result"
            )
            return text, "legacy_markitdown"

    def _fetch_legacy(self, url: str, *, fetch_url: str) -> tuple[str, str]:
        self.cancel_check()
        try:
            text = self.adapter.convert_url(fetch_url)
            self._log_stage_success("legacy_markitdown", url, text)
            return text, "legacy_markitdown"
        except Exception as original_exc:
            if self.work_dir is None:
                raise
            try:
                return self._fetch_browser_stage(url, fetch_url=fetch_url)
            except Exception as fallback_exc:
                self._log(f"[PUBLIC-BROWSER-FALLBACK-FAILED] {url}: {fallback_exc!r}")
                raise original_exc from fallback_exc

    def _fetch_browser_stage(self, url: str, *, fetch_url: str) -> tuple[str, str]:
        self.cancel_check()
        text = self._fetch_with_browser(fetch_url)
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
            self.cancel_check()
            if self.public_fetch.browser_connect_over_cdp:
                html = self._fetch_with_attached_browser(
                    p,
                    url,
                    playwright_timeout_error=PlaywrightTimeoutError,
                )
            else:
                html = self._fetch_with_launched_browser(
                    p,
                    url,
                    playwright_timeout_error=PlaywrightTimeoutError,
                )
            temp_html.write_text(html, encoding="utf-8")

        return self.adapter.convert_path(temp_html)

    def _fetch_with_launched_browser(
        self,
        playwright,
        url: str,
        *,
        playwright_timeout_error,
    ) -> str:
        launch_options = generic_browser_launch_options(
            channel=self.public_fetch.browser_channel,
            headless=True,
        )
        browser = playwright.chromium.launch(**launch_options)
        try:
            context = browser.new_context(locale="zh-TW")
            apply_stealth(context)
            page = context.new_page()
            self._load_browser_page(
                page,
                url,
                playwright_timeout_error=playwright_timeout_error,
            )
            return page.content()
        finally:
            browser.close()

    def _fetch_with_attached_browser(
        self,
        playwright,
        url: str,
        *,
        playwright_timeout_error,
    ) -> str:
        port = self.public_fetch.browser_cdp_port or 9225
        endpoint = f"http://127.0.0.1:{port}"
        self._log(f"[PUBLIC-BROWSER-ATTACH] endpoint={endpoint}")
        wait_for_cdp_endpoint(
            endpoint,
            timeout_seconds=max(5, self.navigation_timeout_ms / 1000),
        )
        browser = playwright.chromium.connect_over_cdp(endpoint)
        try:
            if not browser.contexts:
                raise RuntimeError(
                    "public browser CDP attach succeeded but no browser context was available"
                )
            context = browser.contexts[0]
            apply_stealth(context)
            page = context.new_page()
            try:
                self._load_browser_page(
                    page,
                    url,
                    playwright_timeout_error=playwright_timeout_error,
                )
                return page.content()
            finally:
                page.close()
        finally:
            try:
                browser.disconnect()
            except AttributeError:
                pass

    def _load_browser_page(
        self,
        page,
        url: str,
        *,
        playwright_timeout_error,
    ) -> None:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=self.navigation_timeout_ms,
        )
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except playwright_timeout_error:
            self._log(f"[WARN] networkidle timeout for public URL: {url}")
        self.cancel_check()
        page.wait_for_timeout(3000)

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
        self._increment_success_counter(stage_name)
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
        self._increment_quality_counter(quality)
        self._log(
            "[PUBLIC-FETCH-STAGE] "
            f"url={url} stage={stage_name} status=needs_upgrade "
            f"quality={quality} chars={count_meaningful_visible_chars(text)}"
        )

    def _log(self, message: str) -> None:
        if self.report is not None:
            self.report.log(message)

    def _increment_success_counter(self, stage_name: str) -> None:
        counter_name = {
            "scrapling_static": "public_url_scrapling_static_success",
            "scrapling_dynamic": "public_url_scrapling_dynamic_success",
            "legacy_markitdown": "public_url_markitdown_success",
            "legacy_playwright_html": "public_url_playwright_success",
        }.get(stage_name)
        if counter_name is not None:
            self._increment_report_stat(counter_name)

    def _increment_quality_counter(self, quality: str) -> None:
        if quality == "blank":
            self._increment_report_stat("public_url_blank")
        elif quality == "blocked":
            self._increment_report_stat("public_url_blocked")

    def _count_quality_retry(self, reason: str | None) -> None:
        if reason in {"blank", "blocked", "too_short"}:
            self._increment_report_stat("public_url_quality_retry")

    def _increment_report_stat(self, stat_name: str) -> None:
        if self.report is None:
            return
        current = getattr(self.report.stats, stat_name, None)
        if current is None:
            return
        setattr(self.report.stats, stat_name, current + 1)
        self.report.flush_running()


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
