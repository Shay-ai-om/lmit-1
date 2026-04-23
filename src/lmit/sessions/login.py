from __future__ import annotations

from time import monotonic

from lmit.config import SessionSiteConfig
from lmit.reports import ConversionReport
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

    deadline = monotonic() + timeout_seconds
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(site.login_url, wait_until="domcontentloaded")

        if is_facebook_site(site):
            while monotonic() < deadline:
                cookie_names = {cookie.get("name") for cookie in context.cookies()}
                if "c_user" in cookie_names and "xs" in cookie_names:
                    context.storage_state(path=str(site.state_file))
                    browser.close()
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
            browser.close()
            report.log(f"[LOGIN-SAVED] {site.name}: {site.state_file}")
            return

        browser.close()

    raise TimeoutError(f"timed out waiting for login cookies for {site.name}")
