from __future__ import annotations

from html import unescape
import re

from lmit.config import PublicFetchConfig


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BLOCK_BREAK_RE = re.compile(
    r"</?(?:article|section|main|div|p|li|ul|ol|h[1-6]|blockquote|br|tr|td|th)\b[^>]*>",
    re.IGNORECASE,
)
_NOISY_TAG_BLOCK_RE = re.compile(
    r"<(?P<tag>script|style|nav|header|footer|aside|form|noscript|svg)\b[^>]*>"
    r".*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_NOISY_HINT = (
    r"cookie|consent|banner|popup|modal|advert|ad-|ads|promo|subscribe|newsletter|"
    r"social|share|related|recommend|breadcrumb"
)
_NOISY_CONTAINER_RE = re.compile(
    rf"<(?P<tag>[a-z0-9]+)\b"
    rf"(?=[^>]*\b(?:id|class|role|aria-label|data-testid)\s*=\s*['\"][^'\"]*(?:{_NOISY_HINT})[^'\"]*['\"])"
    rf"[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_AD_BLOCKED_DOMAINS = {
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "googletagmanager.com",
}


class PublicUrlScraplingFetcher:
    def __init__(self, config: PublicFetchConfig):
        self.config = config

    def fetch_static(self, url: str) -> str:
        fetcher_cls, _ = self._load_fetchers()
        response = fetcher_cls.get(
            url,
            timeout=self.config.request_timeout_seconds,
        )
        return self._normalize_response_text(response)

    def fetch_dynamic(self, url: str) -> str:
        _, dynamic_fetcher_cls = self._load_fetchers()
        kwargs: dict[str, object] = {
            "timeout": self.config.navigation_timeout_ms,
            "network_idle": True,
            "headless": True,
        }
        if self.config.scrapling_block_ads:
            kwargs["disable_resources"] = True
            kwargs["blocked_domains"] = set(_AD_BLOCKED_DOMAINS)
        response = dynamic_fetcher_cls.fetch(url, **kwargs)
        return self._normalize_response_text(response)

    def _load_fetchers(self):
        from scrapling.fetchers import DynamicFetcher, Fetcher

        return Fetcher, DynamicFetcher

    def _normalize_response_text(self, response: object) -> str:
        cleanup_mode = self.config.scrapling_cleanup.strip().lower()
        raw = self._extract_raw_text(response)
        if cleanup_mode == "none":
            return raw
        if cleanup_mode == "ai_targeted":
            structured_html = self._extract_structured_html(response)
            if structured_html is not None:
                return self._cleanup_ai_targeted_text(structured_html)
            return self._cleanup_ai_targeted_text(raw)
        return self._cleanup_basic_text(raw)

    def _extract_raw_text(self, response: object) -> str:
        if isinstance(response, str):
            return response

        for attr_name in ("markdown", "text", "html", "content"):
            value = getattr(response, attr_name, None)
            if isinstance(value, str) and value.strip():
                return value

        body = getattr(response, "body", None)
        if isinstance(body, bytes):
            return body.decode("utf-8", errors="replace")
        if isinstance(body, str):
            return body
        return str(response)

    def _extract_structured_html(self, response: object) -> str | None:
        if isinstance(response, str):
            return response if "<" in response and ">" in response else None

        for attr_name in ("html", "content"):
            value = getattr(response, attr_name, None)
            if isinstance(value, str) and value.strip() and "<" in value and ">" in value:
                return value

        body = getattr(response, "body", None)
        if isinstance(body, bytes):
            decoded = body.decode("utf-8", errors="replace")
            if "<" in decoded and ">" in decoded:
                return decoded
        elif isinstance(body, str) and "<" in body and ">" in body:
            return body
        return None

    def _cleanup_basic_text(self, text: str) -> str:
        cleaned = _HTML_COMMENT_RE.sub(" ", text)
        cleaned = _TAG_RE.sub(" ", cleaned)
        cleaned = unescape(cleaned)
        cleaned = _SPACE_RE.sub(" ", cleaned)
        return cleaned.strip()

    def _cleanup_ai_targeted_text(self, text: str) -> str:
        cleaned = _HTML_COMMENT_RE.sub(" ", text)
        cleaned = _NOISY_TAG_BLOCK_RE.sub(" ", cleaned)
        cleaned = _NOISY_CONTAINER_RE.sub(" ", cleaned)
        cleaned = _BLOCK_BREAK_RE.sub("\n", cleaned)
        cleaned = _TAG_RE.sub(" ", cleaned)
        cleaned = unescape(cleaned)
        lines = [
            _SPACE_RE.sub(" ", line).strip()
            for line in cleaned.splitlines()
        ]
        compact_lines = [line for line in lines if line]
        return "\n".join(compact_lines).strip()
