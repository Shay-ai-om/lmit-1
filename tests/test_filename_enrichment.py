from pathlib import Path

from lmit.config import OutputNamingConfig
from lmit.filename_enrichment import enriched_output_path, filename_prefix


def _cfg(**overrides) -> OutputNamingConfig:
    values = {
        "enrich_filenames": True,
        "prefix_source": "auto",
        "max_prefix_chars": 64,
        "separator": "__",
    }
    values.update(overrides)
    return OutputNamingConfig(**values)


def test_filename_prefix_uses_first_non_generic_heading():
    markdown = "\n".join(
        [
            "# TXT Source",
            "",
            "## URL Fetched Content",
            "",
            "### URL 1",
            "",
            "# OpenClaw",
            "",
            "A browser automation tool.",
        ]
    )

    assert filename_prefix(markdown, _cfg()) == "OpenClaw"


def test_filename_prefix_handles_bom_before_heading():
    markdown = "\ufeff# Sample Page Title\n\nBody"

    assert filename_prefix(markdown, _cfg()) == "Sample Page Title"


def test_filename_prefix_falls_back_to_meaningful_line():
    markdown = "\n".join(
        [
            "# TXT Source",
            "",
            "Source file: link.txt",
            "",
            "https://example.com/page",
            "",
            "This page explains the deployment flow.",
        ]
    )

    assert filename_prefix(markdown, _cfg()) == "This page explains the deployment flow"


def test_filename_prefix_skips_error_page_titles():
    markdown = "\n".join(
        [
            "# 504 Gateway Time-out",
            "",
            "nginx",
        ]
    )

    assert filename_prefix(markdown, _cfg()) is None


def test_filename_prefix_skips_facebook_unavailable_message():
    markdown = "目前無法查看此內容\n會發生此情況，通常是因為擁有者僅與一小群用戶分享內容。"

    assert filename_prefix(markdown, _cfg()) is None


def test_filename_prefix_skips_youtube_footer_shell():
    markdown = "簡介媒體著作權與我們聯絡創作者廣告開發人員條款隱私權政策與安全性YouTube 運作方式測試新功能"

    assert filename_prefix(markdown, _cfg()) is None


def test_filename_prefix_skips_navigation_until_repo_heading():
    markdown = "\n".join(
        [
            "## Navigation Menu",
            "",
            "# Search code, repositories, users, issues, pull requests...",
            "",
            "# jo-inc/camofox-browser",
        ]
    )

    assert filename_prefix(markdown, _cfg()) == "jo-inc camofox-browser"


def test_filename_prefix_skips_bare_facebook_heading():
    markdown = "\n".join(
        [
            "# Facebook",
            "",
            "鍾均的貼文",
        ]
    )

    assert filename_prefix(markdown, _cfg()) == "鍾均的貼文"


def test_filename_prefix_skips_angle_bracket_url():
    markdown = "<https://zhuanlan.zhihu.com/p/2002485126714644013>"

    assert filename_prefix(markdown, _cfg()) is None


def test_enriched_output_path_sanitizes_windows_filename_chars(tmp_path: Path):
    output_root = tmp_path / "output"
    base = output_root / "note.md"
    markdown = "# A:Title/With*Unsafe?Chars\n\nBody"

    path = enriched_output_path(base, output_root, markdown, _cfg(max_prefix_chars=80))

    assert path == (output_root / "A Title With Unsafe Chars__note.md").resolve()


def test_enriched_output_path_limits_final_filename_length_to_60_chars():
    output_root = Path("output").resolve()
    base = output_root / "very-long-original-name.md"
    markdown = "# " + ("A" * 120) + "\n\nBody"

    path = enriched_output_path(base, output_root, markdown, _cfg(max_prefix_chars=120))

    assert len(path.name) <= 60
    assert path.name.endswith("__very-long-original-name.md")


def test_enriched_output_path_keeps_existing_title_prefix(tmp_path: Path):
    output_root = tmp_path / "output"
    base = output_root / "OpenClaw-notes.md"
    markdown = "# OpenClaw\n\nBody"

    path = enriched_output_path(base, output_root, markdown, _cfg())

    assert path == base.resolve()
