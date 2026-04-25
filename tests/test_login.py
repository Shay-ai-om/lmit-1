from pathlib import Path

from lmit.config import SessionSiteConfig
from lmit.sessions.launch import (
    STEALTH_INIT_SCRIPT,
    apply_stealth,
    browser_launch_options,
    login_profile_dir,
    login_uses_persistent_context,
)


def _site(tmp_path: Path, **overrides) -> SessionSiteConfig:
    payload = {
        "name": "reddit",
        "domains": ["reddit.com"],
        "login_url": "https://www.reddit.com/login/",
        "state_file": tmp_path / "reddit_state.json",
        "headless": True,
        "wait_ms": 8000,
        "render_mode": "desktop",
        "navigation_timeout_ms": 90000,
        "retry_count": 2,
        "retry_backoff_ms": 1500,
        "browser_channel": None,
        "login_use_persistent_context": False,
        "login_persistent_profile_dir": None,
    }
    payload.update(overrides)
    return SessionSiteConfig(**payload)


def test_browser_launch_options_include_channel_when_configured(tmp_path: Path):
    site = _site(tmp_path, browser_channel="msedge")

    assert browser_launch_options(site, headless=False) == {
        "headless": False,
        "ignore_default_args": ["--enable-automation"],
        "args": ["--disable-blink-features=AutomationControlled"],
        "channel": "msedge",
    }


def test_login_uses_persistent_context_when_enabled(tmp_path: Path):
    site = _site(tmp_path, login_use_persistent_context=True)

    assert login_uses_persistent_context(site) is True
    assert login_profile_dir(site) == tmp_path / "reddit_profile"


def test_login_profile_dir_prefers_explicit_path(tmp_path: Path):
    profile_dir = tmp_path / ".lmit_work" / "browser_profiles" / "reddit"
    site = _site(tmp_path, login_persistent_profile_dir=profile_dir)

    assert login_uses_persistent_context(site) is True
    assert login_profile_dir(site) == profile_dir


def test_apply_stealth_adds_init_script():
    class FakeContext:
        def __init__(self):
            self.scripts = []

        def add_init_script(self, script):
            self.scripts.append(script)

    context = FakeContext()

    apply_stealth(context)

    assert context.scripts == [STEALTH_INIT_SCRIPT]
