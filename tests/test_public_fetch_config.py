from __future__ import annotations

from pathlib import Path

from lmit.config import (
    MarkItDownConfig,
    OcrConfig,
    PublicFetchConfig,
    default_config,
    load_config,
)


def test_default_config_includes_public_fetch_defaults(tmp_path: Path):
    cfg = default_config(tmp_path)

    assert cfg.public_fetch == PublicFetchConfig()


def test_load_config_overrides_public_fetch_block(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[public_fetch]",
                'provider = "scrapling"',
                "enable_scrapling = false",
                "enable_scrapling_dynamic = false",
                "enable_scrapling_stealthy = true",
                "enable_scrapling_stealthy_on_cloudflare = false",
                "scrapling_stealthy_solve_cloudflare = false",
                'scrapling_cleanup = "none"',
                "scrapling_block_ads = false",
                "request_timeout_seconds = 12",
                "navigation_timeout_ms = 15000",
                "min_meaningful_chars = 123",
                'browser_channel = "chrome"',
                "browser_connect_over_cdp = true",
                "browser_cdp_port = 9333",
                "public_browser_auto_launch = true",
                'public_browser_profile_dir = ".lmit_work/browser_profiles/baidu"',
                "public_browser_verification_timeout_seconds = 240",
                "public_browser_verification_poll_seconds = 5",
                'cdp_first_domains = ["baidu.com", "https://tieba.baidu.com:443/path"]',
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_path, cwd=tmp_path)

    assert cfg.public_fetch == PublicFetchConfig(
        provider="scrapling",
        enable_scrapling=False,
        enable_scrapling_dynamic=False,
        enable_scrapling_stealthy=True,
        enable_scrapling_stealthy_on_cloudflare=False,
        scrapling_stealthy_solve_cloudflare=False,
        scrapling_cleanup="none",
        scrapling_block_ads=False,
        request_timeout_seconds=12,
        navigation_timeout_ms=15000,
        min_meaningful_chars=123,
        browser_channel="chrome",
        browser_executable_path=None,
        browser_connect_over_cdp=True,
        browser_cdp_port=9333,
        public_browser_auto_launch=True,
        public_browser_profile_dir=tmp_path / ".lmit_work" / "browser_profiles" / "baidu",
        public_browser_verification_timeout_seconds=240,
        public_browser_verification_poll_seconds=5,
        cdp_first_domains=("baidu.com", "tieba.baidu.com"),
    )


def test_load_config_overrides_markitdown_llm_block(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[markitdown]",
                "llm_enabled = true",
                'llm_provider = "gemini"',
                'llm_base_url = "https://generativelanguage.googleapis.com/v1beta"',
                'llm_model = "gemini-2.5-flash"',
                'llm_api_key_env = "GEMINI_API_KEY"',
                'llm_prompt = "Describe the image and any visible text."',
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_path, cwd=tmp_path)

    assert cfg.markitdown == MarkItDownConfig(
        llm_enabled=True,
        llm_provider="gemini",
        llm_base_url="https://generativelanguage.googleapis.com/v1beta",
        llm_model="gemini-2.5-flash",
        llm_api_key_env="GEMINI_API_KEY",
        llm_prompt="Describe the image and any visible text.",
    )


def test_load_config_overrides_ocr_block(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[ocr]",
                'provider = "paddleocr"',
                'paddle_profile = "vision"',
                'paddle_lang = "en"',
                "paddle_use_angle_cls = false",
                "paddle_pdf_render_dpi = 240",
                "paddle_structure_use_doc_orientation_classify = false",
                "paddle_structure_use_chart_recognition = false",
                "paddle_structure_merge_layout_blocks = false",
                "paddle_vision_use_doc_preprocessor = false",
                "paddle_vision_format_block_content = false",
                "paddle_vision_merge_layout_blocks = false",
                'paddle_device = "gpu:1"',
                "paddle_enable_hpi = true",
                "paddle_use_tensorrt = true",
                'paddle_precision = "fp16"',
                "paddle_cpu_threads = 12",
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_path, cwd=tmp_path)

    assert cfg.ocr == OcrConfig(
        provider="paddleocr",
        paddle_profile="vision",
        paddle_lang="en",
        paddle_use_angle_cls=False,
        paddle_pdf_render_dpi=240,
        paddle_structure_use_doc_orientation_classify=False,
        paddle_structure_use_chart_recognition=False,
        paddle_structure_merge_layout_blocks=False,
        paddle_vision_use_doc_preprocessor=False,
        paddle_vision_format_block_content=False,
        paddle_vision_merge_layout_blocks=False,
        paddle_device="gpu:1",
        paddle_enable_hpi=True,
        paddle_use_tensorrt=True,
        paddle_precision="fp16",
        paddle_cpu_threads=12,
    )
