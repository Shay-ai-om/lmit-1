from __future__ import annotations

from pathlib import Path

from lmit.config import SessionSiteConfig

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['zh-TW', 'zh', 'en-US', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'plugins', {
  get: () => [
    { name: 'Chrome PDF Plugin' },
    { name: 'Chrome PDF Viewer' },
    { name: 'Native Client' },
  ],
});
"""


def browser_launch_options(site: SessionSiteConfig, *, headless: bool) -> dict:
    options = {
        "headless": headless,
        "ignore_default_args": ["--enable-automation"],
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if site.browser_channel:
        options["channel"] = site.browser_channel
    return options


def apply_stealth(context) -> None:
    context.add_init_script(STEALTH_INIT_SCRIPT)


def login_uses_persistent_context(site: SessionSiteConfig) -> bool:
    return site.login_use_persistent_context or site.login_persistent_profile_dir is not None


def login_profile_dir(site: SessionSiteConfig) -> Path:
    if site.login_persistent_profile_dir is not None:
        return site.login_persistent_profile_dir
    return site.state_file.parent / f"{site.name}_profile"
