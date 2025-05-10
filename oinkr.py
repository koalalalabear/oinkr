import os
import csv
import io
import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# In-memory log for tracking food entries
user_logs = {}


# Ensure the 'photos' directory exists
if not os.path.exists("photos"):
    os.makedirs("photos")

# Ensure the CSV file exists with headers
csv_file = 'user_logs.csv'
if not os.path.exists(csv_file):
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'time', 'food', 'calories', 'photo_path'])

# Function to save a row to the CSV file
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

    parts = [part.strip() for part in text.split(",")]
    if len(parts) < 2:
        await update.message.reply_text("Please log like this: food, calories (e.g., pizza, 300)")
        return

    food = parts[0]
    try:
        calories = int(parts[1])
    except ValueError:
        await update.message.reply_text("Calories must be a number. Example: apple, 95")
        return

    entry = {
        "time": time,
        "food": food,
        "calories": calories
    }

    if user_id not in user_logs:
        user_logs[user_id] = []
    user_logs[user_id].append(entry)

    # Save to CSV after each log
    save_to_csv(user_id, time, food, calories)

    await update.message.reply_text(f"Logged: {food} ({calories} kcal)")

async def log_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    photo_file = await update.message.photo[-1].get_file()
    file_path = f"photos/{user_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    await photo_file.download_to_drive(file_path)

    entry = {
        "time": time,
        "photo_path": file_path
    }

    if user_id not in user_logs:
        user_logs[user_id] = []
    user_logs[user_id].append(entry)

    # Save to CSV after each photo log
    save_to_csv(user_id, time, '', '', file_path)

    await update.message.reply_text("Photo logged! 📸")

async def show_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entries = user_logs.get(user_id, [])
    if not entries:
        await update.message.reply_text("Your trough is empty. Start logging.")
    else:
        total_calories = sum(e['calories'] for e in entries if 'calories' in e)
        log_lines = []
        for e in entries:
            if 'food' in e:
                log_lines.append(f"{e['time']} — {e['food']} ({e['calories']} kcal)")
            elif 'photo_path' in e:
                log_lines.append(f"{e['time']} — 📸 Photo logged: {e['photo_path']}")

        log_text = "\n".join(log_lines)
        await update.message.reply_text(f"Here’s your oinklog:\n{log_text}\n\nTotal calories: {total_calories} kcal")

async def today_calories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entries = user_logs.get(user_id, [])
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    today_entries = [e for e in entries if e['time'].startswith(today) and 'calories' in e]
    total_calories = sum(e['calories'] for e in today_entries)

    if today_entries:
        log_lines = [f"{e['time']} — {e['food']} ({e['calories']} kcal)" for e in today_entries]
        log_text = "\n".join(log_lines)
        await update.message.reply_text(
            f"Today’s food log:\n{log_text}\n\nTotal calories today: {total_calories} kcal"
        )
    else:
        await update.message.reply_text("You haven’t logged any food today. Get munching! 🐷")

async def edit_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Generate CSV in memory for the user
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['user_id', 'time', 'food', 'calories', 'photo_path'])  # CSV header

    # Write user logs to the CSV
    entries = user_logs.get(user_id, [])
    for entry in entries:
        row = [user_id, entry['time'], entry.get('food', ''), entry.get('calories', ''), entry.get('photo_path', '')]
        writer.writerow(row)

    # Get the CSV contents as string
    output.seek(0)
    csv_data = output.getvalue()

    # Send the CSV file to the user
    await update.message.reply_document(
        document=csv_data.encode(),  # Send as bytes
        filename="user_log.csv",
        caption="Here is your food log. Please edit and upload the updated version."
    )

async def handle_csv_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Check if the message contains a document (i.e., uploaded CSV)
    if update.message.document and update.message.document.mime_type == 'text/csv':
        file = await update.message.document.get_file()
        file_path = f'photos/{user_id}_uploaded_log.csv'  # Save the uploaded file temporarily
        await file.download_to_drive(file_path)

        # Read the uploaded CSV and update the user logs
        with open(file_path, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            updated_entries = []

            for row in reader:
                try:
                    user_id_csv, time, food, calories, photo_path = row
                    user_id_csv = int(user_id_csv)

                    # Ensure this belongs to the user
                    if user_id_csv == user_id:
                        entry = {"time": time}
                        if food: entry["food"] = food
                        if calories: entry["calories"] = int(calories)
                        if photo_path: entry["photo_path"] = photo_path
                        updated_entries.append(entry)

                except ValueError as e:
                    await update.message.reply_text(f"Error processing your CSV: {e}. Please make sure it's formatted correctly.")
                    return

        # Update the in-memory log with the new entries
        user_logs[user_id] = updated_entries
        save_all_logs_to_csv()  # Save updated logs to CSV file

        # Confirm to the user that their logs have been updated
        await update.message.reply_text("Your logs have been successfully updated!")

# Helper function to save the updated logs back to CSV
def save_all_logs_to_csv():
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'time', 'food', 'calories', 'photo_path'])
        for user_id, entries in user_logs.items():
            for entry in entries:
                writer.writerow([user_id, entry['time'], entry.get('food', ''), entry.get('calories', ''), entry.get('photo_path', '')])


app = ApplicationBuilder().token(BOT_TOKEN).build()

# Handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("log", show_log))
app.add_handler(CommandHandler("today", today_calories))
app.add_handler(CommandHandler("edit_log", edit_log))  # Command to edit logs
app.add_handler(MessageHandler(filters.DOCUMENT.mime_type('text/csv'), handle_csv_upload))  # Handle uploaded CSV
app.add_handler(MessageHandler(filters.PHOTO, log_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, log_food))

# Start the bot

def load_existing_logs():
    if os.path.exists(csv_file):
        with open(csv_file, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                user_id, time, food, calories, photo_path = row
                user_id = int(user_id)  # CSV stores user_id as string
                if user_id not in user_logs:
                    user_logs[user_id] = []
                entry = {"time": time}
                if food:  # Food log
                    entry.update({"food": food, "calories": int(calories)})
                if photo_path:  # Photo log
                    entry.update({"photo_path": photo_path})
                user_logs[user_id].append(entry)


load_existing_logs()  # Populate user_logs from CSV
app.run_polling()