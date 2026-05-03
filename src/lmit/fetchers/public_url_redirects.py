from __future__ import annotations

from urllib.parse import urlsplit

import requests


_REDIRECT_ONLY_HOSTS = {
    "search.app",
    "www.search.app",
}

_REDIRECT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}


def resolve_public_url_redirect(url: str, *, timeout_seconds: int) -> str | None:
    if not _should_resolve_redirect(url):
        return None

    response = requests.get(
        url,
        allow_redirects=True,
        headers=_REDIRECT_HEADERS,
        stream=True,
        timeout=max(1, int(timeout_seconds)),
    )
    try:
        final_url = response.url
    finally:
        response.close()

    if not final_url or final_url == url:
        return None
    if not _is_http_url(final_url):
        return None
    return final_url


def _should_resolve_redirect(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        return False
    return parts.hostname in _REDIRECT_ONLY_HOSTS


def _is_http_url(url: str) -> bool:
    return urlsplit(url).scheme in {"http", "https"}
