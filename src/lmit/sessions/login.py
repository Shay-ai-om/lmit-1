from __future__ import annotations

from time import monotonic
from urllib.request import urlopen
import subprocess
from typing import Callable

from lmit.config import SessionSiteConfig
from lmit.reports import ConversionReport
from lmit.sessions.launch import (
    apply_stealth,
    browser_executable_for_site,
    browser_launch_options,
    login_cdp_endpoint,
    login_cdp_port,
    login_profile_dir,
    login_uses_cdp,
    login_uses_persistent_context,
)
from lmit.sessions.strategies.facebook import is_facebook_site

LoginConfirmationCallback = Callable[[SessionSiteConfig, ConversionReport], None]


def capture_session_state(
    site: SessionSiteConfig,
    report: ConversionReport,
    *,
    timeout_seconds: int = 900,
    confirm_login: LoginConfirmationCallback | None = None,
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
    if login_uses_cdp(site):
        report.log(
            "[LOGIN-BROWSER] "
            f"{site.name}: connect_over_cdp = {login_cdp_endpoint(site)}"
        )

    deadline = monotonic() + timeout_seconds
    confirm_login = confirm_login or wait_for_login_confirmation
    with sync_playwright() as p:
        if login_uses_cdp(site):
            _capture_session_state_via_cdp(
                site,
                report,
                deadline=deadline,
                playwright=p,
                confirm_login=confirm_login,
            )
            return

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
            apply_stealth(context)
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
                confirm_login(site, report)
                context.storage_state(path=str(site.state_file))
                report.log(f"[LOGIN-SAVED] {site.name}: {site.state_file}")
                return
        finally:
            if browser is not None:
                browser.close()
            else:
                context.close()

    raise TimeoutError(f"timed out waiting for login cookies for {site.name}")


def _capture_session_state_via_cdp(
    site: SessionSiteConfig,
    report: ConversionReport,
    *,
    deadline: float,
    playwright,
    confirm_login: LoginConfirmationCallback,
) -> None:
    profile_dir = login_profile_dir(site)
    profile_dir.mkdir(parents=True, exist_ok=True)
    executable = browser_executable_for_site(site)
    endpoint = login_cdp_endpoint(site)
    port = login_cdp_port(site)
    process = subprocess.Popen(
        [
            str(executable),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-popup-blocking",
            "--new-window",
            site.login_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    report.log(f"[LOGIN-BROWSER] {site.name}: executable = {executable}")

    browser = None
    try:
        _wait_for_cdp(endpoint, deadline)
        confirm_login(site, report)
        browser = playwright.chromium.connect_over_cdp(endpoint)
        if not browser.contexts:
            raise RuntimeError(f"{site.name}: no browser context found after CDP connect")
        context = browser.contexts[0]
        context.storage_state(path=str(site.state_file))
        report.log(f"[LOGIN-SAVED] {site.name}: {site.state_file}")
    finally:
        if browser is not None:
            browser.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _wait_for_cdp(endpoint: str, deadline: float) -> None:
    while monotonic() < deadline:
        try:
            with urlopen(f"{endpoint}/json/version", timeout=2):
                return
        except Exception:
            pass
    raise TimeoutError(f"timed out waiting for CDP endpoint: {endpoint}")


def wait_for_login_confirmation(site: SessionSiteConfig, report: ConversionReport) -> None:
    report.log(
        "[LOGIN-WAITING] complete login in the browser, then press Enter "
        "in this terminal to save the session"
    )
    input("Complete login in the browser, then press Enter here to save session...")
