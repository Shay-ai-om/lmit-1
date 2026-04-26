from __future__ import annotations

from pathlib import Path

import pytest

from lmit.cancellation import ConversionCancelled
from lmit.converters.txt_urls import convert_txt_with_urls
from lmit.reports import ConversionReport


class DummyPublicFetcher:
    def __init__(self):
        self.calls: list[str] = []

    def fetch(self, url: str) -> str:
        self.calls.append(url)
        return f"content for {url}"


class DummySessionFetcher:
    def fetch(self, url: str, site) -> str:
        raise AssertionError("session fetch should not run in this test")


class DummySessionManager:
    def site_for_url(self, url: str):
        return None


def test_convert_txt_with_urls_marks_partial_cancellation(tmp_path: Path):
    source = tmp_path / "urls.txt"
    source.write_text(
        "https://example.com/one\nhttps://example.com/two\n",
        encoding="utf-8",
    )
    public_fetcher = DummyPublicFetcher()
    report = ConversionReport()
    calls = {"count": 0}

    def cancel_check() -> None:
        calls["count"] += 1
        if calls["count"] >= 2:
            raise ConversionCancelled("stop now")

    result = convert_txt_with_urls(
        source,
        fetch_urls=True,
        public_fetcher=public_fetcher,
        session_fetcher=DummySessionFetcher(),
        session_manager=DummySessionManager(),
        report=report,
        cancel_check=cancel_check,
    )

    assert result.cancelled is True
    assert result.failed_count == 0
    assert public_fetcher.calls == ["https://example.com/one"]
    assert "[URL_FETCH_CANCELLED]" in result.markdown
    assert any("[CANCELLED]" in line for line in report.lines)
