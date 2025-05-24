from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import os
import storage
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

app = FastAPI()
telegram_app = None  # Global reference to the Telegram Application


# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐷 Hey little piggy! Start logging your food.\n\n"
        "📝 For text: Send 'food, calories' (e.g., apple, 95)\n"
        "📸 For photos: Send a photo with 'food, calories' as caption"
    )

async def log_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if ',' not in text:
        await update.message.reply_text("Please log food like: food, calories (e.g., apple, 95)")
        return

    food, calories_str = map(str.strip, text.rsplit(',', 1))
    try:
        calories = int(calories_str)
    except ValueError:
        await update.message.reply_text("Calories must be a number. Try again!")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    success = storage.append_log(user_id, food, calories, timestamp)

    if success:
        await update.message.reply_text(f"✅ Logged: {food} ({calories} kcal)")
    else:
        await update.message.reply_text("❌ Oops, something went wrong saving your log. Try again later.")

async def log_food_with_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    caption = update.message.caption

    if not caption:
        await update.message.reply_text("📸 Please add a caption with: food, calories (e.g., apple, 95)")
        return

    caption = caption.strip()

    if ',' not in caption:
        await update.message.reply_text("📸 Caption should be: food, calories (e.g., apple, 95)")
        return

    food, calories_str = map(str.strip, caption.rsplit(',', 1))
    try:
        calories = int(calories_str)
    except ValueError:
        await update.message.reply_text("📸 Calories in caption must be a number. Try again!")
        return

    photo_file = await update.message.photo[-1].get_file()

    photos_dir = "food_photos"
    os.makedirs(photos_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    photo_filename = f"{user_id}_{timestamp}_{food.replace(' ', '_').replace(',', '')}.jpg"
    photo_path = os.path.join(photos_dir, photo_filename)

    try:
        await photo_file.download_to_drive(photo_path)
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        success = storage.append_log(user_id, food, calories, timestamp_str, photo_path)

        if success:
            await update.message.reply_text(f"📸✅ Logged with photo: {food} ({calories} kcal)")
        else:
            await update.message.reply_text("❌ Oops, something went wrong saving your log. Try again later.")

    except Exception as e:
        print(f"Error handling photo: {e}")
        await update.message.reply_text("❌ Error saving photo. Try again later.")

async def show_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    logs = storage.get_today_logs(user_id, today)

    if not logs:
        await update.message.reply_text("Nothing to oink about today 🐽")
        return

    total_calories = sum(log['calories'] for log in logs)

    lines = [f"{log['timestamp']} — {log['food']} ({log['calories']} kcal)" for log in logs]
    response = f"🍽️ Today's food logs:\n" + "\n".join(lines)
    response += f"\n\n📊 Total today: {total_calories} kcal"

    await update.message.reply_text(response)


# --- FastAPI lifecycle events to manage Telegram bot ---

@app.on_event("startup")
async def startup_event():
    global telegram_app
    telegram_app = ApplicationBuilder().token(TOKEN).build()

    # Register handlers here AFTER creating telegram_app
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("show", show_logs))
    telegram_app.add_handler(MessageHandler(filters.PHOTO, log_food_with_photo))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, log_food))

    await telegram_app.initialize()
    await telegram_app.start()


@app.on_event("shutdown")
async def shutdown_event():
    global telegram_app
    if telegram_app:
        await telegram_app.stop()


# --- Webhook endpoint ---

@app.post("/webhook")
async def webhook(request: Request):
    global telegram_app
    if telegram_app is None:
        return {"status": "error", "detail": "Telegram app not initialized yet"}

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"status": "ok"}
