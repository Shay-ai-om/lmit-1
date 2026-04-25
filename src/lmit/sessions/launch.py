from __future__ import annotations

from pathlib import Path

from lmit.config import SessionSiteConfig


def browser_launch_options(site: SessionSiteConfig, *, headless: bool) -> dict:
    options = {"headless": headless}
    if site.browser_channel:
        options["channel"] = site.browser_channel
    return options


def login_uses_persistent_context(site: SessionSiteConfig) -> bool:
    return site.login_use_persistent_context or site.login_persistent_profile_dir is not None


def login_profile_dir(site: SessionSiteConfig) -> Path:
    if site.login_persistent_profile_dir is not None:
        return site.login_persistent_profile_dir
    return site.state_file.parent / f"{site.name}_profile"
