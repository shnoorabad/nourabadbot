
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler
import sqlite3
from datetime import datetime
import os
from collections import defaultdict
from openpyxl import Workbook
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from bidi.algorithm import get_display
import arabic_reshaper
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

ASK_START, ASK_END = range(2)
admin_report_requests = {}

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

def reshape(text):
    return get_display(arabic_reshaper.reshape(text))

def create_pdf_report(records, start_date, end_date):
    pdfmetrics.registerFont(TTFont("Vazir", FONT_PATH))
    c = canvas.Canvas(PDF_REPORT)
    c.setFont("Vazir", 14)
    c.drawRightString(550, 800, reshape(f"گزارش حضور از {start_date} تا {end_date}"))

    y = 770
    grouped = defaultdict(list)
    for row in records:
        key = (row[0], row[4][:10])  # (full_name, date)
        grouped[key].append(row)

    for (name, date), actions in grouped.items():
        total = 0
        ins = [datetime.fromisoformat(r[4]) for r in actions if r[1] == "ورود"]
        outs = [datetime.fromisoformat(r[4]) for r in actions if r[1] == "خروج"]
        for i in range(min(len(ins), len(outs))):
            total += (outs[i] - ins[i]).total_seconds()
        total_hours = round(total / 3600, 2)

        c.drawRightString(550, y, reshape(f"{name} - {date}"))
        y -= 20
        for r in actions:
            t = datetime.fromisoformat(r[4])
            line = f"{r[1]} | {t.strftime('%H:%M')} | مختصات: {r[2]:.5f}, {r[3]:.5f}"
            c.drawRightString(550, y, reshape(line))
            y -= 20
        c.drawRightString(550, y, reshape(f"جمع کل: {total_hours} ساعت"))
        y -= 30
        if y < 50:
            c.showPage()
            y = 800
    c.save()

def create_excel_report(records):
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.append(["نام", "تاریخ", "ورود/خروج", "ساعت", "مختصات", "مدت (ساعت)"])

    grouped = defaultdict(list)
    for r in records:
        key = (r[0], r[4][:10])
        grouped[key].append(r)

    for (name, date), actions in grouped.items():
        ins = [r for r in actions if r[1] == "ورود"]
        outs = [r for r in actions if r[1] == "خروج"]
        total = 0
        for i in range(min(len(ins), len(outs))):
            t1 = datetime.fromisoformat(ins[i][4])
            t2 = datetime.fromisoformat(outs[i][4])
            delta = (t2 - t1).total_seconds()
            total += delta
            ws.append([name, date, "ورود", t1.strftime("%H:%M"), f"{ins[i][2]:.5f},{ins[i][3]:.5f}", ""])
            ws.append(["", "", "خروج", t2.strftime("%H:%M"), f"{outs[i][2]:.5f},{outs[i][3]:.5f}", round(delta / 3600, 2)])
        ws.append(["", "", "", "", "جمع کل:", round(total / 3600, 2)])
        ws.append([])

    wb.save(EXCEL_REPORT)

# ادامه فایل (start, handlers ...) را می‌توان در پیام بعدی فرستاد



from telegram.ext import MessageHandler, filters, ConversationHandler

ASK_START, ASK_END = range(2)
admin_report_requests = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = update.effective_user.id == ADMIN_CHAT_ID
    keyboard = [[KeyboardButton("ثبت حضور", request_location=True)]]
    if is_admin:
        keyboard.append([KeyboardButton("گزارش‌گیری")])
    await update.message.reply_text("لطفاً یک گزینه را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "گزارش‌گیری" and update.effective_user.id == ADMIN_CHAT_ID:
        await update.message.reply_text("تاریخ شروع را وارد کنید (YYYY-MM-DD):")
        return ASK_START
    return ConversationHandler.END

async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_report_requests[user_id] = {"start": update.message.text}
    await update.message.reply_text("تاریخ پایان را وارد کنید (YYYY-MM-DD):")
    return ASK_END

async def ask_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_report_requests[user_id]["end"] = update.message.text
    start = admin_report_requests[user_id]["start"]
    end = admin_report_requests[user_id]["end"]

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, action, latitude, longitude, timestamp FROM attendance WHERE DATE(timestamp) BETWEEN ? AND ?", (start, end))
    records = cursor.fetchall()
    conn.close()

    create_pdf_report(records, start, end)
    create_excel_report(records)

    await update.message.reply_text("گزارش آماده است:")
    await context.bot.send_document(chat_id=user_id, document=open(PDF_REPORT, "rb"))
    await context.bot.send_document(chat_id=user_id, document=open(EXCEL_REPORT, "rb"))
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.")
    return ConversationHandler.END

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

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex("گزارش‌گیری"), text_handler)],
        states={
            ASK_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_start)],
            ASK_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_end)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.run_polling()
