
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import sqlite3
from datetime import datetime
from collections import defaultdict
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
import os
import arabic_reshaper
from bidi.algorithm import get_display
from openpyxl import Workbook
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ADMIN_CHAT_ID = 123902504  # شناسه عددی مدیر
BOT_TOKEN = "866070292:AAESA0AZzrMvjEEPPJCw8iSUM9hDcRUvnvo"

# فونت فارسی
font_path = os.path.join(os.path.dirname(__file__), "fonts", "Vazir.ttf")
pdfmetrics.registerFont(TTFont("Vazir", font_path))
registerFontFamily("Vazir", normal="Vazir")

def reshape_text(text):
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def init_db():
    conn = sqlite3.connect("attendance.db")
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        full_name TEXT,
        action TEXT,
        latitude REAL,
        longitude REAL,
        timestamp TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

def upload_to_drive():
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    SERVICE_ACCOUNT_FILE = '/etc/secrets/credentials.json'
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)
    now = datetime.now().strftime("%Y-%m-%d_%H-%M")
    file_metadata = {'name': f'attendance_{now}.db'}
    media = MediaFileUpload('attendance.db', mimetype='application/octet-stream')
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("ثبت ورود")], [KeyboardButton("ثبت خروج")]],
        resize_keyboard=True
    )
    await update.message.reply_text("لطفاً نوع حضور را انتخاب کنید:", reply_markup=keyboard)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "ورود" in text:
        context.user_data["action"] = "ورود"
        await update.message.reply_text("اکنون لطفاً لوکیشن خود را ارسال کنید.")
    elif "خروج" in text:
        context.user_data["action"] = "خروج"
        await update.message.reply_text("اکنون لطفاً لوکیشن خود را ارسال کنید.")

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    location = update.message.location
    action = context.user_data.get("action", "نامشخص")
    timestamp = datetime.now().isoformat()

    conn = sqlite3.connect("attendance.db")
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO attendance (user_id, full_name, action, latitude, longitude, timestamp)
                      VALUES (?, ?, ?, ?, ?, ?)""",
                   (user.id, user.full_name, action, location.latitude, location.longitude, timestamp))
    conn.commit()
    conn.close()

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"{user.full_name} ({action})\nموقعیت: https://maps.google.com/?q={location.latitude},{location.longitude}\nزمان: {timestamp}"
    )

    await update.message.reply_text("ثبت شد. سپاسگزاریم!")
    upload_to_drive()

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("دسترسی ندارید.")
        return

    try:
        start_str, end_str = context.args[0], context.args[1]
        start_date = datetime.fromisoformat(start_str)
        end_date = datetime.fromisoformat(end_str)
    except (IndexError, ValueError):
        await update.message.reply_text("فرمت درست:\n/report YYYY-MM-DD YYYY-MM-DD")
        return

    conn = sqlite3.connect("attendance.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, full_name, action, timestamp FROM attendance ORDER BY timestamp")
    records = cursor.fetchall()
    conn.close()

    summary = defaultdict(lambda: {"name": "", "in": [], "out": []})
    for uid, name, action, time in records:
        ts = datetime.fromisoformat(time)
        if start_date <= ts <= end_date:
            summary[uid]["name"] = name
            summary[uid][action == "ورود" and "in" or "out"].append(ts)

    filename = "attendance_report.pdf"
    c = canvas.Canvas(filename)
    c.setFont("Vazir", 12)
    y = 800
    title = reshape_text(f"گزارش حضور کاربران از {start_str} تا {end_str}")
    c.drawString(100, y, title)
    y -= 30
    for record in summary.values():
        total_seconds = 0
        for i in range(min(len(record["in"]), len(record["out"]))):
            delta = record["out"][i] - record["in"][i]
            total_seconds += delta.total_seconds()
        hours = round(total_seconds / 3600, 2)
        line = reshape_text(f'{record["name"]} : {hours} ساعت حضور')
        c.drawString(100, y, line)
        y -= 20
        if y < 50:
            c.showPage()
            y = 800
    c.save()

    await context.bot.send_document(
        chat_id=ADMIN_CHAT_ID,
        document=open(filename, "rb"),
        caption=f"گزارش PDF از {start_str} تا {end_str}"
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "گزارش حضور"
    ws.append(["نام", "ورود", "خروج", "مدت حضور (ساعت)"])
    for record in summary.values():
        name = record["name"]
        for i in range(min(len(record["in"]), len(record["out"]))):
            enter = record["in"][i]
            exit = record["out"][i]
            delta = exit - enter
            hours = round(delta.total_seconds() / 3600, 2)
            ws.append([name, str(enter), str(exit), hours])
    excel_file = "attendance_report.xlsx"
    wb.save(excel_file)

    await context.bot.send_document(
        chat_id=ADMIN_CHAT_ID,
        document=open(excel_file, "rb"),
        caption="گزارش اکسل حضور کاربران"
    )

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.run_polling()
