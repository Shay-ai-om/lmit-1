from __future__ import annotations

from pathlib import Path
import argparse
import sys
import time

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", default="sessions/facebook_state.json")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    state_file = Path(args.state_file).resolve()
    state_file.parent.mkdir(parents=True, exist_ok=True)

    print("Opening Facebook login page...")
    print(f"Session state will be saved to: {state_file}")
    print("After you finish logging in, this script will save the session automatically.")

    deadline = time.monotonic() + args.timeout_seconds
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")

        while time.monotonic() < deadline:
            cookies = context.cookies()
            cookie_names = {cookie.get("name") for cookie in cookies}
            current_url = page.url
            if "c_user" in cookie_names and "xs" in cookie_names:
                context.storage_state(path=str(state_file))
                print(f"Facebook session saved: {state_file}")
                browser.close()
                return 0

            if "login" not in current_url.lower() and "facebook.com" in current_url.lower():
                # Some Facebook flows set cookies shortly after navigation completes.
                page.wait_for_timeout(3000)
            else:
                page.wait_for_timeout(1000)

        browser.close()

    print("Timed out before Facebook login cookies were detected.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
