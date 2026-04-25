from __future__ import annotations

from pathlib import Path
import json
import sys
import types

import requests

from lmit.converters.markitdown_adapter import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    MarkItDownAdapter,
    build_requests_session,
)
from lmit.fetchers.public_url import PublicUrlFetcher
from lmit.reports import ConversionReport, latest_report_path


def test_build_requests_session_sets_default_timeout(monkeypatch):
    captured: dict[str, object] = {}
    session = build_requests_session(DEFAULT_REQUEST_TIMEOUT_SECONDS)

    def fake_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["timeout"] = kwargs.get("timeout")
        return object()

    monkeypatch.setattr(requests.Session, "request", fake_request)

    session.get("https://example.com")

    assert captured == {
        "method": "GET",
        "url": "https://example.com",
        "timeout": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    }


def test_markitdown_adapter_passes_timeout_session(monkeypatch):
    captured: dict[str, object] = {}

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        types.SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    MarkItDownAdapter(enable_plugins=False)

    session = captured["requests_session"]
    assert captured["enable_plugins"] is False
    assert isinstance(session, requests.Session)
    assert session.headers["Accept"].startswith("text/markdown")


def test_public_url_browser_fallback_sets_navigation_timeout(tmp_path: Path):
    captured: dict[str, object] = {}

    class FakePage:
        def goto(self, url, *, wait_until, timeout):
            captured["goto"] = {
                "url": url,
                "wait_until": wait_until,
                "timeout": timeout,
            }

        def wait_for_load_state(self, state, *, timeout):
            captured["wait_for_load_state"] = {"state": state, "timeout": timeout}

        def wait_for_timeout(self, timeout):
            captured["wait_for_timeout"] = timeout

        def content(self):
            return "<html><body>ok</body></html>"

    class FakeContext:
        def new_page(self):
            return FakePage()

    class FakeBrowser:
        def new_context(self):
            return FakeContext()

        def close(self):
            captured["browser_closed"] = True

    class FakeChromium:
        def launch(self, *, headless):
            captured["headless"] = headless
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeSyncPlaywright:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_module = types.SimpleNamespace(
        TimeoutError=RuntimeError,
        sync_playwright=lambda: FakeSyncPlaywright(),
    )
    monkeypatch_modules = {"playwright.sync_api": fake_module}
    original_modules = {name: sys.modules.get(name) for name in monkeypatch_modules}
    sys.modules.update(monkeypatch_modules)
    try:
        class DummyAdapter:
            def convert_url(self, url: str) -> str:
                raise RuntimeError("primary failed")

            def convert_path(self, path: Path) -> str:
                return path.read_text(encoding="utf-8")

        fetcher = PublicUrlFetcher(
            DummyAdapter(),
            work_dir=tmp_path,
            report=ConversionReport(),
        )

        result = fetcher.fetch("https://example.com")
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    assert "ok" in result
    assert captured["goto"]["url"] == "https://example.com"
    assert captured["goto"]["wait_until"] == "domcontentloaded"
    assert captured["goto"]["timeout"] > 0
    assert captured["wait_for_load_state"] == {"state": "networkidle", "timeout": 15000}
    assert captured["wait_for_timeout"] == 3000
    assert captured["browser_closed"] is True


def test_running_report_updates_without_affecting_latest_final_report(tmp_path: Path):
    report = ConversionReport()
    report.stats.converted = 1
    report.enable_running_report(tmp_path)
    report.log("[OK] alpha.txt -> alpha.md")

    running_json = tmp_path / "conversion_report_running.json"
    payload = json.loads(running_json.read_text(encoding="utf-8"))
    assert payload["stats"]["converted"] == 1
    assert payload["log"] == ["[OK] alpha.txt -> alpha.md"]

    finished = tmp_path / "conversion_report_20260425_010203.json"
    finished.write_text(json.dumps({"stats": {}, "log": []}), encoding="utf-8")

    assert latest_report_path(tmp_path) == finished
