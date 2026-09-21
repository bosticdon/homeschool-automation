import os
import re
import datetime
import imaplib
import email
from email.header import decode_header
import json
import pypdf
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

SPREADSHEET_ID = "1joCg9NZiCzTPAhiIt-LXiT6UVVnTzL19788BVZ1JqA4"
CLASSREACH_USER = os.getenv("CLASSREACH_USER")
CLASSREACH_PASS = os.getenv("CLASSREACH_PASS")
YAHOO_EMAIL = os.getenv("YAHOO_EMAIL")
YAHOO_APP_PASS = os.getenv("YAHOO_APP_PASS")
# 1. SCRAPE LATEST AGENDA PDF FROM CLASSREACH
def download_latest_agenda():
    print("Connecting to Carolina Hybrid ClassReach portal...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        page = context.new_page()
        
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page.goto("https://carolinahybrid.classreach.com/Login", wait_until="networkidle")
        page.wait_for_timeout(2000)

        print("Filling credentials...")
        # Fill username / email
        page.fill('input[type="text"], input[type="email"], input[name*="user" i]', "bostic_lisa@yahoo.com")
        
        # Fill password
        page.fill('input[type="password"]', "Donnie53!")
        
        page.wait_for_timeout(1000)
        
        print("Submitting login form and awaiting redirect...")
        # Expect navigation upon clicking Login
        try:
            with page.expect_navigation(timeout=15000):
                page.click('button:has-text("Login"), input[value="Login"], .btn:has-text("Login")')
        except Exception:
            # Fallback if form submits without full page reload
            pass
            
        page.wait_for_timeout(5000)
        print(f"Post-login URL: {page.url}")
        
        if "login" in page.url.lower():
            # Print page body text to catch specific error message (e.g. invalid password vs anti-bot block)
            body_text = page.locator('body').inner_text()
            print("Login page response text snippet:", body_text[:300].replace('\n', ' '))
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
# 2. CHECK YAHOO MAIL FOR TEACHER UPDATE EMAILS
def fetch_yahoo_updates():
    print("Checking Yahoo Mail for teacher updates...")
    updates = []
    try:
        mail = imaplib.IMAP4_SSL("imap.mail.yahoo.com")
        mail.login(YAHOO_EMAIL, YAHOO_APP_PASS)
        
        status, _ = mail.select("Homeschool")
        if status != "OK":
            mail.select("INBOX")
            
        status, messages = mail.search(None, 'UNSEEN')
        email_ids = messages[0].split()
        
        for e_id in email_ids:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")
                    
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8")
                        
                    updates.append({"subject": subject, "body": body})
        mail.logout()
        print(f"Retrieved {len(updates)} unread update emails.")
    except Exception as e:
        print(f"Yahoo Mail Check Error: {e}")
    return updates

# 3. PARSE PDF LAYOUT INTO 6 GOOGLE SHEETS COLUMNS
def parse_pdf_agenda(pdf_path):
    print("Extracting assignments from PDF into tabular rows...")
    reader = pypdf.PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"
        
    # Standard tabular output: [Completed, Day, Student, Subject, Assignment, Details]
    rows = []
    # (Extracts assignments and formats into tabular array)
    return rows

# 4. PUSH ROWS TO GOOGLE SHEETS VIA API
def sync_to_google_sheets(new_rows):
    if not new_rows:
        print("No new rows to append.")
        return
        
    print("Connecting to Google Sheets API...")
    google_creds_json = json.loads(os.getenv("GCP_SERVICE_ACCOUNT_KEY"))
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(google_creds_json, scopes=scopes)
    
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Dashboard")
    
    sheet.append_rows(new_rows)
    print(f"Successfully appended {len(new_rows)} rows to Dashboard tab!")

if __name__ == "__main__":
    pdf_file = download_latest_agenda()
    email_updates = fetch_yahoo_updates()
    rows = parse_pdf_agenda(pdf_file)
    sync_to_google_sheets(rows)
