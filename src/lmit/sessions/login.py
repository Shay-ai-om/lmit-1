from __future__ import annotations

from time import monotonic

from lmit.config import SessionSiteConfig
from lmit.reports import ConversionReport
from lmit.sessions.launch import (
    browser_launch_options,
    login_profile_dir,
    login_uses_persistent_context,
)
from lmit.sessions.strategies.facebook import is_facebook_site


def capture_session_state(
    site: SessionSiteConfig,
    report: ConversionReport,
    *,
    timeout_seconds: int = 900,
) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for interactive login. Install with "
            "`pip install -e .[session]` and run `playwright install chromium`."
        ) from exc

    site.state_file.parent.mkdir(parents=True, exist_ok=True)
    report.log(f"[LOGIN-REQUIRED] {site.name}: opening login window")
    report.log(f"[LOGIN-STATE] session will be saved to: {site.state_file}")
    if site.browser_channel:
        report.log(f"[LOGIN-BROWSER] {site.name}: channel={site.browser_channel}")
    if login_uses_persistent_context(site):
        report.log(
            "[LOGIN-BROWSER] "
            f"{site.name}: persistent profile = {login_profile_dir(site)}"
        )

    deadline = monotonic() + timeout_seconds
    with sync_playwright() as p:
        browser = None
        if login_uses_persistent_context(site):
            profile_dir = login_profile_dir(site)
            profile_dir.mkdir(parents=True, exist_ok=True)
            context = p.chromium.launch_persistent_context(
                str(profile_dir),
                **browser_launch_options(site, headless=False),
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(**browser_launch_options(site, headless=False))
            context = browser.new_context()
            page = context.new_page()

        try:
            page.goto(site.login_url, wait_until="domcontentloaded")

            if is_facebook_site(site):
                while monotonic() < deadline:
                    cookie_names = {cookie.get("name") for cookie in context.cookies()}
                    if "c_user" in cookie_names and "xs" in cookie_names:
                        context.storage_state(path=str(site.state_file))
                        report.log(f"[LOGIN-SAVED] {site.name}: {site.state_file}")
                        return
                    page.wait_for_timeout(1000)
            else:
                report.log(
                    "[LOGIN-WAITING] complete login in the browser, then press Enter "
                    "in this terminal to save the session"
                )
                input("Complete login in the browser, then press Enter here to save session...")
                context.storage_state(path=str(site.state_file))
                report.log(f"[LOGIN-SAVED] {site.name}: {site.state_file}")
                return
        finally:
            if browser is not None:
                browser.close()
            else:
                context.close()

    raise TimeoutError(f"timed out waiting for login cookies for {site.name}")
