from __future__ import annotations

import hashlib
import json

from lmit.config import AppConfig


def conversion_key(cfg: AppConfig) -> str:
    payload = {
        "version": 9,
        "fetch_urls": cfg.conversion.fetch_urls,
        "enable_markitdown_plugins": cfg.conversion.enable_markitdown_plugins,
        "blank_note_for_images": cfg.conversion.blank_note_for_images,
        "supported_exts": sorted(cfg.scan.supported_exts),
        "public_fetch": {
            # Bump this when the public-URL extraction pipeline changes in a
            # way that should invalidate previously "unchanged" outputs.
            "algorithm": 2,
            "provider": cfg.public_fetch.provider,
            "enable_scrapling": cfg.public_fetch.enable_scrapling,
            "enable_scrapling_dynamic": cfg.public_fetch.enable_scrapling_dynamic,
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
