import os
import time
from playwright.sync_api import sync_playwright

URL = "https://testapppy-mrzkqdn6kzmjfmsg7a2wv9.streamlit.app/"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    print(f"Navigating to {URL} ...")
    page.goto(URL, timeout=60000)

    # Give the splash screen time to load
    time.sleep(5)

    # Streamlit's wake button label
    wake_button = page.get_by_role("button", name="Yes, get this app back up!")

    if wake_button.is_visible():
        print("App is sleeping — clicking wake button...")
        wake_button.click()
        # Wait for the app to actually boot up
        page.wait_for_load_state("networkidle", timeout=120000)
        print("App is awake!")
    else:
        print("App is already running — nothing to do.")

    browser.close()
