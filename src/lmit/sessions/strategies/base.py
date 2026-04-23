from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from lmit.config import SessionSiteConfig
from lmit.converters.markitdown_adapter import MarkItDownAdapter
from lmit.reports import ConversionReport


class DefaultSessionStrategy:
    wait_for_networkidle = True

    def __init__(self, site: SessionSiteConfig):
        self.site = site
        self.render_mode = site.render_mode.lower().strip() or "desktop"

    def target_url(self, url: str) -> str:
        return url

    def context_options(self) -> dict:
        return {}

    def temp_html_path(self, work_dir: Path, site: SessionSiteConfig, url: str) -> Path:
        tmp_dir = work_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir / f"{site.name}_{sha256(url.encode('utf-8')).hexdigest()[:16]}.html"

    def after_load(self, page, report: ConversionReport) -> None:
        return None

    def extract_markdown(
        self,
        page,
        *,
        adapter: MarkItDownAdapter,
        temp_html: Path,
        target_url: str,
        final_url: str,
    ) -> str:
        temp_html.write_text(page.content(), encoding="utf-8")
        return adapter.convert_path(temp_html)
