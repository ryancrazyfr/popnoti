from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from telegram import Update, ChatPermissions
import os
import json
from datetime import datetime
from io import StringIO
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# === CONFIG ===
BOT_TOKEN = os.environ['BOT_TOKEN']
GOOGLE_JSON = os.environ['GOOGLE_JSON']
SHEET_NAME = "POP Submissions"
POP_DIR = "pop_submissions"
DRIVE_FOLDER_ID = "1GvJdGDW7ZZPTyhbxNW-W9P1J94unyGvp"

# === INIT ===
if not os.path.exists(POP_DIR):
    os.makedirs(POP_DIR)

# === Google APIs setup ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GOOGLE_JSON)

# Google Sheets
sheets_creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(sheets_creds)
sheet = client.open(SHEET_NAME).sheet1

# Google Drive
drive_creds = service_account.Credentials.from_service_account_info(creds_dict)
drive_service = build("drive", "v3", credentials=drive_creds)

# === Folder Handling ===
def get_or_create_user_folder(username):
    if not username:
        return DRIVE_FOLDER_ID

    query = f"name = '{username}' and mimeType = 'application/vnd.google-apps.folder' and '{DRIVE_FOLDER_ID}' in parents"
    response = drive_service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    files = response.get("files", [])

    if files:
        return files[0]["id"]

    # Create new folder
    file_metadata = {
        "name": username,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [DRIVE_FOLDER_ID]
    }
    folder = drive_service.files().create(body=file_metadata, fields="id").execute()
    return folder.get("id")

# === File Upload ===
def upload_to_drive(username, filename, filepath):
    folder_id = get_or_create_user_folder(username or "unknown")

    file_metadata = {
        "name": filename,
        "parents": [folder_id]
    }
    media = MediaFileUpload(filepath, mimetype="image/jpeg")
    uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
    return uploaded_file.get("webViewLink")

# === Bot Commands ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /submitpop to send your POP screenshot.")

async def submitpop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please send your POP screenshot now.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    username = user.username or f"user_{user.id}"
    photo = update.message.photo[-1]
    file = await photo.get_file()
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"{username}_{timestamp}.jpg"
    filepath = os.path.join(POP_DIR, filename)
    await file.download_to_drive(filepath)

    # Upload to Google Drive
    drive_link = upload_to_drive(username, filename, filepath)

    # Log to Google Sheet
    sheet.append_row([
        username,
        str(user.id),
        datetime.now().strftime('%Y-%m-%d'),
        datetime.now().strftime('%H:%M:%S'),
        drive_link
    ])

    await update.message.reply_text("✅ POP received and uploaded to your folder in Drive!")

# === Start bot ===
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("submitpop", submitpop))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()

if __name__ == "__main__":
    main()
