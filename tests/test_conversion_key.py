from __future__ import annotations

from dataclasses import replace

from lmit.config import PublicFetchConfig, default_config
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
