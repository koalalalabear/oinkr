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
from googleapiclient.http import MediaFileUpload

load_dotenv()


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


user_logs = {}

if not os.path.exists("photos"):
    os.makedirs("photos")

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def authenticate_drive():
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

def upload_file_to_drive(file_path, mime_type='text/csv'):
    service = authenticate_drive()
    file_metadata = {'name': os.path.basename(file_path)}
    media = MediaFileUpload(file_path, mimetype=mime_type)
    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name, webViewLink'
    ).execute()
    print(f"File uploaded: {uploaded_file.get('name')} ({uploaded_file.get('webViewLink')})")
    return uploaded_file

# test_upload.py
from drive_uploader import upload_file_to_drive

upload_file_to_drive('your_log.csv')

csv_file = 'user_logs.csv'
if not os.path.exists(csv_file):
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'time', 'food', 'calories', 'photo_path'])

def save_to_csv(user_id, time, food='', calories='', photo_path=''):
    with open(csv_file, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([user_id, time, food, calories, photo_path])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey little piggy. I saw that snack! Log it like this:\n"
        "- Text: food, calories (e.g., pizza, 300)\n"
        "- Or send a photo!"
    )

async def log_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    user_id = update.effective_user.id
    load_existing_logs()
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
    user_id = update.effective_user.id
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['user_id', 'time', 'food', 'calories', 'photo_path'])
    entries = user_logs.get(user_id, [])
    for entry in entries:
        writer.writerow([user_id, entry['time'], entry.get('food', ''), entry.get('calories', ''), entry.get('photo_path', '')])
    output.seek(0)
    csv_data = output.getvalue()

    await update.message.reply_document(
        document=csv_data.encode(),
        filename="user_log.csv",
        caption="Here is your food log. Please edit and upload the updated version."
    )

async def handle_csv_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            load_existing_logs()  # <- Ensures logs are in sync
            total_calories = sum(entry.get("calories", 0) for entry in updated_entries if "calories" in entry)
            await update.message.reply_text(
                f"🎉 Oink oink! Your food logs have been updated! 🎉\n\n"
                f"📝 Successfully processed {row_count} entries\n"
                f"🔢 Total calories in your log: {total_calories} kcal\n\n"
                f"🐷 Type /log to see your updated entries! 🥕🍎"
            )
        else:
            await update.message.reply_text("❌ No valid entries found in your CSV. Please check the format and try again.")

    except Exception as e:
        await update.message.reply_text(f"❌ Error processing your CSV: {e}. Please make sure it's formatted correctly.")

def save_all_logs_to_csv():
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'time', 'food', 'calories', 'photo_path'])
        for user_id, entries in user_logs.items():
            for entry in entries:
                writer.writerow([user_id, entry['time'], entry.get('food', ''), entry.get('calories', ''), entry.get('photo_path', '')])

def load_existing_logs():
    user_logs.clear()
    if os.path.exists(csv_file):
        try:
            with open(csv_file, 'r') as f:
                reader = csv.reader(f)
                next(reader)
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

load_existing_logs()

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("log", show_log))
app.add_handler(CommandHandler("today", today_calories))
app.add_handler(CommandHandler("edit_log", edit_log))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, log_food))
app.add_handler(MessageHandler(filters.PHOTO, log_photo))
app.add_handler(MessageHandler(filters.Document.MimeType("text/csv"), handle_csv_upload))

app.run_polling()
