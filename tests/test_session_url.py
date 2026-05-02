from pathlib import Path

from lmit.config import SessionSiteConfig
from lmit.fetchers.session_url import SessionUrlFetcher
from lmit.reports import ConversionReport
from lmit.sessions.browser_provider import (
    BrowserFetchResult,
    PlaywrightBrowserProvider,
    SessionLoginRequired,
)
from lmit.sessions.strategies.facebook import (
    clean_facebook_text,
    crop_desktop_facebook_chrome,
    facebook_context_options,
    facebook_mobile_url,
    facebook_target_url,
    facebook_text_requires_login,
)


def test_facebook_mobile_url_rewrites_www():
    assert (
        facebook_mobile_url("https://www.facebook.com/share/p/abc/")
        == "https://m.facebook.com/share/p/abc/"
    )


def test_facebook_target_url_keeps_desktop_url():
    assert (
        facebook_target_url("https://www.facebook.com/share/p/abc/", "desktop")
        == "https://www.facebook.com/share/p/abc/"
    )


def test_facebook_context_options_desktop_not_mobile():
    options = facebook_context_options("desktop")

    assert options["viewport"] == {"width": 1365, "height": 900}
    assert "is_mobile" not in options


def test_clean_facebook_text_strips_private_use_icons():
    assert clean_facebook_text("\U000f1678\nHello\n\n\nWorld\ue000") == "Hello\n\nWorld"


def test_crop_desktop_facebook_chrome_starts_at_post_marker():
    text = "\n".join(
        [
            "Facebook 功能表",
            "Neo Chen",
            "Roger's Letter 的貼文",
            "開源了一個Auto Research小工具，做投資研究用的。",
        ]
    )

    assert crop_desktop_facebook_chrome(text).startswith("Roger's Letter 的貼文")


def test_facebook_text_requires_login_detects_login_wall():
    assert facebook_text_requires_login("登入 Facebook 即可繼續")


class FakePlaywrightError(Exception):
    pass


class FakePlaywrightTimeoutError(Exception):
    pass


class FakeProvider:
    name = "fake"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def fetch_once(self, url, site, *, sync_playwright, playwright_timeout_error):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return BrowserFetchResult(
            markdown=outcome,
            provider=self.name,
            render_mode=site.render_mode,
            target_url=url,
            final_url=f"{url}?done=1",
        )


class DummyAdapter:
    pass


def _site(tmp_path: Path, *, retry_count: int = 1, **overrides) -> SessionSiteConfig:
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")
    payload = dict(
        name="example",
        domains=["example.com"],
        login_url="https://example.com/login",
        state_file=state,
        headless=True,
        wait_ms=0,
        retry_count=retry_count,
        retry_backoff_ms=0,
    )
    payload.update(overrides)
    return SessionSiteConfig(**payload)


def test_session_url_fetcher_retries_provider_errors(tmp_path: Path):
    report = ConversionReport()
    provider = FakeProvider([FakePlaywrightTimeoutError("slow"), "ok"])
    fetcher = SessionUrlFetcher(
        adapter=DummyAdapter(),
        work_dir=tmp_path,
        report=report,
        provider=provider,
        playwright_api=(FakePlaywrightError, FakePlaywrightTimeoutError, object()),
    )

    result = fetcher.fetch("https://example.com/private", _site(tmp_path))

    assert result == "ok"
    assert provider.calls == 2
    assert any("[SESSION-RETRY]" in line for line in report.lines)
    assert any("provider=fake" in line for line in report.lines)


def test_session_url_fetcher_recaptures_on_session_login_required(tmp_path: Path):
    report = ConversionReport()
    provider = FakeProvider([SessionLoginRequired("login"), "ok"])
    captures = []

    def capture(site, report):
        captures.append(site.name)

    fetcher = SessionUrlFetcher(
        adapter=DummyAdapter(),
        work_dir=tmp_path,
        report=report,
        provider=provider,
        capture_session=capture,
        playwright_api=(FakePlaywrightError, FakePlaywrightTimeoutError, object()),
    )

    result = fetcher.fetch("https://example.com/private", _site(tmp_path))

    assert result == "ok"
    assert captures == ["example"]
    assert any("[SESSION-EXPIRED]" in line for line in report.lines)


def test_playwright_provider_launches_cdp_profile_when_endpoint_missing(
    tmp_path: Path,
    monkeypatch,
):
    calls: dict[str, object] = {"waits": 0}
    executable = tmp_path / "msedge.exe"
    executable.write_text("", encoding="utf-8")
    site = _site(
        tmp_path,
        name="reddit",
        login_connect_over_cdp=True,
        login_cdp_port=9444,
        login_persistent_profile_dir=tmp_path / "reddit_profile",
        browser_executable_path=executable,
    )

    def fake_wait_for_cdp_endpoint(endpoint: str, *, timeout_seconds: float) -> None:
        calls["waits"] = int(calls["waits"]) + 1
        raise TimeoutError("not ready")

    class FakePopen:
        def __init__(self, args, **kwargs):
            calls["popen_args"] = args
            calls["popen_kwargs"] = kwargs

    monkeypatch.setattr(
        "lmit.sessions.browser_provider.wait_for_cdp_endpoint",
        fake_wait_for_cdp_endpoint,
    )
    monkeypatch.setattr("lmit.sessions.browser_provider.subprocess.Popen", FakePopen)

    report = ConversionReport()
    provider = PlaywrightBrowserProvider(
        adapter=DummyAdapter(),
        work_dir=tmp_path,
        report=report,
    )

    provider._ensure_cdp_browser(
        site,
        port=9444,
        target_url="https://www.reddit.com/r/LocalLLaMA/s/abc",
    )

    assert calls["waits"] == 1
    popen_args = calls["popen_args"]
    assert str(executable) == popen_args[0]
    assert "--remote-debugging-port=9444" in popen_args
    assert f"--user-data-dir={tmp_path / 'reddit_profile'}" in popen_args
    assert "https://www.reddit.com/r/LocalLLaMA/s/abc" in popen_args
    assert any("[SESSION-BROWSER-LAUNCH]" in line for line in report.lines)
