import os
import sqlite3
import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from reportlab.pdfgen import canvas
import pandas as pd

# Google Drive imports
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# اطلاعات ادمین
ADMIN_CHAT_ID = 123902504  # عدد واقعی جایگزین شود
BOT_TOKEN = "866070292:AAG5jnr1idoHgZRWYLHTaKKb4ewy52lk9Pg"

# مسیر دیتابیس
DB_FILE = "attendance.db"
PDF_REPORT = "attendance_report.pdf"
EXCEL_REPORT = "attendance_report.xlsx"

# نام فایل سرویس‌اکانت گوگل
SERVICE_ACCOUNT_FILE = "/etc/secrets/credentials.json"

# آپلود فایل در گوگل درایو
def upload_to_drive(file_path):
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)
    file_metadata = {"name": os.path.basename(file_path)}
    media = MediaFileUpload(file_path)
    service.files().create(body=file_metadata, media_body=media, fields="id").execute()

# دانلود فایل دیتابیس از گوگل درایو
def download_from_drive(filename):
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)
    results = service.files().list(q=f"name='{filename}'", fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        file_id = files[0]["id"]
        request = service.files().get_media(fileId=file_id)
        with open(filename, "wb") as f:
            downloader = request.execute()
            f.write(downloader)

# دیتابیس را در صورت عدم وجود بساز
def create_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            full_name TEXT,
            type TEXT,
            latitude REAL,
            longitude REAL,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ذخیره حضور
def save_attendance(user_id, full_name, type, lat, lon):
    now = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO attendance (user_id, full_name, type, latitude, longitude, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, full_name, type, lat, lon, now))
    conn.commit()
    conn.close()

# تولید گزارش
def generate_reports(start_date, end_date):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM attendance", conn)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[(df["timestamp"].dt.date >= pd.to_datetime(start_date).date()) &
            (df["timestamp"].dt.date <= pd.to_datetime(end_date).date())]

    pdf = canvas.Canvas(PDF_REPORT)
    pdf.setFont("Helvetica", 12)
    pdf.drawRightString(580, 820, f"گزارش حضور از {start_date} تا {end_date}")
    y = 780
    grouped = df.sort_values("timestamp").groupby(["user_id", df["timestamp"].dt.date])
    for (user_id, date), group in grouped:
        pdf.drawString(50, y, f"{group['full_name'].iloc[0]} - {date}")
        y -= 20
        ins = group[group["type"] == "ورود"]["timestamp"].tolist()
        outs = group[group["type"] == "خروج"]["timestamp"].tolist()
        total = datetime.timedelta()
        for i in range(min(len(ins), len(outs))):
            t = pd.to_datetime(outs[i]) - pd.to_datetime(ins[i])
            total += t
        pdf.drawString(100, y, f"مدت حضور: {total}")
        y -= 30
        if y < 50:
            pdf.showPage()
            y = 800
    pdf.save()

    df.to_excel(EXCEL_REPORT, index=False)
    conn.close()

# شروع
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [KeyboardButton("ثبت ورود")],
        [KeyboardButton("ثبت خروج")]
    ]
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=reply_markup)

# دکمه ورود/خروج
async def choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["type"] = update.message.text.replace("ثبت ", "")
    await update.message.reply_text("اکنون لوکیشن خود را ارسال کنید:", reply_markup=ReplyKeyboardMarkup(
        [[KeyboardButton("ارسال موقعیت", request_location=True)]], resize_keyboard=True))

# دریافت لوکیشن
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    location = update.message.location
    full_name = user.full_name or "نامشخص"
    type = context.user_data.get("type")
    if type not in ["ورود", "خروج"]:
        await update.message.reply_text("لطفاً ابتدا دکمه ورود یا خروج را انتخاب کنید.")
        return
    save_attendance(user.id, full_name, type, location.latitude, location.longitude)
    await update.message.reply_text("ثبت شد. سپاسگزاریم!")
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"{full_name} ({type})\nموقعیت:\nhttps://maps.google.com/?q={location.latitude},{location.longitude}\nزمان:\n{datetime.datetime.now().isoformat()}"
    )
    context.user_data.clear()

# گزارش
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("دسترسی ندارید.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("فرمت صحیح: /report YYYY-MM-DD YYYY-MM-DD")
        return
    start_date, end_date = args
    generate_reports(start_date, end_date)
    await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=open(PDF_REPORT, "rb"))
    await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=open(EXCEL_REPORT, "rb"))

# بارگذاری دیتابیس از گوگل درایو (در شروع)
if os.path.exists(SERVICE_ACCOUNT_FILE):
    try:
        download_from_drive(DB_FILE)
    except Exception as e:
        print("دانلود از درایو انجام نشد:", e)

# ساخت دیتابیس در صورت نیاز
create_database()

# اجرای بات
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("report", report))
app.add_handler(MessageHandler(filters.Regex("ثبت ورود|ثبت خروج"), choice_handler))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.run_polling()

# بارگذاری دیتابیس روی درایو پس از هر اجرا
try:
    upload_to_drive(DB_FILE)
except Exception as e:
    print("آپلود در گوگل درایو انجام نشد:", e)
