
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

ADMIN_CHAT_ID = 123902504  # شناسه عددی مدیر
BOT_TOKEN = "866070292:AAHXfqObC98ajBHnDRdfqs24haU6crDxlv8"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    button = KeyboardButton("ورود/خروج", request_location=True)
    keyboard = ReplyKeyboardMarkup([[button]], resize_keyboard=True)
    await update.message.reply_text(
        "لطفاً برای ثبت حضور، لوکیشن زنده خود را به صورت دستی ارسال کنید.",
        reply_markup=keyboard
    )

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    location = update.message.location

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"{user.full_name} لوکیشن خود را ارسال کرده است:\nhttps://maps.google.com/?q={location.latitude},{location.longitude}"
    )
    await update.message.reply_text("حضور شما ثبت شد. ممنون!")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))  # برای /start در گروه و خصوصی
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.run_polling()
    
