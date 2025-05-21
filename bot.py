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

ADMIN_CHAT_ID = 123902504  # شناسه عددی مدیر
BOT_TOKEN = "866070292:AAHXfqObC98ajBHnDRdfqs24haU6crDxlv8"

# ثبت فونت فارسی با مسیر مطلق (برای اجرای موفق در Render)
font_path = os.path.join(os.path.dirname(__file__), "fonts", "Vazir.ttf")
pdfmetrics.registerFont(TTFont("Vazir", font_path))
registerFontFamily("Vazir", normal="Vazir")

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("ثبت ورود", request_location=True)],
         [KeyboardButton("ثبت خروج", request_location=True)]],
        resize_keyboard=True
    )
    await update.message.reply_text(
        "لطفاً یکی از گزینه‌ها را انتخاب و موقعیت مکانی خود را ارسال کنید.",
        reply_markup=keyboard
    )

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    location = update.message.location
    message_text = update.message.text or ""

    action = "ورود" if "ورود" in message_text else "خروج"
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
    await update.message.reply_text("ثبت شد. ممنون!")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("شما مجاز نیستید.")
        return

    try:
        start_str, end_str = context.args[0], context.args[1]
        start_date = datetime.fromisoformat(start_str)
        end_date = datetime.fromisoformat(end_str)
    except (IndexError, ValueError):
        await update.message.reply_text("لطفاً دستور را به این صورت وارد کنید:\n/report YYYY-MM-DD YYYY-MM-DD")
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
    c.drawString(100, y, f"گزارش حضور کاربران از {start_str} تا {end_str}")
    y -= 30

    for record in summary.values():
        total_seconds = 0
        for i in range(min(len(record["in"]), len(record["out"]))):
            delta = record["out"][i] - record["in"][i]
            total_seconds += delta.total_seconds()
        hours = round(total_seconds / 3600, 2)
        line = f'{record["name"]}: {hours} ساعت حضور'
        c.drawString(100, y, line)
        y -= 20
        if y < 50:
            c.showPage()
            y = 800

    c.save()

    await context.bot.send_document(
        chat_id=ADMIN_CHAT_ID,
        document=open(filename, "rb"),
        caption=f"گزارش از {start_str} تا {end_str}"
    )

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.run_polling()
