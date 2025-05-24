from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters,
    ConversationHandler, CallbackQueryHandler
)
import sqlite3
from datetime import datetime
import os
import jdatetime
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
from pytz import timezone
iran = timezone("Asia/Tehran")
import os
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = 123902504
DB_FILE = "attendance.db"
FONT_PATH = "./fonts/Vazir.ttf"
PDF_REPORT = "attendance_report.pdf"
EXCEL_REPORT = "attendance_report.xlsx"
SERVICE_ACCOUNT_FILE = "credentials.json"

ASK_START, ASK_END = range(2)
ASK_LEAVE_TYPE, ASK_LEAVE_DATE, ASK_LEAVE_HOURS = range(10, 13)
admin_report_requests = {}
leave_requests = {}

def reshape(text):
    return get_display(arabic_reshaper.reshape(text))

def get_today_shamsi():
    return jdatetime.datetime.fromgregorian(datetime=datetime.now()).strftime("%Y/%m/%d")

def shamsi_to_miladi(shamsi_date):
    try:
        parts = [int(x) for x in shamsi_date.replace("-", "/").split("/")]
        return jdatetime.date(parts[0], parts[1], parts[2]).togregorian().isoformat()
    except:
        return None

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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            full_name TEXT,
            leave_type TEXT,
            date TEXT,
            start_hour TEXT,
            end_hour TEXT,
            status TEXT DEFAULT 'در انتظار',
            submitted_at TEXT
        )
    """)
    conn.commit()
    conn.close()
def get_next_action(user_id):
    today = datetime.now(iran).date().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT action FROM attendance 
        WHERE user_id = ? AND DATE(timestamp) = ? 
        ORDER BY timestamp DESC LIMIT 1
    """, (user_id, today))
    row = cursor.fetchone()
    conn.close()
    return "خروج" if row and row[0] == "ورود" else "ورود"

def save_attendance(user_id, full_name, action, latitude, longitude):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO attendance (user_id, full_name, action, latitude, longitude, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, full_name, action, latitude, longitude, datetime.now(iran).isoformat()))
    conn.commit()
    conn.close()

def upload_to_drive():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/drive"])
    service = build("drive", "v3", credentials=creds)

    filename = "attendance1404.db"

    # بررسی وجود فایل قبلی با همین نام
    results = service.files().list(
        q=f"name = '{filename}'",
        fields="files(id)",
        pageSize=1
    ).execute()

    items = results.get("files", [])
    media = MediaFileUpload(DB_FILE, mimetype="application/octet-stream")

    if items:
        # اگر فایل قبلی وجود دارد، بروزرسانی کن
        file_id = items[0]['id']
        service.files().update(fileId=file_id, media_body=media).execute()
        print("فایل قبلی در گوگل درایو بروزرسانی شد.")
    else:
        # اگر فایل وجود نداشت، فایل جدید ایجاد کن
        file_metadata = {"name": filename}
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        print("فایل جدید در گوگل درایو آپلود شد.")

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    location = update.message.location
    action = get_next_action(user.id)
    save_attendance(user.id, user.full_name, action, location.latitude, location.longitude)
    await update.message.reply_text(f"{action} شما ثبت شد.")
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"{user.full_name} - {action}\nموقعیت: https://maps.google.com/?q={location.latitude},{location.longitude}\nزمان: {datetime.now(iran).isoformat()}"
    )
    upload_to_drive()

async def send_leave_request_to_admin(user_id, full_name, leave_type, date, start_hour="", end_hour=""):
    text = f"درخواست مرخصی جدید:\nنام: {full_name}\nنوع: {leave_type}\nتاریخ: {date}"
    if leave_type == "ساعتی":
        text += f"\nساعت: {start_hour} تا {end_hour}"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("تأیید", callback_data=f"approve_{user_id}_{date}"),
         InlineKeyboardButton("رد", callback_data=f"reject_{user_id}_{date}")]
    ])
    await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, reply_markup=buttons)
from telegram import ReplyKeyboardMarkup, KeyboardButton

async def request_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("ساعتی")], [KeyboardButton("روزانه")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text("نوع مرخصی را انتخاب کنید:", reply_markup=keyboard)
    return ASK_LEAVE_TYPE

async def ask_leave_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text not in ["ساعتی", "روزانه"]:

    return ASK_LEAVE_TYPE
    context.user_data["leave_type"] = text
    today = get_today_shamsi()
    await update.message.reply_text(
        f"تاریخ مرخصی را وارد کنید :\n`{today}`",
        parse_mode="Markdown"
    )
    return ASK_LEAVE_DATE

async def ask_leave_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date"] = update.message.text.strip()
    if context.user_data["leave_type"] == "روزانه":
        full_name = update.effective_user.full_name
        user_id = update.effective_user.id
        now = datetime.now().isoformat()
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO leave_requests (user_id, full_name, leave_type, date, submitted_at) VALUES (?, ?, ?, ?, ?)",
                       (user_id, full_name, "روزانه", context.user_data["date"], now))
        conn.commit()
        conn.close()
        await update.message.reply_text("درخواست شما ثبت شد و در انتظار تأیید ادمین است.")
        await send_leave_request_to_admin(user_id, full_name, "روزانه", context.user_data["date"])
        keyboard = [[KeyboardButton("ثبت حضور", request_location=True)], [KeyboardButton("درخواست مرخصی")]]
        if update.effective_user.id == ADMIN_CHAT_ID:
           keyboard.append([KeyboardButton("گزارش‌گیری")])
        await update.message.reply_text("یکی از گزینه‌ها را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return ConversationHandler.END
    else:
        await update.message.reply_text("ساعت شروع و پایان را وارد کنید (مثلاً 09 تا 12):")
        return ASK_LEAVE_HOURS

async def ask_leave_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hours = update.message.text.strip()
    if "تا" not in hours:
        await update.message.reply_text("لطفاً به فرمت 09 تا 12 وارد کنید.")
        return ASK_LEAVE_HOURS
    start_hour, end_hour = [s.strip() for s in hours.split("تا")]
    full_name = update.effective_user.full_name
    user_id = update.effective_user.id
    date = context.user_data["date"]
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO leave_requests (user_id, full_name, leave_type, date, start_hour, end_hour, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (user_id, full_name, "ساعتی", date, start_hour, end_hour, now))
    conn.commit()
    conn.close()
    await update.message.reply_text("درخواست شما ثبت شد و در انتظار تأیید ادمین است.")
    await send_leave_request_to_admin(user_id, full_name, "ساعتی", date, start_hour, end_hour)
    keyboard = [[KeyboardButton("ثبت حضور", request_location=True)], [KeyboardButton("درخواست مرخصی")]]
    if update.effective_user.id == ADMIN_CHAT_ID:
       keyboard.append([KeyboardButton("گزارش‌گیری")])
    await update.message.reply_text("یکی از گزینه‌ها را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return ConversationHandler.END
async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    action, user_id, date = data.split("_", 2)
    status = "تأیید " if action == "approve" else "رد "

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE leave_requests SET status = ? WHERE user_id = ? AND date = ?", (status, user_id, date))
    conn.commit()
    conn.close()

    await query.edit_message_text(f"درخواست مربوط به {date} {status} شد.")
    await app.bot.send_message(chat_id=int(user_id), text=f"درخواست مرخصی شما برای {date} {status} شد.")

def create_pdf_report(records, start_date, end_date):
    start_shamsi = jdatetime.date.fromgregorian(date=datetime.fromisoformat(start_date).date()).strftime("%Y/%m/%d")
    end_shamsi = jdatetime.date.fromgregorian(date=datetime.fromisoformat(end_date).date()).strftime("%Y/%m/%d")
    pdfmetrics.registerFont(TTFont("Vazir", FONT_PATH))
    c = canvas.Canvas(PDF_REPORT)
    c.setFont("Vazir", 14)
    y = 800
    c.drawRightString(550, y, reshape(f"گزارش حضور از {start_shamsi} تا {end_shamsi}"))
    y -= 30

    grouped = defaultdict(list)
    for row in records:
        key = (row[0], row[4][:10])
        grouped[key].append(row)

    for (name, date), actions in grouped.items():
        total = 0
        ins = [datetime.fromisoformat(r[4]) for r in actions if r[1] == "ورود"]
        outs = [datetime.fromisoformat(r[4]) for r in actions if r[1] == "خروج"]
        for i in range(min(len(ins), len(outs))):
            total += (outs[i] - ins[i]).total_seconds()
        total_hours = round(total / 3600, 2)

        date_shamsi = jdatetime.date.fromgregorian(date=datetime.fromisoformat(date).date()).strftime("%Y/%m/%d")
        c.drawRightString(550, y, reshape(f"{name} - {date_shamsi}"))
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
            date_shamsi = jdatetime.date.fromgregorian(date=datetime.fromisoformat(date).date()).strftime("%Y/%m/%d")
            ws.append([name, date_shamsi, "ورود", t1.strftime("%H:%M"), f"{ins[i][2]:.5f},{ins[i][3]:.5f}", ""])
            ws.append(["", date_shamsi, "خروج", t2.strftime("%H:%M"), f"{outs[i][2]:.5f},{outs[i][3]:.5f}", round(delta / 3600, 2)])
        ws.append(["", "", "", "", "جمع کل:", round(total / 3600, 2)])
        ws.append([])
    wb.save(EXCEL_REPORT)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = update.effective_user.id == ADMIN_CHAT_ID
    keyboard = [[KeyboardButton("ثبت حضور", request_location=True)], [KeyboardButton("درخواست مرخصی")]]
    if is_admin:
        keyboard.append([KeyboardButton("گزارش‌گیری")])
    await update.message.reply_text("یکی از گزینه‌ها را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today_shamsi()
    await update.message.reply_text(
    f"تاریخ شروع را وارد کنید :\n`{get_today_shamsi()}`",
    parse_mode="Markdown"
)
    return ASK_START

async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_report_requests[update.effective_user.id] = {"start": update.message.text}
    await update.message.reply_text("تاریخ پایان را وارد کنید:")
    return ASK_END

async def ask_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    start = shamsi_to_miladi(admin_report_requests[user_id]["start"])
    end = shamsi_to_miladi(update.message.text.strip())
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, action, latitude, longitude, timestamp FROM attendance WHERE DATE(timestamp) BETWEEN ? AND ?", (start, end))
    records = cursor.fetchall()
    conn.close()
    create_pdf_report(records, start, end)
    create_excel_report(records)
    await context.bot.send_document(chat_id=user_id, document=open(PDF_REPORT, "rb"))
    await context.bot.send_document(chat_id=user_id, document=open(EXCEL_REPORT, "rb"))
    return ConversationHandler.END
def download_from_drive(filename):
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    service = build("drive", "v3", credentials=creds)

    # جستجو برای فایل با نام خاص
    results = service.files().list(
        q="name = 'attendance1404.db'",
        fields="files(id)",
        pageSize=1
    ).execute()

    items = results.get('files', [])
    if not items:
        print("فایل attendance1404.db در گوگل درایو پیدا نشد.")
        return

    file_id = items[0]['id']
    request = service.files().get_media(fileId=file_id)
    with open(filename, "wb") as f:
        f.write(request.execute())
    print("فایل attendance1404.db با موفقیت دانلود شد.")

def main():
    try:
        download_from_drive(DB_FILE)
    except Exception as e:
        print("خطا در دانلود فایل از گوگل درایو:", e)

    if not os.path.exists(DB_FILE):
        init_db()
    global app
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_approval))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex("گزارش‌گیری"), report_start)],
        states={
            ASK_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_start)],
            ASK_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_end)],
        },
        fallbacks=[]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex("درخواست مرخصی"), request_leave)],
        states={
            ASK_LEAVE_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_leave_type)],
            ASK_LEAVE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_leave_date)],
            ASK_LEAVE_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_leave_hours)],
        },
        fallbacks=[]
    ))

    app.run_polling()

if __name__ == "__main__":
    main()
