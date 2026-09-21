import os
import sys
import re
import gspread
import pdfplumber
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

# Force Python to print logs immediately without buffering
sys.stdout.reconfigure(line_buffering=True)

# CLASSREACH & SHEETS CONFIG
CLASSREACH_USER = os.getenv("CLASSREACH_USER", "bostic_lisa@yahoo.com")
CLASSREACH_PASS = os.getenv("CLASSREACH_PASS", "Donnie53!")
GOOGLE_SHEETS_JSON = os.getenv("GCP_SERVICE_ACCOUNT_KEY") or os.getenv("GOOGLE_SHEETS_JSON")

# 1. SCRAPE LATEST AGENDA PDF FROM CLASSREACH
def download_latest_agenda():
    print("Connecting to Carolina Hybrid ClassReach portal via Firefox...", flush=True)
    with sync_playwright() as p:
        # Launch Firefox which bypasses Cloudflare Chromium signatures
        browser = p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "dom.webdriver.enabled": False,
                "useAutomationExtension": False,
            }
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/New_York"
        )
        page = context.new_page()
        
        # Navigate to login page
        print("Navigating to portal...", flush=True)
        page.goto("https://carolinahybrid.classreach.com/Login", wait_until="domcontentloaded")
        
        # Allow Cloudflare challenge to evaluate and resolve
        print("Waiting for Cloudflare verification to complete...", flush=True)
        page.wait_for_timeout(7000)

        # Locate inputs after Cloudflare bypasses
        print("Locating credential fields...", flush=True)
        email_selector = 'input[type="text"], input[type="email"], input[name*="user" i], #Username'
        page.wait_for_selector(email_selector, timeout=30000)
        
        print("Filling credentials...", flush=True)
        page.fill(email_selector, CLASSREACH_USER)
        page.fill('input[type="password"]', CLASSREACH_PASS)
        page.wait_for_timeout(1000)
        
        print("Clicking Login button...", flush=True)
        page.click('button:has-text("Login"), input[value="Login"], .btn:has-text("Login")')
        
        # Wait for authentication redirect
        page.wait_for_timeout(6000)
        print(f"Post-login URL: {page.url}", flush=True)

        if "login" in page.url.lower():
            body_text = page.locator('body').inner_text()
            print("Login page response snippet:", body_text[:300].replace('\n', ' '), flush=True)
            raise Exception("Authentication failed - stayed on login page.")

        print("Waiting for ClassReach dashboard...", flush=True)
        download_btn = page.locator('text="Download Weekly Items"')
        download_btn.wait_for(state="visible", timeout=30000)
        
        print("Clicking 'Download Weekly Items' button...", flush=True)
        with page.expect_download() as download_info:
            download_btn.click()
        
        download = download_info.value
        pdf_path = "latest_agenda.pdf"
        download.save_as(pdf_path)
        browser.close()
        print("ClassReach PDF successfully downloaded.", flush=True)
        return pdf_path


# 2. PARSE PDF AGENDA DATA
def parse_agenda_pdf(pdf_path):
    print(f"Parsing PDF agenda: {pdf_path}", flush=True)
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
                    
    print(f"Successfully extracted {len(extracted_tasks)} agenda items.", flush=True)
    return extracted_tasks


# 3. UPDATE GOOGLE SHEETS DASHBOARD
def update_google_sheets(tasks):
    if not GOOGLE_SHEETS_JSON:
        print("Warning: Neither GCP_SERVICE_ACCOUNT_KEY nor GOOGLE_SHEETS_JSON set. Skipping Sheets update.", flush=True)
        return
        
    print("Connecting to Google Sheets...", flush=True)
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
        
    print("Google Sheets dashboard updated successfully!", flush=True)
    
    if os.path.exists("credentials.json"):
        os.remove("credentials.json")


# MAIN EXECUTION FLOW
if __name__ == "__main__":
    pdf_file = download_latest_agenda()
    parsed_tasks = parse_agenda_pdf(pdf_file)
    update_google_sheets(parsed_tasks)
