from __future__ import annotations

from pathlib import Path

from lmit.config import PublicFetchConfig, default_config, load_config


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
                'scrapling_cleanup = "none"',
                "scrapling_block_ads = false",
                "request_timeout_seconds = 12",
                "navigation_timeout_ms = 15000",
                "min_meaningful_chars = 123",
                'browser_channel = "chrome"',
                "browser_connect_over_cdp = true",
                "browser_cdp_port = 9333",
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_path, cwd=tmp_path)

    assert cfg.public_fetch == PublicFetchConfig(
        provider="scrapling",
        enable_scrapling=False,
        enable_scrapling_dynamic=False,
        scrapling_cleanup="none",
        scrapling_block_ads=False,
        request_timeout_seconds=12,
        navigation_timeout_ms=15000,
        min_meaningful_chars=123,
        browser_channel="chrome",
        browser_executable_path=None,
        browser_connect_over_cdp=True,
        browser_cdp_port=9333,
    )
