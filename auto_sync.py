import os
import re
import gspread
import pdfplumber
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# CLASSREACH & SHEETS CONFIG
CLASSREACH_USER = os.getenv("CLASSREACH_USER", "bostic_lisa@yahoo.com")
CLASSREACH_PASS = os.getenv("CLASSREACH_PASS", "Donnie53!")
GOOGLE_SHEETS_JSON = os.getenv("GOOGLE_SHEETS_JSON")

# 1. SCRAPE LATEST AGENDA PDF FROM CLASSREACH
def download_latest_agenda():
    print("Connecting to Carolina Hybrid ClassReach portal via Stealth Firefox...")
    with sync_playwright() as p:
        # Launch Firefox with stealth configuration
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0"
        )
        page = context.new_page()
        
        # Apply stealth patches to bypass Cloudflare detection
        stealth_sync(page)
        
        page.goto("https://carolinahybrid.classreach.com/Login", wait_until="networkidle")
        print("Waiting for Cloudflare verification to complete...")
        page.wait_for_timeout(5000)

        print("Filling credentials...")
        page.fill('input[type="text"], input[type="email"], input[name*="user" i]', "bostic_lisa@yahoo.com")
        page.fill('input[type="password"]', "Donnie53!")
        page.wait_for_timeout(1000)
        
        print("Clicking Login button...")
        page.click('button:has-text("Login"), input[value="Login"], .btn:has-text("Login")')
        page.wait_for_timeout(6000)
        print(f"Post-login URL: {page.url}")

        if "login" in page.url.lower():
            body_text = page.locator('body').inner_text()
            print("Login page response snippet:", body_text[:300].replace('\n', ' '))
            raise Exception("Authentication failed - stayed on login page.")

        print("Waiting for ClassReach dashboard...")
        download_btn = page.locator('text="Download Weekly Items"')
        download_btn.wait_for(state="visible", timeout=30000)
        
        print("Clicking 'Download Weekly Items' button...")
        with page.expect_download() as download_info:
            download_btn.click()
        
        download = download_info.value
        pdf_path = "latest_agenda.pdf"
        download.save_as(pdf_path)
        browser.close()
        print("ClassReach PDF successfully downloaded.")
        return pdf_path

if __name__ == "__main__":
    pdf_file = download_latest_agenda()
