import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os


# Google Sheet ID
SHEET_ID = "1LMpoNHFbtzXvJnfUUwCvSyjKw9PDEkrHtMsSz71NwSA"

# Scopes for accessing Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Path to your service account credentials file
SERVICE_ACCOUNT_FILE = 'oink-svc-acc-credentials.json'


# Globals
sheet = None
client = None

def initialize_sheet():
    """Initialize the Google Sheets connection."""
    global client, sheet
    try:
        # Setup credentials and client
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        client = gspread.authorize(creds)
        
        # Open the sheet by ID
        spreadsheet = client.open_by_key(SHEET_ID)
        sheet = spreadsheet.sheet1  # Use first worksheet
        
        print("Successfully connected to Google Sheets!")
        return True
    except Exception as e:
        print(f"Error initializing Google Sheets: {e}")
        return False

def append_log(user_id: int, food: str, calories: int, timestamp: str, photo_path: str = None) -> bool:
    """Append a new food log row to the Google Sheet."""
    global sheet
    
    # Initialize if not already done
    if sheet is None:
        if not initialize_sheet():
            return False
    
    print(f"Attempting to log: {user_id}, {timestamp}, {food}, {calories}, photo: {photo_path}")
    try:
        # Include photo path if provided, otherwise empty string
        row = [str(user_id), timestamp, food, str(calories), photo_path or ""]
        sheet.append_row(row)
        print("Successfully appended row to Google Sheet!")
        return True
    except Exception as e:
        print(f"Error appending to Google Sheet: {e}")
        # Try to reinitialize the sheet connection
        if initialize_sheet():
            try:
                row = [str(user_id), timestamp, food, str(calories), photo_path or ""]
                sheet.append_row(row)
                print("Successfully appended row after reconnection!")
                return True
            except Exception as e2:
                print(f"Error appending after reconnection: {e2}")
        return False

def get_today_logs(user_id: int, today_date: str):
    """Retrieve today's logs for a user from the Google Sheet."""
    global sheet
    
    # Initialize if not already done
    if sheet is None:
        if not initialize_sheet():
            return []
    
    try:
        # Get all data rows (skip header if exists)
        rows = sheet.get_all_records()
        print(f"Retrieved {len(rows)} rows from Google Sheet")
        
        # Filter by user_id and today's date
        user_logs = []
        for row in rows:
            try:
                # Handle case where user_id might be stored as string
                row_user_id = int(row.get('user_id', 0))
                timestamp = row.get('timestamp', '')
                
                # Check if this log is for the right user and from today
                if row_user_id == user_id and timestamp.startswith(today_date):
                    log_entry = {
                        "timestamp": timestamp,
                        "food": row.get('food', ''),
                        "calories": int(row.get('calories', 0))
                    }
                    
                    # Add photo path if it exists
                    photo_path = row.get('photo_path', '')
                    if photo_path:
                        log_entry['photo_path'] = photo_path
                    
                    user_logs.append(log_entry)
            except (ValueError, KeyError) as e:
                print(f"Error processing row: {row}, Error: {e}")
                continue
        
        print(f"Found {len(user_logs)} logs for user {user_id} today")
        return user_logs
    except Exception as e:
        print(f"Error reading today's logs from Google Sheet: {e}")
        return []

def get_logs(user_id: int):
    """Retrieve all logs for a user from the Google Sheet."""
    global sheet
    
    # Initialize if not already done
    if sheet is None:
        if not initialize_sheet():
            return []
    
    try:
        # Get all data rows (skip header if exists)
        rows = sheet.get_all_records()
        print(f"Retrieved {len(rows)} rows from Google Sheet")
        
        # Filter by user_id (handling both string and int comparisons)
        user_logs = []
        for row in rows:
            try:
                # Handle case where user_id might be stored as string
                row_user_id = int(row.get('user_id', 0))
                if row_user_id == user_id:
                    log_entry = {
                        "timestamp": row.get('timestamp', ''),
                        "food": row.get('food', ''),
                        "calories": int(row.get('calories', 0))
                    }
                    
                    # Add photo path if it exists
                    photo_path = row.get('photo_path', '')
                    if photo_path:
                        log_entry['photo_path'] = photo_path
                    
                    user_logs.append(log_entry)
            except (ValueError, KeyError) as e:
                print(f"Error processing row: {row}, Error: {e}")
                continue
        
        print(f"Found {len(user_logs)} logs for user {user_id}")
        return user_logs
    except Exception as e:
        print(f"Error reading logs from Google Sheet: {e}")
        return []

# Don't initialize automatically - let functions handle it when needed

print("✅ storage.py loaded")
print("Available symbols in storage.py:", dir())