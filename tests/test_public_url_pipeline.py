from __future__ import annotations

from pathlib import Path

import pytest

from lmit.config import PublicFetchConfig
from lmit.fetchers.public_url import PublicUrlFetcher
from lmit.fetchers.public_url_scrapling import PublicUrlScraplingFetcher
from lmit.reports import ConversionReport


LONG_TEXT = "Meaningful public page content. " * 12


class DummyAdapter:
    def __init__(self, *, url_result: str | Exception = LONG_TEXT):
        self.url_result = url_result
        self.convert_url_calls: list[str] = []
        self.convert_path_calls: list[Path] = []

    def convert_url(self, url: str) -> str:
        self.convert_url_calls.append(url)
        if isinstance(self.url_result, Exception):
            raise self.url_result
        return self.url_result

    def convert_path(self, path: Path) -> str:
        self.convert_path_calls.append(path)
        return path.read_text(encoding="utf-8")


class DummyScraplingFetcher:
    def __init__(
        self,
        *,
        static_result: str | Exception = LONG_TEXT,
        dynamic_result: str | Exception = LONG_TEXT,
    ):
        self.static_result = static_result
        self.dynamic_result = dynamic_result
        self.calls: list[tuple[str, str]] = []

    def fetch_static(self, url: str) -> str:
        self.calls.append(("static", url))
        if isinstance(self.static_result, Exception):
            raise self.static_result
        return self.static_result

    def fetch_dynamic(self, url: str) -> str:
        self.calls.append(("dynamic", url))
        if isinstance(self.dynamic_result, Exception):
            raise self.dynamic_result
        return self.dynamic_result


class BrowserOverrideFetcher(PublicUrlFetcher):
    def __init__(self, *args, browser_result: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.browser_result = browser_result

    def _fetch_with_browser(self, url: str) -> str:
        return self.browser_result


class BrowserFailureFetcher(PublicUrlFetcher):
    def __init__(self, *args, browser_exc: Exception, **kwargs):
        super().__init__(*args, **kwargs)
        self.browser_exc = browser_exc

    def _fetch_with_browser(self, url: str) -> str:
        raise self.browser_exc


class FakeResponse:
    def __init__(self, *, html: str = "", text: str = "", markdown: str = "", body: bytes | None = None):
        self.html = html
        self.text = text
        self.markdown = markdown
        self.body = body


def test_public_url_pipeline_uses_static_scrapling_when_quality_is_good(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter()
    scrapling = DummyScraplingFetcher(static_result=LONG_TEXT)

    fetcher = PublicUrlFetcher(
        adapter,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(provider="auto"),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://example.com/article")

    assert result == LONG_TEXT
    assert scrapling.calls == [("static", "https://example.com/article")]
    assert adapter.convert_url_calls == []
    assert any("provider=auto" in line for line in report.lines)
    assert any("scrapling_static" in line for line in report.lines)
    assert any("[PUBLIC-FETCH-DONE]" in line for line in report.lines)


def test_public_url_pipeline_upgrades_blank_static_scrapling_to_dynamic(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter()
    scrapling = DummyScraplingFetcher(static_result="   ", dynamic_result=LONG_TEXT)

    fetcher = PublicUrlFetcher(
        adapter,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(provider="auto", enable_scrapling_dynamic=True),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://example.com/article")

    assert result == LONG_TEXT
    assert scrapling.calls == [
        ("static", "https://example.com/article"),
        ("dynamic", "https://example.com/article"),
    ]
    assert adapter.convert_url_calls == []
    assert any("quality=blank" in line for line in report.lines)
    assert any("upgrade=scrapling_dynamic" in line for line in report.lines)


def test_public_url_pipeline_falls_back_to_legacy_after_scrapling_failure(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter(url_result=LONG_TEXT)
    scrapling = DummyScraplingFetcher(static_result=RuntimeError("scrapling failed"))

    fetcher = PublicUrlFetcher(
        adapter,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(provider="auto", enable_scrapling_dynamic=False),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://example.com/article")

    assert result == LONG_TEXT
    assert scrapling.calls == [("static", "https://example.com/article")]
    assert adapter.convert_url_calls == ["https://example.com/article"]
    assert any("scrapling_static" in line and "failed" in line for line in report.lines)
    assert any("legacy_markitdown" in line for line in report.lines)


def test_public_url_pipeline_legacy_provider_bypasses_scrapling(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter(url_result="legacy markdown")
    scrapling = DummyScraplingFetcher()

    fetcher = PublicUrlFetcher(
        adapter,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(provider="legacy"),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://example.com/article")

    assert result == "legacy markdown"
    assert scrapling.calls == []
    assert adapter.convert_url_calls == ["https://example.com/article"]
    assert any("provider=legacy" in line for line in report.lines)
    assert any("legacy_markitdown" in line for line in report.lines)


def test_public_url_pipeline_logs_low_quality_browser_fallback(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter(url_result="short legacy text")

    fetcher = BrowserOverrideFetcher(
        adapter,
        browser_result="   ",
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(provider="auto", enable_scrapling=False),
    )

    result = fetcher.fetch("https://example.com/article")

    assert result == "   "
    assert any(
        "stage=legacy_playwright_html" in line
        and "status=needs_upgrade" in line
        and "quality=blank" in line
        for line in report.lines
    )
    assert not any(
        "stage=legacy_playwright_html" in line and "status=ok" in line
        for line in report.lines
    )


def test_scrapling_fetcher_basic_cleanup_keeps_common_noise():
    html = """
    <html>
      <body>
        <header>Site Header</header>
        <nav>Docs Pricing</nav>
        <main><article><h1>Useful article</h1><p>Main body text.</p></article></main>
        <div class="cookie-banner">Accept cookies</div>
      </body>
    </html>
    """
    fetcher = PublicUrlScraplingFetcher(PublicFetchConfig(scrapling_cleanup="basic"))

    text = fetcher._normalize_response_text(FakeResponse(html=html))

    assert "Useful article" in text
    assert "Accept cookies" in text
    assert "Docs Pricing" in text


def test_scrapling_fetcher_ai_targeted_cleanup_removes_common_noise():
    html = """
    <html>
      <body>
        <header>Site Header</header>
        <nav>Docs Pricing</nav>
        <main><article><h1>Useful article</h1><p>Main body text.</p></article></main>
        <div class="cookie-banner">Accept cookies</div>
        <aside>Related links</aside>
      </body>
    </html>
    """
    fetcher = PublicUrlScraplingFetcher(PublicFetchConfig(scrapling_cleanup="ai_targeted"))

    text = fetcher._normalize_response_text(FakeResponse(html=html))

    assert "Useful article" in text
    assert "Main body text." in text
    assert "Accept cookies" not in text
    assert "Docs Pricing" not in text
    assert "Related links" not in text


def test_scrapling_fetcher_ai_targeted_prefers_html_over_markdown():
    html = """
    <html>
      <body>
        <nav>Docs Pricing</nav>
        <main><article><h1>Useful article</h1><p>Main body text.</p></article></main>
      </body>
    </html>
    """
    fetcher = PublicUrlScraplingFetcher(PublicFetchConfig(scrapling_cleanup="ai_targeted"))

    text = fetcher._normalize_response_text(
        FakeResponse(
            html=html,
            markdown="Cookie wall\nDocs Pricing\nTiny markdown fallback",
        )
    )

    assert "Useful article" in text
    assert "Main body text." in text
    assert "Tiny markdown fallback" not in text
    assert "Docs Pricing" not in text


def test_scrapling_fetcher_uses_fake_loader_for_dynamic_fetch():
    captured: dict[str, object] = {}

    class FakeStaticFetcher:
        @staticmethod
        def get(url: str, **kwargs):
            captured["static_url"] = url
            captured["static_kwargs"] = kwargs
            return FakeResponse(html="<main>static</main>")

    class FakeDynamicFetcher:
        @staticmethod
        def fetch(url: str, **kwargs):
            captured["dynamic_url"] = url
            captured["dynamic_kwargs"] = kwargs
            return FakeResponse(html="<main>dynamic text</main>")

    fetcher = PublicUrlScraplingFetcher(
        PublicFetchConfig(
            scrapling_cleanup="basic",
            scrapling_block_ads=True,
            navigation_timeout_ms=12345,
        )
    )
    fetcher._load_fetchers = lambda: (FakeStaticFetcher, FakeDynamicFetcher)

    result = fetcher.fetch_dynamic("https://example.com/article")

    assert result == "dynamic text"
    assert captured["dynamic_url"] == "https://example.com/article"
    assert captured["dynamic_kwargs"]["timeout"] == 12345
    assert captured["dynamic_kwargs"]["network_idle"] is True
    assert captured["dynamic_kwargs"]["headless"] is True
    assert captured["dynamic_kwargs"]["disable_resources"] is True
    assert "doubleclick.net" in captured["dynamic_kwargs"]["blocked_domains"]


def test_public_url_pipeline_auto_path_preserves_original_legacy_exception(tmp_path: Path):
    original_exc = RuntimeError("markitdown failed")
    browser_exc = RuntimeError("browser failed")
    adapter = DummyAdapter(url_result=original_exc)

    fetcher = BrowserFailureFetcher(
        adapter,
        browser_exc=browser_exc,
        work_dir=tmp_path,
        report=ConversionReport(),
        public_fetch=PublicFetchConfig(provider="auto", enable_scrapling=False),
    )

    with pytest.raises(RuntimeError, match="markitdown failed") as exc_info:
        fetcher.fetch("https://example.com/article")

    assert exc_info.value is original_exc
    assert exc_info.value.__cause__ is browser_exc
