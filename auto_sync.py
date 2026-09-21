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
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()
        
        # Navigate directly to Carolina Hybrid login page
        page.goto("https://carolinahybrid.classreach.com/login", wait_until="domcontentloaded")
        
        # Fill email and password
        email_selector = 'input[type="email"], input[name="email"], input[name="username"], input[placeholder*="Email"]'
        page.wait_for_selector(email_selector, timeout=20000)
        page.fill(email_selector, CLASSREACH_USER)
        
        pass_selector = 'input[type="password"], input[name="password"]'
        page.fill(pass_selector, CLASSREACH_PASS)
        
        # Click login button
        page.click('button[type="submit"], input[type="submit"], button:has-text("Log In")')
        
        # Wait for home dashboard to render
        print("Waiting for ClassReach dashboard...")
        page.wait_for_selector('text=Download Weekly Items', timeout=25000)
        
        # Click the "Download Weekly Items" button directly under WEEKLY AGENDA
        print("Clicking 'Download Weekly Items' button...")
        with page.expect_download() as download_info:
            page.click('text=Download Weekly Items')
        
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
