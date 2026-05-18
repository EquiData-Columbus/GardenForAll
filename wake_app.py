import os
import time
from playwright.sync_api import sync_playwright

URL = "https://testapppy-mrzkqdn6kzmjfmsg7a2wv9.streamlit.app/"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    # ── Navigate ───────────────────────────────────────────────────────────────
    print(f"Navigating to {URL} ...")
    page.goto(URL, timeout=60000)
    time.sleep(5)

    # ── Screenshot 1: what does the page look like on arrival? ─────────────────
    page.screenshot(path="screenshot_1_on_arrival.png", full_page=True)
    print("Screenshot 1 saved.")

    # ── Print all visible text so we can read the page in the logs ─────────────
    print("=== PAGE TEXT ===")
    print(page.inner_text("body"))
    print("=================")

    # ── Print all buttons on the page ──────────────────────────────────────────
    buttons = page.get_by_role("button").all()
    print(f"Found {len(buttons)} button(s) on page:")
    for i, btn in enumerate(buttons):
        try:
            print(f"  [{i}] '{btn.inner_text()}' | visible={btn.is_visible()}")
        except Exception as e:
            print(f"  [{i}] could not read button: {e}")

    # ── Try clicking any button that mentions waking/restarting ────────────────
    wake_phrases = [
        "Yes, get this app back up!",
        "Get this app back up",
        "Wake up",
        "Restart",
        "Resume",
    ]

    clicked = False
    for phrase in wake_phrases:
        try:
            btn = page.get_by_role("button", name=phrase)
            if btn.is_visible():
                print(f"Found wake button: '{phrase}' — clicking...")
                btn.click()
                clicked = True
                break
        except Exception:
            pass

    # ── Fallback: try clicking ANY visible button ───────────────────────────────
    if not clicked:
        print("No known wake button found. Trying to click the first visible button...")
        for i, btn in enumerate(buttons):
            try:
                if btn.is_visible():
                    print(f"Clicking button [{i}]: '{btn.inner_text()}'")
                    btn.click()
                    clicked = True
                    break
            except Exception as e:
                print(f"Could not click button [{i}]: {e}")

    # ── Screenshot 2: what does the page look like after the click? ─────────────
    time.sleep(5)
    page.screenshot(path="screenshot_2_after_click.png", full_page=True)
    print("Screenshot 2 saved.")

    if clicked:
        print("Waiting for app to finish booting...")
        try:
            page.wait_for_load_state("networkidle", timeout=120000)
            print("App is awake!")
        except Exception as e:
            print(f"Timed out waiting for app to load: {e}")
    else:
        print("WARNING: No button was clicked. See screenshots for what the page looks like.")

    browser.close()
