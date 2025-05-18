from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

ADMIN_CHAT_ID = 123456789  # شناسه عددی مدیر (به‌جای این مقدار، آی‌دی عددی خودتان را بگذارید)
BOT_TOKEN = "866070292:AAHXfqObC98ajBHnDRdfqs24haU6crDxlv8"

# دکمه شروع
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    button = KeyboardButton("حاضر", request_location=True)
    keyboard = ReplyKeyboardMarkup([[button]], resize_keyboard=True)

    await update.message.reply_text(
        "سلام! لطفاً برای ثبت حضور، لوکیشن زنده خود را ارسال کنید.",
        reply_markup=keyboard
    )

# مدیریت لوکیشن
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    location = update.message.location

    # ارسال پیام حضور به مدیر
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"{user.full_name} لوکیشن خود را ارسال کرده است:\nhttps://maps.google.com/?q={location.latitude},{location.longitude}"
    )
    await update.message.reply_text("حضور شما ثبت شد. ممنون!")

# بررسی پیام‌های متنی جهت دیباگ در گروه
async def echo_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    message = update.message.text
    print(f"پیام از {user.full_name} در چت {chat.id} با متن: {message}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), echo_debug))  # فقط برای تست

    app.run_polling()
