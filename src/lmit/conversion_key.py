from __future__ import annotations

import hashlib
import json

from lmit.config import AppConfig


def conversion_key(cfg: AppConfig) -> str:
    payload = {
        "version": 14,
        "fetch_urls": cfg.conversion.fetch_urls,
        "enable_markitdown_plugins": cfg.conversion.enable_markitdown_plugins,
        "blank_note_for_images": cfg.conversion.blank_note_for_images,
        "supported_exts": sorted(cfg.scan.supported_exts),
        "markitdown": {
            "algorithm": 2,
            "llm_enabled": cfg.markitdown.llm_enabled,
            "llm_provider": cfg.markitdown.llm_provider,
            "llm_base_url": cfg.markitdown.llm_base_url,
            "llm_model": cfg.markitdown.llm_model,
            "llm_api_key_env": cfg.markitdown.llm_api_key_env,
            "llm_prompt": cfg.markitdown.llm_prompt,
        },
        "ocr": {
            "provider": cfg.ocr.provider,
            "paddle_profile": cfg.ocr.paddle_profile,
            "paddle_lang": cfg.ocr.paddle_lang,
            "paddle_device": cfg.ocr.paddle_device,
            "paddle_enable_hpi": cfg.ocr.paddle_enable_hpi,
            "paddle_use_tensorrt": cfg.ocr.paddle_use_tensorrt,
            "paddle_precision": cfg.ocr.paddle_precision,
            "paddle_cpu_threads": cfg.ocr.paddle_cpu_threads,
            "paddle_use_angle_cls": cfg.ocr.paddle_use_angle_cls,
            "paddle_pdf_render_dpi": cfg.ocr.paddle_pdf_render_dpi,
            "paddle_structure_use_doc_orientation_classify": (
                cfg.ocr.paddle_structure_use_doc_orientation_classify
            ),
            "paddle_structure_use_chart_recognition": (
                cfg.ocr.paddle_structure_use_chart_recognition
            ),
            "paddle_structure_merge_layout_blocks": (
                cfg.ocr.paddle_structure_merge_layout_blocks
            ),
            "paddle_vision_use_doc_preprocessor": (
                cfg.ocr.paddle_vision_use_doc_preprocessor
            ),
            "paddle_vision_format_block_content": (
                cfg.ocr.paddle_vision_format_block_content
            ),
            "paddle_vision_merge_layout_blocks": (
                cfg.ocr.paddle_vision_merge_layout_blocks
            ),
        },
        "public_fetch": {
            # Bump this when the public-URL extraction pipeline changes in a
            # way that should invalidate previously "unchanged" outputs.
            "algorithm": 3,
            "provider": cfg.public_fetch.provider,
            "enable_scrapling": cfg.public_fetch.enable_scrapling,
            "enable_scrapling_dynamic": cfg.public_fetch.enable_scrapling_dynamic,
            "enable_scrapling_stealthy": cfg.public_fetch.enable_scrapling_stealthy,
            "enable_scrapling_stealthy_on_cloudflare": (
                cfg.public_fetch.enable_scrapling_stealthy_on_cloudflare
            ),
            "scrapling_stealthy_solve_cloudflare": (
                cfg.public_fetch.scrapling_stealthy_solve_cloudflare
            ),
            "scrapling_cleanup": cfg.public_fetch.scrapling_cleanup,
            "scrapling_block_ads": cfg.public_fetch.scrapling_block_ads,
            "request_timeout_seconds": cfg.public_fetch.request_timeout_seconds,
            "navigation_timeout_ms": cfg.public_fetch.navigation_timeout_ms,
            "min_meaningful_chars": cfg.public_fetch.min_meaningful_chars,
            "browser_channel": cfg.public_fetch.browser_channel,
            "browser_executable_path": (
                str(cfg.public_fetch.browser_executable_path)
                if cfg.public_fetch.browser_executable_path is not None
                else None
            ),
            "browser_connect_over_cdp": cfg.public_fetch.browser_connect_over_cdp,
            "browser_cdp_port": cfg.public_fetch.browser_cdp_port,
            "public_browser_auto_launch": cfg.public_fetch.public_browser_auto_launch,
            "public_browser_profile_dir": (
                str(cfg.public_fetch.public_browser_profile_dir)
                if cfg.public_fetch.public_browser_profile_dir is not None
                else None
            ),
            "public_browser_verification_timeout_seconds": (
                cfg.public_fetch.public_browser_verification_timeout_seconds
            ),
            "public_browser_verification_poll_seconds": (
                cfg.public_fetch.public_browser_verification_poll_seconds
            ),
            "cdp_first_domains": sorted(cfg.public_fetch.cdp_first_domains),
        },
        "session_sites": [
            {
                "name": site.name,
                "domains": sorted(site.domains),
                "render_mode": site.render_mode,
                "navigation_timeout_ms": site.navigation_timeout_ms,
                "retry_count": site.retry_count,
                "retry_backoff_ms": site.retry_backoff_ms,
            }
            for site in cfg.sessions
        ],
    }
    if cfg.output_naming.enrich_filenames:
        payload["output_naming"] = {
            "algorithm": 4,
            "enrich_filenames": cfg.output_naming.enrich_filenames,
            "prefix_source": cfg.output_naming.prefix_source,
            "max_prefix_chars": cfg.output_naming.max_prefix_chars,
            "separator": cfg.output_naming.separator,
        }
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
