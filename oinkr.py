import os
import csv
import io
import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")  # Optional: Specific folder ID to store files

user_logs = {}
csv_file = 'user_logs.csv'
DRIVE_FILE_ID = None  # Will store the Google Drive file ID

if not os.path.exists("photos"):
    os.makedirs("photos")

SCOPES = ['https://www.googleapis.com/auth/drive']  # Using full drive scope for simplicity

def authenticate_drive():
    """Authenticate with Google Drive API."""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
            
    return build('drive', 'v3', credentials=creds)

def find_csv_in_drive():
    """Find if our CSV file already exists in Google Drive."""
    global DRIVE_FILE_ID
    
    service = authenticate_drive()
    
    # Search for the file by name
    query = f"name = '{os.path.basename(csv_file)}' and trashed = false"
    if DRIVE_FOLDER_ID:
        query += f" and '{DRIVE_FOLDER_ID}' in parents"
        
    results = service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name)'
    ).execute()
    
    items = results.get('files', [])
    
    if items:
        DRIVE_FILE_ID = items[0]['id']
        print(f"Found existing file in Drive: {items[0]['name']} (ID: {DRIVE_FILE_ID})")
        return DRIVE_FILE_ID
    else:
        print("File not found in Google Drive")
        return None

def upload_csv_to_drive():
    """Upload the CSV file to Google Drive."""
    global DRIVE_FILE_ID
    
    service = authenticate_drive()
    
    # Check if file already exists
    file_id = find_csv_in_drive()
    
    media = MediaFileUpload(csv_file, mimetype='text/csv')
    
    if file_id:
        # Update existing file
        updated_file = service.files().update(
            fileId=file_id,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        print(f"File updated in Drive: {updated_file.get('name')} ({updated_file.get('webViewLink')})")
    else:
        # Create new file
        file_metadata = {'name': os.path.basename(csv_file)}
        
        if DRIVE_FOLDER_ID:
            file_metadata['parents'] = [DRIVE_FOLDER_ID]
            
        created_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        
        DRIVE_FILE_ID = created_file.get('id')
        print(f"File uploaded to Drive: {created_file.get('name')} (ID: {DRIVE_FILE_ID})")
    
    return DRIVE_FILE_ID

def download_csv_from_drive():
    """Download the latest CSV file from Google Drive."""
    global DRIVE_FILE_ID
    
    if not DRIVE_FILE_ID:
        file_id = find_csv_in_drive()
        if not file_id:
            print("No file found in Drive to download")
            return False
    
    service = authenticate_drive()
    
    try:
        request = service.files().get_media(fileId=DRIVE_FILE_ID)
        file = io.BytesIO()
        downloader = MediaIoBaseDownload(file, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}%")
        
        file.seek(0)
        
        # Write the downloaded content to the local file
        with open(csv_file, 'wb') as f:
            f.write(file.read())
            
        print(f"File downloaded from Drive and saved to {csv_file}")
        return True
        
    except Exception as e:
        print(f"Error downloading file from Drive: {e}")
        return False

def initialize_logs():
    """Initialize the CSV file if it doesn't exist."""
    if not os.path.exists(csv_file):
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['user_id', 'time', 'food', 'calories', 'photo_path'])
        print(f"Created new CSV file: {csv_file}")

def save_to_csv(user_id, time, food='', calories='', photo_path=''):
    """Save a single entry to the CSV file and upload to Drive."""
    with open(csv_file, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([user_id, time, food, calories, photo_path])
    
    # Upload the updated file to Drive
    upload_csv_to_drive()

def load_existing_logs():
    """Load logs from CSV, prioritizing the Google Drive version."""
    global user_logs
    
    # Try to download the latest version from Drive first
    download_success = download_csv_from_drive()
    
    # If download failed and local file doesn't exist, initialize a new file
    if not download_success and not os.path.exists(csv_file):
        initialize_logs()
    
    user_logs.clear()
    
    if os.path.exists(csv_file):
        try:
            with open(csv_file, 'r') as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                for row in reader:
                    if len(row) < 5:
                        continue
                    user_id, time, food, calories, photo_path = row
                    try:
                        user_id = int(user_id)
                    except ValueError:
                        continue
                        
                    if user_id not in user_logs:
                        user_logs[user_id] = []
                        
                    entry = {"time": time}
                    if food:
                        entry["food"] = food
                    if calories:
                        try:
                            entry["calories"] = int(calories)
                        except ValueError:
                            entry["calories"] = 0
                    if photo_path:
                        entry["photo_path"] = photo_path
                        
                    user_logs[user_id].append(entry)
                    
            print(f"Loaded logs for {len(user_logs)} users from CSV")
        except Exception as e:
            print(f"Error loading logs from CSV: {e}")
    else:
        print(f"CSV file {csv_file} not found")

def save_all_logs_to_csv():
    """Save all logs to the CSV file and upload to Google Drive."""
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'time', 'food', 'calories', 'photo_path'])
        
        for user_id, entries in user_logs.items():
            for entry in entries:
                writer.writerow([
                    user_id, 
                    entry['time'], 
                    entry.get('food', ''), 
                    entry.get('calories', ''), 
                    entry.get('photo_path', '')
                ])
    
    # Upload to Google Drive
    upload_csv_to_drive()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey little piggy. I saw that snack! Log it like this:\n"
        "- Text: food, calories (e.g., pizza, 300)\n"
        "- Or send a photo!"
    )

async def log_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Always refresh logs from Drive first
    load_existing_logs()
    
    user_id = update.effective_user.id
    text = update.message.text
    time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    entries = text.strip().split('\n')
    logged_foods = []
    total_calories = 0
    
    for entry_text in entries:
        entry_text = entry_text.strip()
        if not entry_text:
            continue
            
        last_comma_pos = entry_text.rfind(',')
        if last_comma_pos == -1:
            await update.message.reply_text(f"Error with entry: '{entry_text}'\nPlease log like this: food, calories (e.g., pizza, 300)")
            continue
            
        food = entry_text[:last_comma_pos].strip()
        calories_str = entry_text[last_comma_pos + 1:].strip()
        
        try:
            calories = int(calories_str)
        except ValueError:
            await update.message.reply_text(f"Error with calories in entry: '{entry_text}'\nCalories must be a number. Example: apple, 95")
            continue
            
        entry = {"time": time, "food": food, "calories": calories}
        
        if user_id not in user_logs:
            user_logs[user_id] = []
            
        user_logs[user_id].append(entry)
        save_to_csv(user_id, time, food, calories)
        
        logged_foods.append(f"{food} ({calories} kcal)")
        total_calories += calories
    
    if logged_foods:
        response = "Logged:\n" + "\n".join(logged_foods)
        response += f"\n\nTotal: {total_calories} kcal"
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("No valid food entries were found. Please use format: food, calories")

async def log_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Always refresh logs from Drive first
    load_existing_logs()
    
    user_id = update.effective_user.id
    time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    photo_file = await update.message.photo[-1].get_file()
    
    file_path = f"photos/{user_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    await photo_file.download_to_drive(file_path)
    
    entry = {"time": time, "photo_path": file_path}
    
    if user_id not in user_logs:
        user_logs[user_id] = []
        
    user_logs[user_id].append(entry)
    save_to_csv(user_id, time, '', '', file_path)
    
    await update.message.reply_text("Photo logged! 📸")

async def show_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Always refresh logs from Drive first
    load_existing_logs()
    
    user_id = update.effective_user.id
    entries = user_logs.get(user_id, [])
    
    if not entries:
        await update.message.reply_text("Your trough is empty. Start logging.")
    else:
        total_calories = sum(e.get('calories', 0) for e in entries if 'calories' in e)
        log_lines = []
        
        for e in entries:
            if 'food' in e:
                log_lines.append(f"{e['time']} — {e['food']} ({e['calories']} kcal)")
            elif 'photo_path' in e:
                log_lines.append(f"{e['time']} — 📸 Photo logged: {e['photo_path']}")
                
        await update.message.reply_text(f"Here's your oinklog:\n{chr(10).join(log_lines)}\n\nTotal calories: {total_calories} kcal")

async def today_calories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Always refresh logs from Drive first
    load_existing_logs()
    
    user_id = update.effective_user.id
    entries = user_logs.get(user_id, [])
    
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    today_entries = [e for e in entries if e['time'].startswith(today) and 'calories' in e]
    
    total_calories = sum(e['calories'] for e in today_entries)
    
    if today_entries:
        log_lines = [f"{e['time']} — {e['food']} ({e['calories']} kcal)" for e in today_entries]
        await update.message.reply_text(
            f"Today's food log:\n{chr(10).join(log_lines)}\n\nTotal calories today: {total_calories} kcal"
        )
    else:
        await update.message.reply_text("You haven't logged any food today. Get munching! 🐷")

async def edit_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Always refresh logs from Drive first
    load_existing_logs()
    
    user_id = update.effective_user.id
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['user_id', 'time', 'food', 'calories', 'photo_path'])
    
    entries = user_logs.get(user_id, [])
    for entry in entries:
        writer.writerow([
            user_id, 
            entry['time'], 
            entry.get('food', ''), 
            entry.get('calories', ''), 
            entry.get('photo_path', '')
        ])
        
    output.seek(0)
    csv_data = output.getvalue()
    
    await update.message.reply_document(
        document=csv_data.encode(),
        filename="user_log.csv",
        caption="Here is your food log. Please edit and upload the updated version."
    )

async def handle_csv_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Always refresh logs from Drive first
    load_existing_logs()
    
    user_id = update.effective_user.id
    file = update.message.document
    file_path = f"photos/{user_id}_{file.file_id}.csv"
    
    telegram_file = await file.get_file()
    await telegram_file.download_to_drive(file_path)
    
    await update.message.reply_text(f"🔄 CSV file received and being processed... 🔄")
    
    try:
        with open(file_path, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)
            updated_entries = []
            row_count = 0
            
            for row in reader:
                if len(row) < 5:
                    await update.message.reply_text(f"⚠️ Skipping row with insufficient columns: {row}")
                    continue
                    
                user_id_csv, time, food, calories, photo_path = row
                try:
                    user_id_csv = int(user_id_csv)
                except ValueError:
                    await update.message.reply_text(f"⚠️ Invalid user_id in row: {row}")
                    continue
                    
                if user_id_csv == user_id:
                    entry = {"time": time}
                    if food: entry["food"] = food
                    if calories.strip():
                        try:
                            entry["calories"] = int(calories)
                        except ValueError:
                            entry["calories"] = 0
                    if photo_path: entry["photo_path"] = photo_path
                    
                    updated_entries.append(entry)
                    row_count += 1
                else:
                    await update.message.reply_text(f"⚠️ Skipping row with user_id {user_id_csv} (not yours)")
        
        if updated_entries:
            user_logs[user_id] = updated_entries
            save_all_logs_to_csv()
            
            # Make sure to load the updated logs
            load_existing_logs()
            
            
            await update.message.reply_text(
                f"🐷 Oink oink! Your food logs have been updated! 🎉\n\n"
                f"📝 Successfully processed entries\n"
                f"Type /log to see your updated entries! 🥕🍎"
            )
        else:
            await update.message.reply_text("❌ No valid entries found in your CSV. Please check the format and try again.")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error processing your CSV: {e}. Please make sure it's formatted correctly.")
    
    # Clean up the temporary file
    if os.path.exists(file_path):
        os.remove(file_path)

async def drive_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to manually sync with Google Drive."""
    await update.message.reply_text("🔄 Syncing with Google Drive...")
    
    try:
        # Upload current local file to Drive
        upload_csv_to_drive()
        # Download the latest file from Drive
        download_csv_from_drive()
        # Reload logs
        load_existing_logs()
        
        await update.message.reply_text("✅ Sync complete! Your food logs are up to date.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error syncing with Google Drive: {e}")

def main():
    # Initialize or download logs
    initialize_logs()
    find_csv_in_drive()  # Try to find existing file in Drive
    load_existing_logs()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", show_log))
    app.add_handler(CommandHandler("today", today_calories))
    app.add_handler(CommandHandler("edit_log", edit_log))
    app.add_handler(CommandHandler("sync", drive_sync))  # New command to manually sync
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, log_food))
    app.add_handler(MessageHandler(filters.PHOTO, log_photo))
    app.add_handler(MessageHandler(filters.Document.MimeType("text/csv"), handle_csv_upload))
    
    print("Starting bot...")
    app.run_polling()

if __name__ == "__main__":
    main()
