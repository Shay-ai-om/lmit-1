from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "dclid",
    "mc_cid",
    "mc_eid",
    "mibextid",
    "sfnsn",
}

_TRACKING_QUERY_PREFIXES = ("utm_",)

_GENERIC_MOBILE_QUERY_PARAMS = {
    "mo_device",
}

_TIEBA_DROP_QUERY_PARAMS = {
    "is_jingpost",
}


@dataclass(frozen=True)
class NormalizedPublicUrl:
    url: str
    reasons: tuple[str, ...] = ()


def normalize_public_url(url: str) -> NormalizedPublicUrl:
    parts = urlsplit(url)
    host = parts.netloc.lower()
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    normalized_items: list[tuple[str, str]] = []
    reasons: list[str] = []

    for key, value in query_items:
        lowered = key.lower()
        if lowered in _TRACKING_QUERY_PARAMS or lowered.startswith(_TRACKING_QUERY_PREFIXES):
            reasons.append(f"drop_query:{lowered}")
            continue
        if lowered in _GENERIC_MOBILE_QUERY_PARAMS:
            reasons.append(f"drop_query:{lowered}")
            continue
        if host == "tieba.baidu.com" and lowered in _TIEBA_DROP_QUERY_PARAMS:
            reasons.append(f"drop_query:{lowered}")
            continue
        normalized_items.append((key, value))

    normalized_fragment = parts.fragment
    if host == "tieba.baidu.com" and parts.fragment:
        normalized_fragment = ""
        reasons.append("drop_fragment")

    normalized = urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(normalized_items, doseq=True),
            normalized_fragment,
        )
    )
    return NormalizedPublicUrl(url=normalized, reasons=tuple(dict.fromkeys(reasons)))
