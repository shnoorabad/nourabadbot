
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import sqlite3
from datetime import datetime
import os
from collections import defaultdict
from openpyxl import Workbook
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

BOT_TOKEN = "866070292:AAG5jnr1idoHgZRWYLHTaKKb4ewy52lk9Pg"
ADMIN_CHAT_ID = 123902504
DB_FILE = "attendance.db"
FONT_PATH = "./fonts/Vazir.ttf"
PDF_REPORT = "attendance_report.pdf"
EXCEL_REPORT = "attendance_report.xlsx"
SERVICE_ACCOUNT_FILE = "/etc/secrets/credentials.json"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            full_name TEXT,
            action TEXT,
            latitude REAL,
            longitude REAL,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_next_action(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT action FROM attendance WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return "خروج" if row and row[0] == "ورود" else "ورود"

def save_attendance(user_id, full_name, action, latitude, longitude):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO attendance (user_id, full_name, action, latitude, longitude, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, full_name, action, latitude, longitude, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def upload_to_drive():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/drive.file"])
    service = build("drive", "v3", credentials=creds)
    file_metadata = {"name": f"attendance_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.db"}
    media = MediaFileUpload(DB_FILE, mimetype="application/octet-stream")
    service.files().create(body=file_metadata, media_body=media, fields="id").execute()

def generate_reports():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, full_name, action, timestamp FROM attendance ORDER BY timestamp")
    records = cursor.fetchall()
    conn.close()

    data = defaultdict(lambda: defaultdict(list))
    for uid, name, action, ts in records:
        date_str = ts[:10]
        data[(uid, name)][date_str].append((action, ts))

    pdfmetrics.registerFont(TTFont("Vazir", FONT_PATH))
    c = canvas.Canvas(PDF_REPORT)
    c.setFont("Vazir", 12)
    y = 800
    c.drawString(100, y, "گزارش روزانه حضور کاربران")
    y -= 30

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.append(["نام", "تاریخ", "مدت (ساعت)"])

    for (uid, name), days in data.items():
        for day, actions in days.items():
            ins = [datetime.fromisoformat(t) for a, t in actions if a == "ورود"]
            outs = [datetime.fromisoformat(t) for a, t in actions if a == "خروج"]
            ins.sort()
            outs.sort()
            total = sum((outs[i] - ins[i]).total_seconds() for i in range(min(len(ins), len(outs))))
            hours = round(total / 3600, 2)
            line = f"{name} - {day} : {hours} ساعت"
            c.drawString(100, y, line)
            y -= 20
            ws.append([name, day, hours])
            if y < 50:
                c.showPage()
                y = 800

    c.save()
    wb.save(EXCEL_REPORT)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = update.effective_user.id == ADMIN_CHAT_ID
    buttons = [[KeyboardButton("ثبت حضور", request_location=True)]]
    if is_admin:
        buttons.append([KeyboardButton("گزارش‌گیری")])
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("یکی از گزینه‌ها را انتخاب کنید:", reply_markup=reply_markup)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "گزارش‌گیری" and update.effective_user.id == ADMIN_CHAT_ID:
        generate_reports()
        await update.message.reply_text("در حال ارسال گزارش‌ها...")
        await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=open(PDF_REPORT, "rb"))
        await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=open(EXCEL_REPORT, "rb"))

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    location = update.message.location
    action = get_next_action(user.id)
    save_attendance(user.id, user.full_name, action, location.latitude, location.longitude)
    await update.message.reply_text(f"{action} شما ثبت شد.")
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"{user.full_name} - {action}\nموقعیت: https://maps.google.com/?q={location.latitude},{location.longitude}\nزمان: {datetime.now().isoformat()}"
    )
    upload_to_drive()

if __name__ == "__main__":
    if not os.path.exists(DB_FILE):
        init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.run_polling()
