from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram import Update
import os
import json
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import re

BOT_TOKEN = os.environ['BOT_TOKEN']
GOOGLE_JSON = os.environ['GOOGLE_JSON']
SHEET_NAME = "POP Submissions"
POP_DIR = "pop_submissions"
DRIVE_FOLDER_ID = "1GvJdGDW7ZZPTyhbxNW-W9P1J94unyGvp"
ADMIN_USER_ID = 6276794389

if not os.path.exists(POP_DIR):
    os.makedirs(POP_DIR)

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GOOGLE_JSON)
sheets_creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(sheets_creds)
sheet = client.open(SHEET_NAME).sheet1
drive_creds = service_account.Credentials.from_service_account_info(creds_dict)
drive_service = build("drive", "v3", credentials=drive_creds)

def get_or_create_user_folder(username):
    if not username:
        return DRIVE_FOLDER_ID
    query = f"name = '{username}' and mimeType = 'application/vnd.google-apps.folder' and '{DRIVE_FOLDER_ID}' in parents"
    response = drive_service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    files = response.get("files", [])
    if files:
        return files[0]["id"]
    file_metadata = {"name": username, "mimeType": "application/vnd.google-apps.folder", "parents": [DRIVE_FOLDER_ID]}
    folder = drive_service.files().create(body=file_metadata, fields="id").execute()
    return folder.get("id")

def upload_to_drive(username, filename, filepath):
    folder_id = get_or_create_user_folder(username or "unknown")
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(filepath, mimetype="image/jpeg")
    uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
    return uploaded_file.get("webViewLink")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "👋 Welcome to the POP Bot!\n\n"
        "📌 *What is POP?*\n"
        "POP (Proof of Promo) is a screenshot you take after promoting our group links "
        "on your own channel or another platform. It helps keep our traffic strong!\n\n"
        "🛠 To submit your weekly POP:\n"
        "1. Tap /submitpop\n"
        "2. Upload your screenshot\n\n"
        "📎 Below are the group links you need to promote 👇"
    )
    await update.message.reply_markdown(welcome_msg)

    pop_links = """🔗 *Do your POP here:*

- [Sexy Baddies](https://t.me/+tGBn9q_6Z-9jMTAx)
- [Content Hub](https://t.me/+F_BNXoMjPPhmNGEx)
- [Seductive Sirens](https://t.me/+nvm1zwZz7FA1MTdh)
- [The Sluts Store](https://t.me/+pkxiRKn2ZvcyMjI8)
- [My Hot Friends](https://t.me/+A47SCYOy2_MzOTcx)
- [CumSlut Paradise](https://t.me/+y5TaJPgVGvI1NzQ0)
"""
    await update.message.reply_markdown(pop_links)

async def submitpop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data["expecting_photo"] = True
    await update.message.reply_text("Please send your POP screenshot now.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.chat_data.get("expecting_photo"):
        await update.message.reply_text("❗ Please tap /submitpop before sending your screenshot.")
        return
    context.chat_data["expecting_photo"] = False

    user = update.message.from_user
    username = user.username or f"user_{user.id}"
    photo = update.message.photo[-1]
    file = await photo.get_file()
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"{username}_{timestamp}.jpg"
    filepath = os.path.join(POP_DIR, filename)
    await file.download_to_drive(filepath)

    context.bot_data[f"pending_{user.id}"] = {
        "username": username,
        "user_id": user.id,
        "filename": filename,
        "filepath": filepath,
        "timestamp": timestamp
    }

    await context.bot.send_photo(
        chat_id=ADMIN_USER_ID,
        photo=open(filepath, "rb"),
        caption=f"👀 *POP Submission from @{username}*\n\nApprove this screenshot?\nReply with /approve_{user.id} or /reject_{user.id}",
        parse_mode="Markdown"
    )

    await update.message.reply_text("📤 POP submitted! Waiting for admin approval.")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        command = update.message.text.strip()
        match = re.match(r"/approve_(\d+)", command)
        if not match:
            await update.message.reply_text("❌ Invalid approve command format.")
            return

        user_id = match.group(1)
        data = context.bot_data.get(f"pending_{user_id}")

        if not data:
            await update.message.reply_text(f"❌ No pending submission found for user {user_id}.")
            return

        drive_link = upload_to_drive(data["username"], data["filename"], data["filepath"])
        sheet.append_row([
            data["username"],
            str(data["user_id"]),
            datetime.now().strftime('%Y-%m-%d'),
            datetime.now().strftime('%H:%M:%S'),
            drive_link
        ])

        await context.bot.send_message(chat_id=data["user_id"], text="✅ Your POP has been approved and logged.")
        await update.message.reply_text(f"✅ Approved and uploaded for @{data['username']}.")
        del context.bot_data[f"pending_{user_id}"]
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        command = update.message.text.strip()
        match = re.match(r"/reject_(\d+)", command)
        if not match:
            await update.message.reply_text("❌ Invalid reject command format.")
            return

        user_id = match.group(1)
        data = context.bot_data.get(f"pending_{user_id}")

        if not data:
            await update.message.reply_text(f"❌ No pending submission found for user {user_id}.")
            return

        await context.bot.send_message(chat_id=data["user_id"], text="❌ Your POP has been rejected by admin.")
        await update.message.reply_text(f"🚫 Rejected submission from @{data['username']}.")
        del context.bot_data[f"pending_{user_id}"]
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("submitpop", submitpop))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/approve_\d+$"), approve))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/reject_\d+$"), reject))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()

if __name__ == "__main__":
    main()
