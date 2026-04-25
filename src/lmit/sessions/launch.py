from __future__ import annotations

from pathlib import Path
import sys

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


def login_uses_cdp(site: SessionSiteConfig) -> bool:
    return site.login_connect_over_cdp


def login_cdp_endpoint(site: SessionSiteConfig) -> str:
    return f"http://127.0.0.1:{login_cdp_port(site)}"


def login_cdp_port(site: SessionSiteConfig) -> int:
    if site.login_cdp_port is not None:
        return site.login_cdp_port
    return 9222


def browser_executable_for_site(site: SessionSiteConfig) -> Path:
    if site.browser_executable_path is not None:
        return site.browser_executable_path

    if sys.platform != "win32":
        raise RuntimeError(
            f"{site.name}: browser_executable_path must be configured outside Windows"
        )

    candidates = windows_browser_candidates(site.browser_channel)
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise RuntimeError(
        f"{site.name}: unable to find a browser executable for channel={site.browser_channel!r}. "
        "Set browser_executable_path in the session config."
    )


def login_uses_persistent_context(site: SessionSiteConfig) -> bool:
    return site.login_use_persistent_context or site.login_persistent_profile_dir is not None


def login_profile_dir(site: SessionSiteConfig) -> Path:
    if site.login_persistent_profile_dir is not None:
        return site.login_persistent_profile_dir
    return site.state_file.parent / f"{site.name}_profile"


def windows_browser_candidates(channel: str | None) -> list[Path]:
    channel_name = (channel or "").lower()
    if channel_name == "chrome":
        return [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ]
    if channel_name == "msedge":
        return [
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ]
    return []
