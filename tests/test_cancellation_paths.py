from __future__ import annotations

from pathlib import Path

import pytest

from lmit.cancellation import ConversionCancelled
from lmit.config import SessionSiteConfig
from lmit.converters.local_file import convert_regular_file
from lmit.fetchers.session_url import SessionUrlFetcher
from lmit.reports import ConversionReport


class DummyAdapter:
    def convert_path(self, path: Path) -> str:
        raise AssertionError("convert_path should not run after cancellation")


class DummyProvider:
    name = "dummy"

    def fetch_once(self, url: str, site, **kwargs):
        raise TimeoutError("retry me")


def test_convert_regular_file_checks_cancellation_before_adapter(tmp_path: Path):
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF-1.0")

    with pytest.raises(ConversionCancelled, match="stop now"):
        convert_regular_file(
            source,
            DummyAdapter(),
            cancel_check=lambda: (_ for _ in ()).throw(ConversionCancelled("stop now")),
        )


def test_session_url_fetcher_can_cancel_during_retry_backoff(tmp_path: Path):
    state_file = tmp_path / "session.json"
    state_file.write_text("{}", encoding="utf-8")
    site = SessionSiteConfig(
        name="example",
        domains=["example.com"],
        login_url="https://example.com/login",
        state_file=state_file,
        headless=True,
        wait_ms=0,
        retry_count=2,
        retry_backoff_ms=500,
    )
    calls = {"count": 0}

    def cancel_check() -> None:
        calls["count"] += 1
        if calls["count"] >= 2:
            raise ConversionCancelled("stop now")

    fetcher = SessionUrlFetcher(
        adapter=DummyAdapter(),
        work_dir=tmp_path,
        report=ConversionReport(),
        provider=DummyProvider(),
        capture_session=lambda site, report: None,
        playwright_api=(RuntimeError, TimeoutError, object()),
        cancel_check=cancel_check,
    )

    with pytest.raises(ConversionCancelled, match="stop now"):
        fetcher.fetch("https://example.com/protected", site)
