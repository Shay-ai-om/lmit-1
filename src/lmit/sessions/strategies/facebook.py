from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

from lmit.config import SessionSiteConfig
from lmit.converters.markitdown_adapter import MarkItDownAdapter
from lmit.reports import ConversionReport
from lmit.sessions.browser_provider import SessionLoginRequired
from lmit.sessions.strategies.base import DefaultSessionStrategy


class FacebookSessionStrategy(DefaultSessionStrategy):
    wait_for_networkidle = False

    def __init__(self, site: SessionSiteConfig):
        super().__init__(site)
        self.render_mode = facebook_render_mode(site)

    def target_url(self, url: str) -> str:
        return facebook_target_url(url, self.render_mode)

    def context_options(self) -> dict:
        return facebook_context_options(self.render_mode)

    def after_load(self, page, report: ConversionReport) -> None:
        if self.render_mode == "mobile":
            expand_facebook_body(page, report)

    def extract_markdown(
        self,
        page,
        *,
        adapter: MarkItDownAdapter,
        temp_html,
        target_url: str,
        final_url: str,
    ) -> str:
        body_text = page.inner_text("body", timeout=10000)
        text = clean_facebook_text(body_text)
        if facebook_text_requires_login(text):
            raise SessionLoginRequired(f"login prompt detected while fetching {target_url}")
        return f"Fetched URL: {target_url}\n\nFinal URL: {final_url}\n\n{text}\n"


def is_facebook_site(site: SessionSiteConfig) -> bool:
    return site.name.lower() == "facebook" or any("facebook.com" in d for d in site.domains)


def facebook_mobile_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host in {"www.facebook.com", "facebook.com", "mbasic.facebook.com"}:
        parsed = parsed._replace(netloc="m.facebook.com")
    return urlunparse(parsed)


def facebook_target_url(url: str, mode: str) -> str:
    if mode == "mobile":
        return facebook_mobile_url(url)
    if mode == "mbasic":
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host in {"www.facebook.com", "facebook.com", "m.facebook.com"}:
            parsed = parsed._replace(netloc="mbasic.facebook.com")
        return urlunparse(parsed)
    return url


def facebook_render_mode(site: SessionSiteConfig) -> str:
    mode = site.render_mode.lower().strip()
    if mode not in {"desktop", "mobile", "mbasic"}:
        return "desktop"
    return mode


def facebook_context_options(mode: str) -> dict:
    if mode == "mobile":
        return {
            "user_agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            ),
            "viewport": {"width": 390, "height": 844},
            "is_mobile": True,
            "has_touch": True,
        }
    return {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1365, "height": 900},
    }


def clean_facebook_text(text: str) -> str:
    text = re.sub(r"[\ue000-\uf8ff]", "", text)
    text = re.sub(r"[\U000f0000-\U000ffffd\U00100000-\U0010fffd]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = crop_desktop_facebook_chrome(text)
    return text.strip()


def crop_desktop_facebook_chrome(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.endswith("\u7684\u8cbc\u6587") and len(stripped) <= 80:
            return "\n".join(lines[index:])
    return text


def facebook_text_requires_login(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "log in to facebook",
        "log into facebook",
        "you must log in",
        "登入 facebook",
        "登入或註冊即可查看",
        "登入即可繼續",
    ]
    return any(marker in lowered for marker in markers)


def expand_facebook_body(page, report: ConversionReport) -> None:
    labels = [
        "\u67e5\u770b\u66f4\u591a",  # 查看更多
        "\u986f\u793a\u66f4\u591a",  # 顯示更多
        "\u770b\u66f4\u591a",  # 看更多
        "See more",
    ]
    clicked = 0
    for _ in range(5):
        clicked_this_round = False
        for label in labels:
            locator = page.locator(f"text={label}")
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                try:
                    locator.nth(index).click(timeout=2500, force=True)
                    page.wait_for_timeout(1500)
                    clicked += 1
                    clicked_this_round = True
                    break
                except Exception:
                    continue
            if clicked_this_round:
                break
        if not clicked_this_round:
            break

    if clicked:
        report.log(f"[FACEBOOK-EXPANDED] clicked see-more controls: {clicked}")
