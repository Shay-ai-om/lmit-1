from __future__ import annotations

from pathlib import Path
from threading import Event, Thread

import pytest

from lmit.cancellation import ConversionCancelled
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
        stealthy_result: str | Exception = LONG_TEXT,
    ):
        self.static_result = static_result
        self.dynamic_result = dynamic_result
        self.stealthy_result = stealthy_result
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

    def fetch_stealthy(self, url: str) -> str:
        self.calls.append(("stealthy", url))
        if isinstance(self.stealthy_result, Exception):
            raise self.stealthy_result
        return self.stealthy_result


class BrowserOverrideFetcher(PublicUrlFetcher):
    def __init__(self, *args, browser_result: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.browser_result = browser_result

    def _fetch_with_browser(self, url: str, *, force_attached: bool = False) -> str:
        return self.browser_result


class AttachedBrowserOverrideFetcher(PublicUrlFetcher):
    def __init__(self, *args, browser_result: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.browser_result = browser_result
        self.attached_urls: list[str] = []

    def _fetch_with_attached_browser(self, playwright, url: str, *, playwright_timeout_error) -> str:
        self.attached_urls.append(url)
        return self.browser_result


class BrowserFailureFetcher(PublicUrlFetcher):
    def __init__(self, *args, browser_exc: Exception, **kwargs):
        super().__init__(*args, **kwargs)
        self.browser_exc = browser_exc

    def _fetch_with_browser(self, url: str, *, force_attached: bool = False) -> str:
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


def test_public_url_pipeline_normalizes_url_before_fetching(tmp_path: Path):
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

    result = fetcher.fetch(
        "https://tieba.baidu.com/p/9152102978?lp=5027&mo_device=1&is_jingpost=0#/"
    )

    assert result == "legacy markdown"
    assert adapter.convert_url_calls == ["https://tieba.baidu.com/p/9152102978?lp=5027"]
    assert any("[PUBLIC-FETCH-NORMALIZED]" in line for line in report.lines)


def test_public_url_pipeline_resolves_search_app_redirect_before_scrapling(
    tmp_path: Path,
    monkeypatch,
):
    report = ConversionReport()
    adapter = DummyAdapter()
    scrapling = DummyScraplingFetcher(static_result=LONG_TEXT)
    redirect_calls: list[tuple[str, int]] = []

    def fake_resolve_redirect(url: str, *, timeout_seconds: int) -> str | None:
        redirect_calls.append((url, timeout_seconds))
        return "https://sspai.com/post/83644"

    monkeypatch.setattr(
        "lmit.fetchers.public_url.resolve_public_url_redirect",
        fake_resolve_redirect,
    )

    fetcher = PublicUrlFetcher(
        adapter,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(provider="auto", request_timeout_seconds=7),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://search.app/PsqCukaJyRGoUVKq9")

    assert result == LONG_TEXT
    assert redirect_calls == [("https://search.app/PsqCukaJyRGoUVKq9", 7)]
    assert scrapling.calls == [("static", "https://sspai.com/post/83644")]
    assert adapter.convert_url_calls == []
    assert any("[PUBLIC-FETCH-REDIRECT]" in line for line in report.lines)


def test_public_url_pipeline_uses_cdp_first_for_matching_domain(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter()
    scrapling = DummyScraplingFetcher()

    fetcher = BrowserOverrideFetcher(
        adapter,
        browser_result=LONG_TEXT,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(
            provider="auto",
            browser_connect_over_cdp=True,
            browser_cdp_port=9333,
            cdp_first_domains=("baidu.com",),
        ),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://tieba.baidu.com/p/9152102978?lp=5027")

    assert result == LONG_TEXT
    assert scrapling.calls == []
    assert adapter.convert_url_calls == []
    assert report.stats.public_url_playwright_success == 1
    assert any("[PUBLIC-FETCH-CDP-FIRST]" in line for line in report.lines)
    assert any("stage=legacy_playwright_html" in line for line in report.lines)


def test_public_url_pipeline_uses_default_cdp_first_for_baidu(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter()
    scrapling = DummyScraplingFetcher()

    fetcher = BrowserOverrideFetcher(
        adapter,
        browser_result=LONG_TEXT,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(provider="auto"),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://tieba.baidu.com/p/9152102978?lp=5027")

    assert result == LONG_TEXT
    assert scrapling.calls == []
    assert adapter.convert_url_calls == []
    assert any("[PUBLIC-FETCH-CDP-FIRST]" in line for line in report.lines)
    assert any("public_browser_auto_launch=True" in line for line in report.lines)
    assert any("cdp_first=baidu.com" in line for line in report.lines)


def test_public_url_pipeline_skips_cdp_first_for_non_matching_domain(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter()
    scrapling = DummyScraplingFetcher(static_result=LONG_TEXT)

    fetcher = BrowserOverrideFetcher(
        adapter,
        browser_result=RuntimeError("browser should not be used"),
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(
            provider="auto",
            browser_connect_over_cdp=True,
            cdp_first_domains=("baidu.com",),
        ),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://example.com/article")

    assert result == LONG_TEXT
    assert scrapling.calls == [("static", "https://example.com/article")]
    assert adapter.convert_url_calls == []
    assert not any("[PUBLIC-FETCH-CDP-FIRST]" in line for line in report.lines)


def test_public_url_pipeline_falls_back_when_cdp_first_is_blocked(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter()
    scrapling = DummyScraplingFetcher(static_result=LONG_TEXT)

    fetcher = BrowserOverrideFetcher(
        adapter,
        browser_result="百度安全验证\n请完成下方验证后继续操作",
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(
            provider="auto",
            browser_connect_over_cdp=True,
            cdp_first_domains=("tieba.baidu.com",),
        ),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://tieba.baidu.com/p/9152102978?lp=5027")

    assert result == LONG_TEXT
    assert scrapling.calls == [("static", "https://tieba.baidu.com/p/9152102978?lp=5027")]
    assert any("[PUBLIC-FETCH-CDP-FIRST-FALLBACK]" in line for line in report.lines)


def test_public_cdp_auto_launch_starts_browser_when_endpoint_is_missing(
    tmp_path: Path,
    monkeypatch,
):
    calls: dict[str, object] = {"waits": 0}
    executable = tmp_path / "chrome.exe"
    executable.write_text("", encoding="utf-8")

    def fake_wait_for_cdp_endpoint(endpoint: str, *, timeout_seconds: float) -> None:
        calls["waits"] = int(calls["waits"]) + 1
        raise TimeoutError("not ready")

    def fake_browser_executable_for_channel(**kwargs):
        calls["browser_lookup"] = kwargs
        return executable

    class FakePopen:
        def __init__(self, args, **kwargs):
            calls["popen_args"] = args
            calls["popen_kwargs"] = kwargs

    monkeypatch.setattr(
        "lmit.fetchers.public_url.wait_for_cdp_endpoint",
        fake_wait_for_cdp_endpoint,
    )
    monkeypatch.setattr(
        "lmit.fetchers.public_url.browser_executable_for_channel",
        fake_browser_executable_for_channel,
    )
    monkeypatch.setattr("lmit.fetchers.public_url.subprocess.Popen", FakePopen)

    report = ConversionReport()
    fetcher = PublicUrlFetcher(
        DummyAdapter(),
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(
            browser_connect_over_cdp=True,
            browser_cdp_port=9333,
            public_browser_auto_launch=True,
            public_browser_profile_dir=tmp_path / "profile",
        ),
    )

    fetcher._ensure_public_cdp_browser(
        "http://127.0.0.1:9333",
        port=9333,
        url="https://tieba.baidu.com/p/9152102978",
    )

    assert calls["waits"] == 1
    assert calls["browser_lookup"] == {
        "channel": None,
        "executable_path": None,
        "label": "public_fetch",
    }
    popen_args = calls["popen_args"]
    assert str(executable) == popen_args[0]
    assert "--remote-debugging-port=9333" in popen_args
    assert f"--user-data-dir={tmp_path / 'profile'}" in popen_args
    assert "https://tieba.baidu.com/p/9152102978" in popen_args
    assert any("[PUBLIC-BROWSER-LAUNCH]" in line for line in report.lines)


def test_public_browser_waits_until_manual_verification_clears(tmp_path: Path):
    class FakeTimeout(Exception):
        pass

    class FakePage:
        def __init__(self):
            self.body_text = "百度安全验证\n请完成下方验证后继续操作"
            self.waits: list[int] = []
            self.load_states: list[tuple[str, int]] = []

        def goto(self, url, *, wait_until, timeout):
            self.goto_url = url
            self.goto_wait_until = wait_until
            self.goto_timeout = timeout

        def wait_for_load_state(self, state, *, timeout):
            self.load_states.append((state, timeout))

        def wait_for_timeout(self, timeout):
            self.waits.append(timeout)
            if len(self.waits) >= 2:
                self.body_text = LONG_TEXT

        def inner_text(self, selector, *, timeout):
            assert selector == "body"
            return self.body_text

        def content(self):
            return f"<main>{self.body_text}</main>"

    report = ConversionReport()
    fetcher = PublicUrlFetcher(
        DummyAdapter(),
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(
            public_browser_verification_timeout_seconds=10,
            public_browser_verification_poll_seconds=1,
        ),
    )

    page = FakePage()
    fetcher._load_browser_page(
        page,
        "https://tieba.baidu.com/p/9152102978",
        playwright_timeout_error=FakeTimeout,
        wait_for_verification=True,
    )

    assert page.waits == [3000, 1000, 2000]
    assert ("networkidle", 15000) in page.load_states
    assert ("networkidle", 2000) in page.load_states
    assert any("[PUBLIC-BROWSER-VERIFY-WAIT]" in line for line in report.lines)
    assert any("[PUBLIC-BROWSER-VERIFY-CLEARED]" in line for line in report.lines)


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


def test_public_url_scrapling_dynamic_can_cancel_mid_fetch():
    started = Event()
    release = Event()
    cancel_calls = {"count": 0}

    class ControlledScraplingFetcher(PublicUrlScraplingFetcher):
        def _load_fetchers(self):
            class FakeStaticFetcher:
                @classmethod
                def get(cls, url: str, timeout: int):
                    return LONG_TEXT

            class FakeDynamicFetcher:
                @classmethod
                def fetch(cls, url: str, **kwargs):
                    started.set()
                    release.wait(timeout=5)
                    return LONG_TEXT

            return FakeStaticFetcher, FakeDynamicFetcher

    def cancel_check() -> None:
        cancel_calls["count"] += 1
        if started.is_set() and cancel_calls["count"] >= 2:
            raise ConversionCancelled("stop now")

    fetcher = ControlledScraplingFetcher(
        PublicFetchConfig(),
        cancel_check=cancel_check,
    )

    try:
        with pytest.raises(ConversionCancelled, match="stop now"):
            fetcher.fetch_dynamic("https://example.com/article")
    finally:
        release.set()


def test_public_url_scrapling_dynamic_times_out_when_fetcher_hangs():
    release = Event()
    outcome: list[object] = []

    class ControlledScraplingFetcher(PublicUrlScraplingFetcher):
        def _load_fetchers(self):
            class FakeStaticFetcher:
                @classmethod
                def get(cls, url: str, timeout: int):
                    return LONG_TEXT

            class HangingDynamicFetcher:
                @classmethod
                def fetch(cls, url: str, **kwargs):
                    release.wait(timeout=5)
                    return LONG_TEXT

            return FakeStaticFetcher, HangingDynamicFetcher

    def run_fetch() -> None:
        try:
            ControlledScraplingFetcher(
                PublicFetchConfig(navigation_timeout_ms=50)
            ).fetch_dynamic("https://search.app/PsqCukaJyRGoUVKq9")
        except BaseException as exc:
            outcome.append(exc)
        else:
            outcome.append("returned")

    thread = Thread(target=run_fetch, daemon=True)
    try:
        thread.start()
        thread.join(timeout=0.8)
        still_running = thread.is_alive()
    finally:
        release.set()
        thread.join(timeout=1)

    assert not still_running
    assert len(outcome) == 1
    assert isinstance(outcome[0], TimeoutError)
    assert "Scrapling fetch timed out" in str(outcome[0])


def test_public_url_pipeline_upgrades_blocked_dynamic_scrapling_to_stealthy(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter()
    scrapling = DummyScraplingFetcher(
        static_result="   ",
        dynamic_result="Just a moment... checking your browser",
        stealthy_result=LONG_TEXT,
    )

    fetcher = PublicUrlFetcher(
        adapter,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(
            provider="auto",
            enable_scrapling_dynamic=True,
            enable_scrapling_stealthy=True,
        ),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://example.com/article")

    assert result == LONG_TEXT
    assert scrapling.calls == [
        ("static", "https://example.com/article"),
        ("dynamic", "https://example.com/article"),
        ("stealthy", "https://example.com/article"),
    ]
    assert adapter.convert_url_calls == []
    assert report.stats.public_url_scrapling_stealthy_success == 1
    assert any("from_stage=scrapling_dynamic" in line for line in report.lines)
    assert any("upgrade=scrapling_stealthy" in line for line in report.lines)


def test_public_url_pipeline_auto_upgrades_cloudflare_challenge_to_stealthy(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter()
    scrapling = DummyScraplingFetcher(
        static_result="   ",
        dynamic_result=(
            "Checking if the site connection is secure\n"
            "Cloudflare Ray ID: 123456789"
        ),
        stealthy_result=LONG_TEXT,
    )

    fetcher = PublicUrlFetcher(
        adapter,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(
            provider="auto",
            enable_scrapling_dynamic=True,
            enable_scrapling_stealthy=False,
            enable_scrapling_stealthy_on_cloudflare=True,
            scrapling_stealthy_solve_cloudflare=True,
        ),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://example.com/article")

    assert result == LONG_TEXT
    assert scrapling.calls == [
        ("static", "https://example.com/article"),
        ("dynamic", "https://example.com/article"),
        ("stealthy", "https://example.com/article"),
    ]
    assert adapter.convert_url_calls == []
    assert report.stats.public_url_scrapling_stealthy_success == 1


def test_public_url_pipeline_does_not_auto_stealthy_for_generic_blocked_text(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter(url_result=LONG_TEXT)
    scrapling = DummyScraplingFetcher(
        static_result="   ",
        dynamic_result="Just a moment... checking your browser",
        stealthy_result=LONG_TEXT,
    )

    fetcher = PublicUrlFetcher(
        adapter,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(
            provider="auto",
            enable_scrapling_dynamic=True,
            enable_scrapling_stealthy=False,
            enable_scrapling_stealthy_on_cloudflare=True,
            scrapling_stealthy_solve_cloudflare=True,
        ),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://example.com/article")

    assert result == LONG_TEXT
    assert scrapling.calls == [
        ("static", "https://example.com/article"),
        ("dynamic", "https://example.com/article"),
    ]
    assert adapter.convert_url_calls == ["https://example.com/article"]
    assert not any("upgrade=scrapling_stealthy" in line for line in report.lines)


def test_public_url_pipeline_can_use_stealthy_when_dynamic_is_disabled(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter()
    scrapling = DummyScraplingFetcher(static_result="short", stealthy_result=LONG_TEXT)

    fetcher = PublicUrlFetcher(
        adapter,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(
            provider="auto",
            enable_scrapling_dynamic=False,
            enable_scrapling_stealthy=True,
        ),
        scrapling_fetcher=scrapling,
    )

    result = fetcher.fetch("https://example.com/article")

    assert result == LONG_TEXT
    assert scrapling.calls == [
        ("static", "https://example.com/article"),
        ("stealthy", "https://example.com/article"),
    ]
    assert adapter.convert_url_calls == []
    assert any("from_stage=scrapling_static" in line for line in report.lines)
    assert any("upgrade=scrapling_stealthy" in line for line in report.lines)


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


def test_public_url_pipeline_uses_attached_browser_when_public_cdp_is_enabled(tmp_path: Path):
    report = ConversionReport()
    adapter = DummyAdapter(url_result=RuntimeError("legacy blocked"))

    fetcher = AttachedBrowserOverrideFetcher(
        adapter,
        browser_result=LONG_TEXT,
        work_dir=tmp_path,
        report=report,
        public_fetch=PublicFetchConfig(
            provider="auto",
            enable_scrapling=False,
            browser_connect_over_cdp=True,
            browser_cdp_port=9333,
        ),
    )

    result = fetcher.fetch("https://example.com/article")

    assert result == LONG_TEXT
    assert fetcher.attached_urls == ["https://example.com/article"]
    assert any("stage=legacy_playwright_html" in line and "status=ok" in line for line in report.lines)


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


def test_scrapling_fetcher_ai_targeted_trims_recommended_news_sections():
    html = """
    <html>
      <body>
        <main>
          <article>
            <h1>Major storm makes landfall</h1>
            <p>The main article lead explains what happened.</p>
            <p>Officials said residents should avoid coastal roads.</p>
            <h2>Recommended</h2>
            <ul>
              <li>Markets close higher after rally</li>
              <li>How to prepare for summer outages</li>
            </ul>
          </article>
        </main>
      </body>
    </html>
    """
    fetcher = PublicUrlScraplingFetcher(PublicFetchConfig(scrapling_cleanup="ai_targeted"))

    text = fetcher._normalize_response_text(FakeResponse(html=html))

    assert "Major storm makes landfall" in text
    assert "Officials said residents should avoid coastal roads." in text
    assert "Recommended" not in text
    assert "Markets close higher after rally" not in text


def test_scrapling_fetcher_ai_targeted_prefers_jsonld_article_body_for_news_pages():
    html = """
    <html>
      <head>
        <title>Site title fallback</title>
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "City council approves housing plan",
            "articleBody": "The city council approved a new housing plan after a three-hour debate. Supporters said the policy could speed up construction near transit."
          }
        </script>
      </head>
      <body>
        <main>
          <article>
            <p>Short teaser.</p>
            <section class="related-news">
              <h2>Related articles</h2>
              <p>Another story</p>
            </section>
          </article>
        </main>
      </body>
    </html>
    """
    fetcher = PublicUrlScraplingFetcher(PublicFetchConfig(scrapling_cleanup="ai_targeted"))

    text = fetcher._normalize_response_text(FakeResponse(html=html))

    assert "City council approves housing plan" in text
    assert "The city council approved a new housing plan" in text
    assert "Related articles" not in text
    assert "Another story" not in text


def test_scrapling_fetcher_ai_targeted_prefers_article_body_container_over_sidebar():
    html = """
    <html>
      <body>
        <main>
          <div class="page-shell">
            <aside class="most-read">
              <h2>Most read</h2>
              <p>Celebrity story</p>
            </aside>
            <section class="article-body">
              <h1>Rail operators restore service</h1>
              <p>Morning service resumed after engineers repaired signaling equipment.</p>
              <p>Commuters were advised to expect minor delays through noon.</p>
            </section>
          </div>
        </main>
      </body>
    </html>
    """
    fetcher = PublicUrlScraplingFetcher(PublicFetchConfig(scrapling_cleanup="ai_targeted"))

    text = fetcher._normalize_response_text(FakeResponse(html=html))

    assert "Rail operators restore service" in text
    assert "Morning service resumed after engineers repaired signaling equipment." in text
    assert "Most read" not in text
    assert "Celebrity story" not in text


def test_scrapling_fetcher_ai_targeted_preserves_paragraph_breaks_and_tail_info():
    html = """
    <html>
      <body>
        <main>
          <article>
            <h1>Global chip demand rebounds ｜ Example News</h1>
            <p>Semiconductor orders climbed for a third straight quarter.</p>
            <p>Analysts said automotive and AI demand drove the recovery.</p>
            <p>責任編輯：王小明</p>
            <p>圖／Example News 資料照</p>
          </article>
        </main>
      </body>
    </html>
    """
    fetcher = PublicUrlScraplingFetcher(PublicFetchConfig(scrapling_cleanup="ai_targeted"))

    text = fetcher._normalize_response_text(FakeResponse(html=html))

    assert text.startswith("Global chip demand rebounds ｜ Example News")
    assert "\n\nSemiconductor orders climbed for a third straight quarter.\n\n" in text
    assert "\n\nAnalysts said automotive and AI demand drove the recovery.\n\n" in text
    assert "尾端資訊" in text
    assert "- 責任編輯：王小明" in text
    assert "- 圖片來源：Example News 資料照" in text
    assert "責任編輯：王小明\n\n圖／Example News 資料照" not in text


def test_scrapling_fetcher_ai_targeted_prefers_paragraphed_html_over_flat_jsonld():
    html = """
    <html>
      <head>
        <title>Site fallback title</title>
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "Economic outlook improves",
            "articleBody": "Growth improved in the latest quarter. Business investment also rose."
          }
        </script>
      </head>
      <body>
        <main>
          <article>
            <h1>Economic outlook improves</h1>
            <p>Growth improved in the latest quarter.</p>
            <p>Business investment also rose.</p>
          </article>
        </main>
      </body>
    </html>
    """
    fetcher = PublicUrlScraplingFetcher(PublicFetchConfig(scrapling_cleanup="ai_targeted"))

    text = fetcher._normalize_response_text(FakeResponse(html=html))

    assert "Economic outlook improves" in text
    assert "\n\nGrowth improved in the latest quarter.\n\nBusiness investment also rose." in text


def test_scrapling_fetcher_ai_targeted_drops_json_blob_and_trailing_tag_cloud():
    html = """
    <html>
      <body>
        <main>
          <article>
            <h1>Policy shift draws reaction</h1>
            <p>{"id":123,"title":"Policy shift draws reaction","summary":"JSON blob should disappear"}</p>
            <p>Main article paragraph one.</p>
            <p>Main article paragraph two.</p>
            <p>Editor Wang / 編輯</p>
            <p>市場</p>
            <p>政策</p>
            <p>評論</p>
          </article>
        </main>
      </body>
    </html>
    """
    fetcher = PublicUrlScraplingFetcher(PublicFetchConfig(scrapling_cleanup="ai_targeted"))

    text = fetcher._normalize_response_text(FakeResponse(html=html))

    assert '{"id":123' not in text
    assert "Main article paragraph one." in text
    assert "Main article paragraph two." in text
    assert "- 編輯：Editor Wang" in text
    assert "\n\n市場" not in text
    assert "\n\n政策" not in text
    assert "\n\n評論" not in text


def test_scrapling_fetcher_ai_targeted_splits_inline_image_credit():
    html = """
    <html>
      <body>
        <main>
          <article>
            <h1>Company expands overseas</h1>
            <p>Executives announced a new regional office.</p>
            <p>圖／https://example.com/photo.jpg Expansion plans continue next year.</p>
            <p>責任編輯：陳編輯</p>
          </article>
        </main>
      </body>
    </html>
    """
    fetcher = PublicUrlScraplingFetcher(PublicFetchConfig(scrapling_cleanup="ai_targeted"))

    text = fetcher._normalize_response_text(FakeResponse(html=html))

    assert "Executives announced a new regional office." in text
    assert "圖片來源：https://example.com/photo.jpg" in text
    assert "Expansion plans continue next year." in text
    assert "- 責任編輯：陳編輯" in text


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


def test_scrapling_fetcher_uses_stealthy_fetcher_with_cloudflare_options():
    captured: dict[str, object] = {}

    class FakeStealthyFetcher:
        @staticmethod
        def fetch(url: str, **kwargs):
            captured["stealthy_url"] = url
            captured["stealthy_kwargs"] = kwargs
            return FakeResponse(html="<main>stealthy text</main>")

    fetcher = PublicUrlScraplingFetcher(
        PublicFetchConfig(
            scrapling_cleanup="basic",
            scrapling_block_ads=True,
            navigation_timeout_ms=12345,
            scrapling_stealthy_solve_cloudflare=True,
        )
    )
    fetcher._load_stealthy_fetcher = lambda: FakeStealthyFetcher

    result = fetcher.fetch_stealthy("https://example.com/protected")

    assert result == "stealthy text"
    assert captured["stealthy_url"] == "https://example.com/protected"
    assert captured["stealthy_kwargs"]["timeout"] == 60000
    assert captured["stealthy_kwargs"]["network_idle"] is True
    assert captured["stealthy_kwargs"]["headless"] is True
    assert captured["stealthy_kwargs"]["block_webrtc"] is True
    assert captured["stealthy_kwargs"]["hide_canvas"] is True
    assert captured["stealthy_kwargs"]["solve_cloudflare"] is True
    assert captured["stealthy_kwargs"]["block_ads"] is True
    assert "doubleclick.net" in captured["stealthy_kwargs"]["blocked_domains"]


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
