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
ADMIN_CHAT_IDS = [123902504,671949064]  # شناسه تلگرام مدیرها
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

    for admin_id in ADMIN_CHAT_IDS:
        await context.bot.send_message(
            chat_id=admin_id,
            text=f"{user.full_name} – {action}\nموقعیت: https://maps.google.com/?q={location.latitude},{location.longitude}\nزمان: {datetime.now(iran).strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await context.bot.send_location(
            chat_id=admin_id,
            latitude=location.latitude,
            longitude=location.longitude
        )

    upload_to_drive()

async def send_leave_request_to_admin(user_id, full_name, leave_type, date, start_hour="", end_hour=""):
    text = f"درخواست مرخصی جدید:\nنام: {full_name}\nنوع: {leave_type}\nتاریخ: {date}"
    if leave_type == "ساعتی":
        text += f"\nساعت: {start_hour} تا {end_hour}"

    callback_approve = f"approve_{user_id}_{date}_{start_hour}_{end_hour}_{leave_type}"
    callback_reject = f"reject_{user_id}_{date}_{start_hour}_{end_hour}_{leave_type}"

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("تأیید", callback_data=callback_approve),
            InlineKeyboardButton("رد", callback_data=callback_reject)
        ]
    ])

    for admin_id in ADMIN_CHAT_IDS:
        await app.bot.send_message(
            chat_id=admin_id,
            text=text,
            reply_markup=buttons
        )
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
        if update.effective_user.id in ADMIN_CHAT_IDS:
           keyboard.append([KeyboardButton("گزارش‌گیری")])
        await update.message.reply_text(" ",  reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
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
    if update.effective_user.id in ADMIN_CHAT_IDS:
       keyboard.append([KeyboardButton("گزارش‌گیری")])
    # await update.message.reply_text("یکی از گزینه‌ها را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return ConversationHandler.END
async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    action, user_id, date = data.split("_", 2)
    status = "تأیید شد ✅" if action == "approve" else "رد شد ❌"

    # گرفتن نام کامل کاربر از تلگرام
    user = await context.bot.get_chat(int(user_id))
    full_name = user.full_name

    # اتصال به دیتابیس و گرفتن اطلاعات مرخصی
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT start_hour, end_hour, leave_type FROM leave_requests WHERE user_id = ? AND date = ?",
        (user_id, date)
    )
    row = cursor.fetchone()

    # بررسی وجود رکورد
    if row:
        start_hour, end_hour, leave_type = row
    else:
        start_hour = end_hour = leave_type = ""

    # به‌روزرسانی وضعیت مرخصی
    cursor.execute("UPDATE leave_requests SET status = ? WHERE user_id = ? AND date = ?", (status, user_id, date))
    conn.commit()
    conn.close()

    # ساخت متن نهایی برای پیام
    if leave_type == "ساعتی":
        msg = f"درخواست مرخصی آقای {full_name} برای تاریخ {date} ساعت {start_hour} تا {end_hour} {status}"
    else:
        msg = f"درخواست مرخصی آقای {full_name} برای تاریخ {date} {status}"

    # پیام برای ادمین
    await query.edit_message_text(msg)

    # پیام به کاربر
    await app.bot.send_message(chat_id=int(user_id), text=f"درخواست مرخصی شما: {msg}")

def create_pdf_report(records, start_date, end_date):
    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date)
    start_shamsi = jdatetime.date.fromgregorian(date=start_dt.date()).strftime("%Y/%m/%d")
    end_shamsi = jdatetime.date.fromgregorian(date=end_dt.date()).strftime("%Y/%m/%d")
    pdfmetrics.registerFont(TTFont("Vazir", FONT_PATH))
    c = canvas.Canvas(PDF_REPORT)
    c.setFont("Vazir", 14)
    y = 800
    c.drawRightString(550, y, reshape(f"گزارش حضور از {start_shamsi} تا {end_shamsi}"))
    y -= 30

    from collections import defaultdict
    user_records = defaultdict(list)
    for row in records:
        user_records[row[0]].append(row)

    for name, recs in user_records.items():
        total_all = 0
        recs.sort(key=lambda x: x[4])  # مرتب‌سازی بر اساس زمان

        c.setFont("Vazir", 13)
        c.drawRightString(550, y, reshape(f"نام: {name}"))
        y -= 25

        # گروه‌بندی بر اساس تاریخ میلادی
        daily_records = defaultdict(list)
        for r in recs:
            day = r[4][:10]  # YYYY-MM-DD
            daily_records[day].append(r)

        for date, day_records in sorted(daily_records.items()):
            entries = []
            exits = []
            date_obj = datetime.fromisoformat(date)
            date_shamsi = jdatetime.date.fromgregorian(date=date_obj.date()).strftime("%Y/%m/%d")
            c.setFont("Vazir", 12)
            c.drawRightString(550, y, reshape(f"📅 تاریخ: {date_shamsi}"))
            y -= 20

            for r in day_records:
                t = datetime.fromisoformat(r[4])
                time_str = t.strftime("%H:%M")
                line = f"{r[1]} | {time_str} | مختصات: {r[2]:.5f}, {r[3]:.5f}"
                c.setFont("Vazir", 11)
                c.drawRightString(550, y, reshape(line))
                y -= 18

                if r[1] == "ورود":
                    entries.append(t)
                elif r[1] == "خروج":
                    exits.append(t)

                if y < 50:
                    c.showPage()
                    c.setFont("Vazir", 14)
                    y = 800

            # محاسبه زمان حضور در این روز
            total_day = 0
            for i in range(min(len(entries), len(exits))):
                total_day += (exits[i] - entries[i]).total_seconds()

            total_day_hours = round(total_day / 3600, 2)
            total_all += total_day  # جمع تمام روزها
            c.setFont("Vazir", 11)
            c.drawRightString(550, y, reshape(f"⏱ حضور این روز: {total_day_hours} ساعت"))
            y -= 25

            if y < 50:
                c.showPage()
                c.setFont("Vazir", 14)
                y = 800

        total_all_hours = round(total_all / 3600, 2)
        c.setFont("Vazir", 12)
        c.drawRightString(550, y, reshape(f"🔸 مجموع کل حضور: {total_all_hours} ساعت"))
        y -= 40

        if y < 50:
            c.showPage()
            c.setFont("Vazir", 14)
            y = 800

    c.save()
def create_excel_report(records):
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.append(["نام", "تاریخ", "ورود/خروج", "ساعت", "مختصات", "مدت (ساعت)"])

    from collections import defaultdict

    user_records = defaultdict(list)
    for r in records:
        user_records[r[0]].append(r)

    for name, recs in user_records.items():
        # مرتب‌سازی همه رکوردهای کاربر بر اساس زمان
        recs.sort(key=lambda x: x[4])
        ws.append([f"نام کاربر: {name}"])
        total_all = 0

        # گروه‌بندی به‌صورت (تاریخ، لیست رکوردها)
        daily_records = defaultdict(list)
        for r in recs:
            day = r[4][:10]
            daily_records[day].append(r)

        for date_str, day_actions in sorted(daily_records.items()):
            ins = [r for r in day_actions if r[1] == "ورود"]
            outs = [r for r in day_actions if r[1] == "خروج"]
            total_day = 0

            try:
                date_g = datetime.fromisoformat(date_str).date()
                date_shamsi = jdatetime.date.fromgregorian(date=date_g).strftime("%Y/%m/%d")
            except:
                date_shamsi = date_str  # fallback

            for i in range(min(len(ins), len(outs))):
                t1 = datetime.fromisoformat(ins[i][4])
                t2 = datetime.fromisoformat(outs[i][4])
                delta = (t2 - t1).total_seconds()

                if delta <= 0:
                    continue

                total_day += delta

                ws.append([name, date_shamsi, "ورود", t1.strftime("%H:%M"), f"{ins[i][2]:.5f},{ins[i][3]:.5f}", ""])
                ws.append(["", date_shamsi, "خروج", t2.strftime("%H:%M"), f"{outs[i][2]:.5f},{outs[i][3]:.5f}", round(delta / 3600, 2)])

            if total_day > 0:
                ws.append(["", "", "", "", "⏱ مجموع این روز:", round(total_day / 3600, 2)])
                ws.append([])

            total_all += total_day

        if total_all > 0:
            ws.append(["", "", "", "", "🔸 مجموع کل حضور کاربر:", round(total_all / 3600, 2)])
            ws.append([])

    wb.save(EXCEL_REPORT)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = update.effective_user.id in ADMIN_CHAT_IDS
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
    cursor.execute(
    "SELECT full_name, action, latitude, longitude, timestamp FROM attendance WHERE timestamp BETWEEN ? AND ?",
    (start + "T00:00:00", end + "T23:59:59")
)
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
