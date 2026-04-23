from __future__ import annotations

from pathlib import Path
import re
import unicodedata

from lmit.config import OutputNamingConfig
from lmit.path_safety import ensure_within_root


GENERIC_HEADINGS = {
    "txt source",
    "conversion result",
    "image conversion result",
    "url fetched content",
    "original text",
    "extracted urls",
    "navigation menu",
    "facebook 功能表",
    "facebook",
    "search code, repositories, users, issues, pull requests...",
    "provide feedback",
    "saved searches",
    "use saved searches to filter your results more quickly",
}
NOISY_TITLE_MARKERS = (
    "504 gateway time-out",
    "502 bad gateway",
    "403 forbidden",
    "404 not found",
    "access denied",
    "目前無法查看此內容",
    "擁有者僅與一小群用戶分享內容",
    "just a moment",
    "checking your browser",
    "cloudflare ray id",
    "enable javascript and cookies",
    "sign in to continue",
    "log in to continue",
    "youtube 運作方式測試新功能",
    "簡介媒體著作權與我們聯絡創作者廣告開發人員條款隱私權政策",
    "google llc",
)

WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


def enriched_output_path(
    base_output_path: Path,
    output_root: Path,
    markdown: str,
    cfg: OutputNamingConfig,
) -> Path:
    prefix = filename_prefix(markdown, cfg)
    if not prefix:
        return ensure_within_root(base_output_path, output_root)

    original_name = base_output_path.name
    comparable_prefix = _comparison_key(prefix)
    comparable_stem = _comparison_key(base_output_path.stem)
    if comparable_prefix and comparable_stem.startswith(comparable_prefix):
        return ensure_within_root(base_output_path, output_root)

    filename = f"{prefix}{cfg.separator}{original_name}"
    filename = _limit_filename(filename, prefix, original_name, cfg.separator)
    return ensure_within_root(base_output_path.with_name(filename), output_root)


def filename_prefix(markdown: str, cfg: OutputNamingConfig) -> str | None:
    source = cfg.prefix_source.lower().strip()
    if source not in {"auto", "heading", "excerpt"}:
        source = "auto"

    candidates: list[str | None] = []
    if source in {"auto", "heading"}:
        candidates.append(_first_heading(markdown))
    if source in {"auto", "excerpt"}:
        candidates.append(_first_meaningful_line(markdown))

    for candidate in candidates:
        cleaned = _sanitize_prefix(candidate or "", max_chars=cfg.max_prefix_chars)
        if cleaned:
            return cleaned
    return None


def _first_heading(markdown: str) -> str | None:
    for line in markdown.splitlines():
        line = line.lstrip("\ufeff")
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        title = _strip_markdown_inline(match.group(1))
        lowered = title.lower().strip()
        if not title or _is_noisy_candidate(title):
            continue
        if re.fullmatch(r"url\s+\d+", lowered):
            continue
        return title
    return None


def _first_meaningful_line(markdown: str) -> str | None:
    skip_prefixes = (
        "#",
        "- ",
        "* ",
        "source file:",
        "source url:",
        "fetched url:",
        "final url:",
        "registry url:",
    )
    for line in markdown.splitlines():
        stripped = _strip_markdown_inline(line.strip())
        lowered = stripped.lower()
        if not stripped:
            continue
        if _is_noisy_candidate(stripped):
            continue
        if lowered.startswith(skip_prefixes):
            continue
        if stripped.startswith("http://") or stripped.startswith("https://"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            continue
        if len(stripped) >= 6 or stripped.endswith("\u7684\u8cbc\u6587"):
            return stripped
    return None


def _sanitize_prefix(value: str, *, max_chars: int) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" ._-")
    if not value:
        return ""
    value = value[: max(8, max_chars)].rstrip(" ._-")
    if value.lower() in WINDOWS_RESERVED_NAMES:
        value = f"{value}-title"
    return value


def _strip_markdown_inline(value: str) -> str:
    value = value.replace("\ufeff", "")
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"(?<!\w)[*_~]+|[*_~]+(?!\w)", "", value)
    return value.strip()


def _limit_filename(filename: str, prefix: str, original_name: str, separator: str) -> str:
    max_filename_chars = 180
    if len(filename) <= max_filename_chars:
        return filename
    available = max_filename_chars - len(separator) - len(original_name)
    if available < 12:
        available = 12
    trimmed_prefix = prefix[:available].rstrip(" ._-")
    return f"{trimmed_prefix}{separator}{original_name}"


def _comparison_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def _is_noisy_candidate(value: str) -> bool:
    lowered = value.casefold().strip().strip("<>")
    if lowered in GENERIC_HEADINGS:
        return True
    if any(marker in lowered for marker in NOISY_TITLE_MARKERS):
        return True
    if lowered.startswith(("http://", "https://", "http ", "https ", "from http")):
        return True
    if re.fullmatch(r"(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:\s+[^\s]+){1,8}", lowered):
        return True
    return False
