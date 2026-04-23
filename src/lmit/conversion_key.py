from __future__ import annotations

import hashlib
import json

from lmit.config import AppConfig


def conversion_key(cfg: AppConfig) -> str:
    payload = {
        "version": 8,
        "fetch_urls": cfg.conversion.fetch_urls,
        "enable_markitdown_plugins": cfg.conversion.enable_markitdown_plugins,
        "blank_note_for_images": cfg.conversion.blank_note_for_images,
        "supported_exts": sorted(cfg.scan.supported_exts),
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
