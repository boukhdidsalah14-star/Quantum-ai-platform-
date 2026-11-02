"""Telegram launcher for the QUANTUM AI dashboard.

Commands are informational only. This bot does not place trades.
"""
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBAPP_URL = os.getenv("TELEGRAM_WEBAPP_URL", "").strip()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "⚡ QUANTUM AI\n\n"
        "Your trading workspace is ready. Open the dashboard to view public crypto markets.\n\n"
        "Market data is informational only. Trading and order execution are currently disabled."
    )
    if WEBAPP_URL.startswith("https://"):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Open QUANTUM AI", web_app=WebAppInfo(url=WEBAPP_URL))]])
        await update.effective_message.reply_text(message, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(message + "\n\nDashboard link is not configured yet.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "QUANTUM AI commands:\n/start — open the dashboard\n/help — show this help\n/status — platform status\n\n"
        "This build provides read-only public crypto data. It cannot open or manage trades."
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🟢 Dashboard foundation: available\n"
        "📈 Public crypto market data: read-only\n"
        "🔒 Broker connection: not configured\n"
        "⛔ Automated execution: disabled"
    )

def build_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status))
    return application
