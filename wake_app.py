import os
import time
from playwright.sync_api import sync_playwright

URL = "https://thegardenforall-heatmap.streamlit.app/"

WAKE_PHRASES = [
    "Yes, get this app back up!",
    "Get this app back up",
    "Wake up",
    "Restart",
    "Resume",
]

MAX_WAIT_SECONDS = 60   # how long to keep trying before giving up
POLL_INTERVAL    = 3    # seconds between each attempt


def find_wake_button(page):
    """Return the first visible wake button, or None if not found."""
    for phrase in WAKE_PHRASES:
        try:
            btn = page.get_by_role("button", name=phrase)
            if btn.is_visible():
                return btn, phrase
        except Exception:
            pass
    return None, None


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    print(f"Navigating to {URL} ...")
    page.goto(URL, timeout=60000)

    # ── Retry loop: poll for the wake button instead of a blind sleep ──────────
    print(f"Waiting up to {MAX_WAIT_SECONDS}s for the wake button to appear...")
    deadline = time.time() + MAX_WAIT_SECONDS
    btn, phrase = None, None

    while time.time() < deadline:
        btn, phrase = find_wake_button(page)
        if btn:
            break
        print(f"  Button not visible yet — retrying in {POLL_INTERVAL}s ...")
        time.sleep(POLL_INTERVAL)

    # ── Act on what we found ───────────────────────────────────────────────────
    if btn:
        print(f"Found wake button: '{phrase}' — clicking...")
        btn.click()

        print("Waiting for app to finish booting (up to 2 min)...")
        try:
            page.wait_for_load_state("networkidle", timeout=120000)
            print("App is awake!")
        except Exception as e:
            print(f"Timed out waiting for full load (app may still be booting): {e}")
    else:
        # App was already running — no splash screen appeared
        print("No wake button found — app is likely already running.")

    browser.close()
