from __future__ import annotations

from lmit.fetchers.public_url_blocked import is_blocked_public_url_text as _is_blocked_text

DEFAULT_MIN_MEANINGFUL_CHARS = 200


def is_blank_public_url_text(text: str | None) -> bool:
    return text is None or text.strip() == ""


def count_meaningful_visible_chars(text: str | None) -> int:
    if text is None:
        return 0
    return sum(1 for char in text if not char.isspace())


def is_blocked_public_url_text(text: str | None) -> bool:
    if is_blank_public_url_text(text):
        return False
    return _is_blocked_text(text)


def is_too_short_public_url_text(
    text: str | None,
    *,
    min_meaningful_chars: int = DEFAULT_MIN_MEANINGFUL_CHARS,
) -> bool:
    if is_blank_public_url_text(text):
        return False
    return count_meaningful_visible_chars(text) < min_meaningful_chars
