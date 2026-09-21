import os
import re
import gspread
import pdfplumber
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

# CLASSREACH & SHEETS CONFIG
CLASSREACH_USER = os.getenv("CLASSREACH_USER", "bostic_lisa@yahoo.com")
CLASSREACH_PASS = os.getenv("CLASSREACH_PASS", "Donnie53!")
GOOGLE_SHEETS_JSON = os.getenv("GOOGLE_SHEETS_JSON")

# 1. SCRAPE LATEST AGENDA PDF FROM CLASSREACH
def download_latest_agenda():
    print("Connecting to Carolina Hybrid ClassReach portal...")
    with sync_playwright() as p:
        # Launch Chromium with anti-bot detection evasions built-in
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-gpu"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York"
        )
        page = context.new_page()
        
        # Mask automation flags from JavaScript window/navigator
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.navigator.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        """)
        
        page.goto("https://carolinahybrid.classreach.com/Login", wait_until="networkidle")
        print("Waiting for Cloudflare verification...")
        page.wait_for_timeout(5000)

        print("Filling credentials...")
        page.fill('input[type="text"], input[type="email"], input[name*="user" i]', CLASSREACH_USER)
        page.fill('input[type="password"]', CLASSREACH_PASS)
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


# 2. PARSE PDF AGENDA DATA
def parse_agenda_pdf(pdf_path):
    print(f"Parsing PDF agenda: {pdf_path}")
    extracted_tasks = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if not text:
                continue
            
            lines = text.split("\n")
            current_subject = "General"
            
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                
                if any(subj in line_str.upper() for subj in ["MATH", "SCIENCE", "HISTORY", "ENGLISH", "BIBLE", "READING"]):
                    current_subject = line_str
                else:
                    extracted_tasks.append({
                        "Subject": current_subject,
                        "Task": line_str,
                        "Page": page_num
                    })
                    
    print(f"Successfully extracted {len(extracted_tasks)} agenda items.")
    return extracted_tasks


# 3. UPDATE GOOGLE SHEETS DASHBOARD
def update_google_sheets(tasks):
    if not GOOGLE_SHEETS_JSON:
        print("Warning: GOOGLE_SHEETS_JSON environment variable not set. Skipping Sheets update.")
        return
        
    print("Connecting to Google Sheets...")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    with open("credentials.json", "w") as f:
        f.write(GOOGLE_SHEETS_JSON)
        
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    
    sheet = client.open("Homeschool Dashboard").sheet1
    sheet.clear()
    headers = ["Subject", "Task Description", "Page Reference"]
    sheet.append_row(headers)
    
    rows_to_append = [[task["Subject"], task["Task"], task["Page"]] for task in tasks]
    if rows_to_append:
        sheet.append_rows(rows_to_append)
        
    print("Google Sheets dashboard updated successfully!")
    
    if os.path.exists("credentials.json"):
        os.remove("credentials.json")


# MAIN EXECUTION FLOW
if __name__ == "__main__":
    pdf_file = download_latest_agenda()
    parsed_tasks = parse_agenda_pdf(pdf_file)
    update_google_sheets(parsed_tasks)
