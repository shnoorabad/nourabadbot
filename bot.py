from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

ADMIN_CHAT_ID = 123456789  # شناسه عددی مدیر (جایگزین کن)

BOT_TOKEN = "866070292:AAHXfqObC98ajBHnDRdfqs24haU6crDxlv8"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! لطفاً موقعیت مکانی خود را به‌صورت دستی ارسال کنید تا حضور شما ثبت شود.")

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    location = update.message.location

    # ارسال پیام به مدیر
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"{user.full_name} لوکیشن خود را ارسال کرد:\nhttps://maps.google.com/?q={location.latitude},{location.longitude}"
    )

    await update.message.reply_text("ممنون! حضور شما ثبت شد.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    app.run_polling()

    
