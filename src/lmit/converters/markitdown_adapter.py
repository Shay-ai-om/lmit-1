from __future__ import annotations

from pathlib import Path
from typing import Any
import requests


DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
ACCEPT_HEADER = "text/markdown, text/html;q=0.9, text/plain;q=0.8, */*;q=0.1"


class _TimeoutSession(requests.Session):
    def __init__(self, timeout_seconds: float):
        super().__init__()
        self._timeout_seconds = float(timeout_seconds)
        self.headers.update({"Accept": ACCEPT_HEADER})

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", self._timeout_seconds)
        return super().request(method, url, **kwargs)


def build_requests_session(
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> requests.Session:
    return _TimeoutSession(timeout_seconds)


class MarkItDownAdapter:
    def __init__(
        self,
        *,
        enable_plugins: bool = True,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ):
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise RuntimeError(
                "MarkItDown is not installed. Install the project dependencies first."
            ) from exc
        self._md = MarkItDown(
            enable_plugins=enable_plugins,
            requests_session=build_requests_session(request_timeout_seconds),
        )

    def convert_path(self, path: Path) -> str:
        return _result_text(self._md.convert(str(path)))

    def convert_url(self, url: str) -> str:
        return _result_text(self._md.convert(url))


def _result_text(result: Any) -> str:
    if hasattr(result, "text_content"):
        return str(result.text_content)
    return str(result)
