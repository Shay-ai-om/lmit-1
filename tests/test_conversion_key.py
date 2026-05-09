from __future__ import annotations

from dataclasses import replace

from lmit.config import MarkItDownConfig, OcrConfig, PublicFetchConfig, default_config
from lmit.conversion_key import conversion_key


def test_conversion_key_changes_when_public_fetch_provider_changes(tmp_path):
    cfg = default_config(cwd=tmp_path)
    legacy_cfg = replace(
        cfg,
        public_fetch=replace(cfg.public_fetch, provider="legacy"),
    )

    assert conversion_key(cfg) != conversion_key(legacy_cfg)


def test_conversion_key_changes_when_public_fetch_cleanup_changes(tmp_path):
    cfg = default_config(cwd=tmp_path)
    none_cfg = replace(
        cfg,
        public_fetch=PublicFetchConfig(
            provider="auto",
            enable_scrapling=True,
            enable_scrapling_dynamic=True,
            scrapling_cleanup="none",
            scrapling_block_ads=True,
            request_timeout_seconds=cfg.public_fetch.request_timeout_seconds,
            navigation_timeout_ms=cfg.public_fetch.navigation_timeout_ms,
            min_meaningful_chars=cfg.public_fetch.min_meaningful_chars,
        ),
    )

    assert conversion_key(cfg) != conversion_key(none_cfg)


def test_conversion_key_changes_when_scrapling_stealthy_changes(tmp_path):
    cfg = default_config(cwd=tmp_path)
    stealthy_cfg = replace(
        cfg,
        public_fetch=replace(cfg.public_fetch, enable_scrapling_stealthy=True),
    )

    assert conversion_key(cfg) != conversion_key(stealthy_cfg)


def test_conversion_key_changes_when_cdp_first_domains_change(tmp_path):
    cfg = default_config(cwd=tmp_path)
    cdp_cfg = replace(
        cfg,
        public_fetch=replace(cfg.public_fetch, cdp_first_domains=("reddit.com",)),
    )

    assert conversion_key(cfg) != conversion_key(cdp_cfg)


def test_conversion_key_changes_when_public_browser_auto_launch_changes(tmp_path):
    cfg = default_config(cwd=tmp_path)
    auto_launch_cfg = replace(
        cfg,
        public_fetch=replace(cfg.public_fetch, public_browser_auto_launch=False),
    )

    assert conversion_key(cfg) != conversion_key(auto_launch_cfg)


def test_conversion_key_changes_when_public_browser_verification_wait_changes(tmp_path):
    cfg = default_config(cwd=tmp_path)
    wait_cfg = replace(
        cfg,
        public_fetch=replace(
            cfg.public_fetch,
            public_browser_verification_timeout_seconds=240,
            public_browser_verification_poll_seconds=5,
        ),
    )

    assert conversion_key(cfg) != conversion_key(wait_cfg)


def test_conversion_key_changes_when_markitdown_llm_changes(tmp_path):
    cfg = default_config(cwd=tmp_path)
    llm_cfg = replace(
        cfg,
        markitdown=MarkItDownConfig(
            llm_enabled=True,
            llm_provider="openai_compatible",
            llm_base_url="https://api.openai.com/v1",
            llm_model="gpt-4.1-mini",
            llm_api_key_env="OPENAI_API_KEY",
            llm_prompt="Describe this image.",
        ),
    )

    assert conversion_key(cfg) != conversion_key(llm_cfg)


def test_conversion_key_changes_when_ocr_provider_changes(tmp_path):
    cfg = default_config(cwd=tmp_path)
    paddle_cfg = replace(
        cfg,
        ocr=OcrConfig(
            provider="paddleocr",
            paddle_lang="ch",
            paddle_use_angle_cls=True,
            paddle_pdf_render_dpi=200,
        ),
    )

    assert conversion_key(cfg) != conversion_key(paddle_cfg)


def test_conversion_key_changes_when_paddle_profile_changes(tmp_path):
    cfg = default_config(cwd=tmp_path)
    structure_cfg = replace(
        cfg,
        ocr=replace(cfg.ocr, provider="paddleocr", paddle_profile="pp_structure"),
    )

    assert conversion_key(cfg) != conversion_key(structure_cfg)


def test_conversion_key_changes_when_paddle_device_acceleration_changes(tmp_path):
    cfg = default_config(cwd=tmp_path)
    gpu_cfg = replace(
        cfg,
        ocr=replace(
            cfg.ocr,
            provider="paddleocr",
            paddle_device="gpu:0",
            paddle_enable_hpi=True,
            paddle_precision="fp16",
        ),
    )

    assert conversion_key(cfg) != conversion_key(gpu_cfg)
