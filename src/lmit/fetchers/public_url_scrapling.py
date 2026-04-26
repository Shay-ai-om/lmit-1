from __future__ import annotations

from html import unescape
import json
import re

from lmit.config import PublicFetchConfig


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BLOCK_BREAK_RE = re.compile(
    r"</?(?:article|section|main|div|p|li|ul|ol|h[1-6]|blockquote|br|tr|td|th)\b[^>]*>",
    re.IGNORECASE,
)
_ARTICLE_PARAGRAPH_BREAK_RE = re.compile(
    r"(?:<br\s*/?>|</?(?:article|section|main|div|p|ul|ol|blockquote|figure|figcaption|h[1-6]|table|tr)\b[^>]*>)",
    re.IGNORECASE,
)
_ARTICLE_LINE_BREAK_RE = re.compile(
    r"</?(?:li|td|th)\b[^>]*>",
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
_ARTICLE_NOISY_HINT = (
    r"cookie|consent|banner|popup|modal|advert|ad-|ads|promo|subscribe|newsletter|"
    r"social|share|related|recommend|breadcrumb|most-read|mostread|most-popular|"
    r"popular|trending|latest|read-more|more-news|more-stories|also-read|suggested|"
    r"taboola|outbrain|comment|comments"
)
_NOISY_CONTAINER_RE = re.compile(
    rf"<(?P<tag>[a-z0-9]+)\b"
    rf"(?=[^>]*\b(?:id|class|role|aria-label|data-testid)\s*=\s*['\"][^'\"]*(?:{_NOISY_HINT})[^'\"]*['\"])"
    rf"[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_ARTICLE_NOISY_CONTAINER_RE = re.compile(
    rf"<(?P<tag>[a-z0-9]+)\b"
    rf"(?=[^>]*\b(?:id|class|role|aria-label|data-testid|data-component|itemprop)\s*=\s*['\"][^'\"]*(?:{_ARTICLE_NOISY_HINT})[^'\"]*['\"])"
    rf"[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_JSONLD_SCRIPT_RE = re.compile(
    r"<script\b[^>]*type\s*=\s*['\"]application/ld\+json['\"][^>]*>(?P<body>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_ARTICLE_CONTAINER_HINT = (
    r"article[-_ ]?body|story[-_ ]?body|article[-_ ]?content|post[-_ ]?content|"
    r"entry[-_ ]?content|main[-_ ]?content|content[-_ ]?body|news[-_ ]?content|"
    r"story[-_ ]?content|正文|內文"
)
_ITEMPROP_ARTICLE_RE = re.compile(
    r"<(?P<tag>article|section|main|div)\b(?=[^>]*\bitemprop\s*=\s*['\"]articleBody['\"])[^>]*>"
    r".*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_ARTICLE_TAG_RE = re.compile(
    r"<article\b[^>]*>.*?</article>",
    re.IGNORECASE | re.DOTALL,
)
_ARTICLE_HINTED_RE = re.compile(
    rf"<(?P<tag>article|section|main|div)\b"
    rf"(?=[^>]*\b(?:id|class|role|aria-label|data-testid|data-component)\s*=\s*['\"][^'\"]*(?:{_ARTICLE_CONTAINER_HINT})[^'\"]*['\"])"
    rf"[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_MAIN_TAG_RE = re.compile(
    r"<main\b[^>]*>.*?</main>",
    re.IGNORECASE | re.DOTALL,
)
_H1_TAG_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TITLE_TAG_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TRAILING_INFO_LINE_RE = re.compile(
    r"^(?P<label>圖(?:片)?來源|圖片提供|照片來源|照片提供|圖|責任編輯|編輯|作者|撰文|記者|資料來源|攝影|採訪整理)\s*"
    r"(?:[:：/／-]\s*)?(?P<value>.+?)$",
    re.IGNORECASE,
)
_BYLINE_INFO_LINE_RE = re.compile(
    r"^(?P<value>.+?)\s*/\s*(?P<label>編輯|作者|撰文|記者|攝影|採訪整理)$",
    re.IGNORECASE,
)
_INLINE_IMAGE_INFO_RE = re.compile(
    r"^(?P<prefix>.*?)(?:\s+|^)(?P<label>圖(?:片)?來源|圖片提供|照片來源|照片提供|圖)\s*[:：/／]\s*"
    r"(?P<value>https?://\S+|[^。！？!?\n]+?)(?P<suffix>\s+.*)?$",
    re.IGNORECASE,
)
_INLINE_EDITOR_INFO_RE = re.compile(
    r"^(?P<prefix>.*?)(?:\s+|^)(?P<label>責任編輯|編輯|作者|撰文|記者|資料來源|攝影|採訪整理)\s*[:：]\s*"
    r"(?P<value>[^。！？!?\n]+?)(?P<suffix>\s+.*)?$",
    re.IGNORECASE,
)
_ARTIFACT_LINE_RE = re.compile(
    r"class=|data-[a-z0-9_-]+=|cursor-pointer|{show=|dl_item|dl_block|gtm|Copy\">",
    re.IGNORECASE,
)
_UI_NOISE_LINE_RE = re.compile(
    r"^(收藏|分享|本文出自.+雜誌|立即訂閱|看更多|看更多文章)$",
    re.IGNORECASE,
)
_STOP_SECTION_LINE_RE = re.compile(
    r"^(?:"
    r"related(?:\s+(?:news|stories|articles|coverage|content|reading))?|"
    r"recommended(?:\s+(?:reading|articles|stories|for you))?|"
    r"read more|"
    r"more(?:\s+(?:news|stories|articles|coverage))?|"
    r"latest(?:\s+(?:news|stories|updates))?|"
    r"most read|most popular|trending|popular(?:\s+stories)?|"
    r"you may also like|editor'?s picks|from around the web|"
    r"即時熱門文章|熱門文章|熱門新聞|即時新聞|"
    r"猜你想看|推薦閱讀|延伸閱讀|相關(?:閱讀|新聞|文章)|更多(?:新聞|文章)|熱門(?:新聞|文章)"
    r")[:：]?$",
    re.IGNORECASE,
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
                article_focused = self._extract_article_focused_text(structured_html)
                if article_focused:
                    return article_focused
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

    def _extract_article_focused_text(self, html: str) -> str | None:
        title = self._extract_title_text(html)
        best_title: str | None = None
        best_text: str | None = None
        best_score = -1
        jsonld_candidate = self._extract_jsonld_article_candidate(html)
        if jsonld_candidate is not None:
            headline, body = jsonld_candidate
            article_text = self._normalize_article_text(body, preserve_paragraphs=False)
            if article_text:
                score = self._score_article_candidate(article_text, "jsonld_article_body")
                if score > best_score:
                    best_score = score
                    best_title = headline or title
                    best_text = article_text

        for source_name, candidate_html in self._iter_article_candidates(html):
            pruned_html = self._prune_article_candidate_html(candidate_html)
            article_text = self._normalize_article_text(pruned_html, preserve_paragraphs=True)
            if not article_text:
                continue
            score = self._score_article_candidate(article_text, source_name)
            if score > best_score:
                best_score = score
                best_title = title
                best_text = article_text

        if best_text:
            return self._combine_title_and_body(best_title or title, best_text)
        return None

    def _extract_jsonld_article_candidate(self, html: str) -> tuple[str | None, str] | None:
        best: tuple[str | None, str] | None = None
        best_len = 0
        for match in _JSONLD_SCRIPT_RE.finditer(html):
            payload = match.group("body").strip()
            if not payload:
                continue
            try:
                data = json.loads(unescape(payload))
            except json.JSONDecodeError:
                continue
            for headline, article_body in self._iter_jsonld_article_nodes(data):
                normalized_body = self._normalize_article_text(
                    article_body,
                    preserve_paragraphs=False,
                )
                if not normalized_body:
                    continue
                if len(normalized_body) > best_len:
                    best = (headline, normalized_body)
                    best_len = len(normalized_body)
        return best

    def _iter_jsonld_article_nodes(self, payload: object):
        if isinstance(payload, list):
            for item in payload:
                yield from self._iter_jsonld_article_nodes(item)
            return
        if not isinstance(payload, dict):
            return

        type_value = payload.get("@type")
        normalized_types: list[str] = []
        if isinstance(type_value, list):
            normalized_types = [str(item).strip().lower() for item in type_value]
        elif isinstance(type_value, str):
            normalized_types = [type_value.strip().lower()]

        if any(
            article_type in {"article", "newsarticle", "reportage", "analysisnewsarticle"}
            for article_type in normalized_types
        ):
            article_body = payload.get("articleBody")
            if isinstance(article_body, str) and article_body.strip():
                headline = payload.get("headline")
                yield (
                    str(headline).strip() if isinstance(headline, str) and headline.strip() else None,
                    article_body,
                )

        for value in payload.values():
            yield from self._iter_jsonld_article_nodes(value)

    def _iter_article_candidates(self, html: str):
        seen: set[str] = set()
        patterns = [
            ("itemprop_article_body", _ITEMPROP_ARTICLE_RE),
            ("article_tag", _ARTICLE_TAG_RE),
            ("hinted_container", _ARTICLE_HINTED_RE),
            ("main_tag", _MAIN_TAG_RE),
        ]
        for source_name, pattern in patterns:
            for match in pattern.finditer(html):
                candidate_html = match.group(0).strip()
                if not candidate_html or candidate_html in seen:
                    continue
                seen.add(candidate_html)
                yield source_name, candidate_html

    def _prune_article_candidate_html(self, html: str) -> str:
        cleaned = _HTML_COMMENT_RE.sub(" ", html)
        cleaned = _NOISY_TAG_BLOCK_RE.sub(" ", cleaned)
        cleaned = _ARTICLE_NOISY_CONTAINER_RE.sub(" ", cleaned)
        return cleaned

    def _normalize_article_text(self, text: str, *, preserve_paragraphs: bool) -> str:
        paragraphs = self._cleanup_article_paragraphs(text, preserve_paragraphs=preserve_paragraphs)
        if not paragraphs:
            return ""
        paragraphs = self._drop_json_blob_paragraphs(paragraphs)
        paragraphs = self._split_embedded_metadata_paragraphs(paragraphs)
        paragraphs = self._drop_artifact_paragraphs(paragraphs)
        paragraphs = self._drop_leading_tag_cloud(paragraphs)
        trimmed_lines = self._trim_after_stop_markers(paragraphs)
        trimmed_lines = self._drop_trailing_tag_cloud(trimmed_lines)
        normalized_lines = self._normalize_trailing_info(trimmed_lines)
        return "\n\n".join(normalized_lines).strip()

    def _cleanup_article_paragraphs(self, text: str, *, preserve_paragraphs: bool) -> list[str]:
        if not preserve_paragraphs:
            cleaned = self._cleanup_ai_targeted_text(text)
            return [line for line in cleaned.splitlines() if line.strip()]

        cleaned = _HTML_COMMENT_RE.sub(" ", text)
        cleaned = _NOISY_TAG_BLOCK_RE.sub(" ", cleaned)
        cleaned = _ARTICLE_NOISY_CONTAINER_RE.sub(" ", cleaned)
        cleaned = _ARTICLE_LINE_BREAK_RE.sub("\n", cleaned)
        cleaned = _ARTICLE_PARAGRAPH_BREAK_RE.sub("\n\n", cleaned)
        cleaned = _TAG_RE.sub(" ", cleaned)
        cleaned = unescape(cleaned)
        cleaned = cleaned.replace("\xa0", " ")

        paragraphs: list[str] = []
        for block in re.split(r"\n\s*\n+", cleaned):
            paragraph = _SPACE_RE.sub(" ", block).strip()
            if paragraph:
                paragraphs.append(paragraph)
        return paragraphs

    def _trim_after_stop_markers(self, lines: list[str]) -> list[str]:
        trimmed: list[str] = []
        for line in lines:
            normalized = _SPACE_RE.sub(" ", line).strip()
            if not normalized:
                continue
            if trimmed and len(trimmed) >= 3 and _STOP_SECTION_LINE_RE.fullmatch(normalized):
                break
            trimmed.append(normalized)
        return trimmed

    def _drop_json_blob_paragraphs(self, lines: list[str]) -> list[str]:
        filtered: list[str] = []
        for line in lines:
            stripped = line.strip()
            if (
                stripped.startswith("{")
                and stripped.endswith("}")
                and (stripped.count('":"') >= 2 or stripped.count('","') >= 2)
            ):
                continue
            filtered.append(line)
        return filtered

    def _split_embedded_metadata_paragraphs(self, lines: list[str]) -> list[str]:
        normalized: list[str] = []
        for line in lines:
            parts = self._split_single_metadata_paragraph(line)
            normalized.extend(parts)
        return normalized

    def _split_single_metadata_paragraph(self, line: str) -> list[str]:
        stripped = line.strip()
        match = _INLINE_IMAGE_INFO_RE.match(stripped) or _INLINE_EDITOR_INFO_RE.match(stripped)
        if match is None:
            return [stripped]

        prefix = match.group("prefix").strip()
        label = self._normalize_trailing_info_label(match.group("label"))
        value = match.group("value").strip()
        suffix = (match.group("suffix") or "").strip()

        if label == "圖片來源":
            if value.startswith("http"):
                pieces = value.split(maxsplit=1)
                value = pieces[0]
                if len(pieces) > 1:
                    suffix = f"{pieces[1]} {suffix}".strip()
            elif suffix:
                value = f"{value} {suffix}".strip()
                suffix = ""

        result: list[str] = []
        if prefix:
            result.append(prefix)
        result.append(f"{label}：{value}")
        if suffix:
            result.append(suffix)
        return result or [stripped]

    def _drop_leading_tag_cloud(self, lines: list[str]) -> list[str]:
        if len(lines) < 5:
            return lines

        if len(lines) >= 6 and len(lines[0]) >= 16:
            short_after_title = 0
            cursor = 1
            while cursor < len(lines) and self._is_short_tag_like_line(lines[cursor]):
                short_after_title += 1
                cursor += 1
            if short_after_title >= 4 and any(len(line) >= 40 for line in lines[cursor:]):
                return [lines[0], *lines[cursor:]]

        drop_count = 0
        for line in lines:
            if self._is_short_tag_like_line(line):
                drop_count += 1
                continue
            break

        if drop_count >= 4 and any(len(line) >= 40 for line in lines[drop_count:]):
            return lines[drop_count:]
        return lines

    def _drop_trailing_tag_cloud(self, lines: list[str]) -> list[str]:
        if len(lines) < 5:
            return lines

        keep = list(lines)
        trailing_short = 0
        while keep and self._is_short_tag_like_line(keep[-1]):
            trailing_short += 1
            keep.pop()

        if trailing_short >= 3:
            return keep
        return lines

    def _drop_artifact_paragraphs(self, lines: list[str]) -> list[str]:
        filtered: list[str] = []
        for line in lines:
            if _ARTIFACT_LINE_RE.search(line):
                continue
            if _UI_NOISE_LINE_RE.fullmatch(line.strip()):
                continue
            filtered.append(line)
        return filtered

    def _is_short_tag_like_line(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if len(stripped) > 12:
            return False
        if re.search(r"[。！？!?,，:：/／]", stripped):
            return False
        if " " in stripped:
            return False
        return True

    def _normalize_trailing_info(self, lines: list[str]) -> list[str]:
        body_lines = list(lines)
        tail_items: list[tuple[str, str]] = []
        while body_lines:
            info = self._parse_trailing_info_line(body_lines[-1])
            if info is None:
                break
            tail_items.insert(0, info)
            body_lines.pop()

        if not tail_items:
            return body_lines

        normalized_lines = list(body_lines)
        normalized_lines.append("尾端資訊")
        normalized_lines.extend(f"- {label}：{value}" for label, value in tail_items)
        return normalized_lines

    def _parse_trailing_info_line(self, line: str) -> tuple[str, str] | None:
        stripped = line.strip()
        match = _TRAILING_INFO_LINE_RE.fullmatch(stripped)
        if match is None:
            byline = _BYLINE_INFO_LINE_RE.fullmatch(stripped)
            if byline is None:
                return None
            label = self._normalize_trailing_info_label(byline.group("label"))
            value = _SPACE_RE.sub(" ", byline.group("value")).strip(" -:：/／")
        else:
            label = self._normalize_trailing_info_label(match.group("label"))
            value = _SPACE_RE.sub(" ", match.group("value")).strip(" -:：/／")
        if not value:
            return None
        return label, value

    def _normalize_trailing_info_label(self, label: str) -> str:
        normalized = label.strip().lower()
        if normalized in {"圖", "圖來源", "圖片來源", "圖片提供", "照片來源", "照片提供"}:
            return "圖片來源"
        if normalized == "責任編輯":
            return "責任編輯"
        if normalized == "編輯":
            return "編輯"
        if normalized == "作者":
            return "作者"
        if normalized == "撰文":
            return "撰文"
        if normalized == "記者":
            return "記者"
        if normalized == "資料來源":
            return "資料來源"
        if normalized == "攝影":
            return "攝影"
        if normalized == "採訪整理":
            return "採訪整理"
        return label.strip()

    def _extract_title_text(self, html: str) -> str | None:
        for pattern in (_H1_TAG_RE, _TITLE_TAG_RE):
            match = pattern.search(html)
            if match is None:
                continue
            candidate = self._cleanup_basic_text(match.group(1))
            if candidate:
                return candidate
        return None

    def _combine_title_and_body(self, title: str | None, body: str) -> str:
        if not title:
            return body
        body_prefix = body[: max(200, len(title) + 40)].lower()
        if title.lower() in body_prefix:
            return body
        return f"{title}\n\n{body}".strip()

    def _score_article_candidate(self, text: str, source_name: str) -> int:
        line_count = len([line for line in text.splitlines() if line.strip()])
        paragraph_count = len([block for block in text.split("\n\n") if block.strip()])
        bonus = {
            "jsonld_article_body": 500,
            "itemprop_article_body": 700,
            "article_tag": 500,
            "hinted_container": 300,
            "main_tag": 100,
        }.get(source_name, 0)
        return len(text) + (line_count * 40) + (paragraph_count * 220) + bonus
