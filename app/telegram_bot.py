"""Telegram interface for the QUANTUM AI dashboard and public market data.

Commands are informational only. This bot never places trades.
"""
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

from app.market_data import ALLOWED_SYMBOLS, get_market_overview

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBAPP_URL = os.getenv("TELEGRAM_WEBAPP_URL", "").strip()


def _price_line(item: dict) -> str:
    price = float(item["price"])
    change = float(item["change_percent"])
    return f"{item['symbol']}: ${price:,.4f} ({change:+.2f}%)"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "⚡ QUANTUM AI\n\n"
        "Your trading workspace is ready. View public crypto markets or open the dashboard.\n\n"
        "Market data is informational only. Broker trading and order execution are disabled."
    )
    if WEBAPP_URL.startswith("https://"):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Open QUANTUM AI", web_app=WebAppInfo(url=WEBAPP_URL))]])
        await update.effective_message.reply_text(message, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(message + "\n\nDashboard link is not configured yet.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "QUANTUM AI commands:\n"
        "/start — open the dashboard\n"
        "/markets — latest public crypto prices\n"
        "/price BTCUSDT — price for a supported market\n"
        "/help — show this help\n"
        "/status — platform status\n\n"
        "All market data is read-only. This bot cannot open or manage trades."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🟢 Dashboard foundation: available\n"
        "📈 Public crypto market data: read-only\n"
        "🔒 Broker execution: disabled\n"
        "⛔ Automated trading: disabled"
    )


async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        rows = await get_market_overview()
        rows = [row for row in rows if row.get("symbol") in ALLOWED_SYMBOLS]
        rows.sort(key=lambda row: row["symbol"])
        if not rows:
            raise RuntimeError("No market quotes returned")
        await update.effective_message.reply_text(
            "📊 QUANTUM AI · PUBLIC MARKETS\n\n"
            + "\n".join(_price_line(row) for row in rows)
            + "\n\nRead-only public exchange prices. Not broker quotes or trade instructions."
        )
    except Exception:
        logger.exception("Telegram /markets request failed")
        await update.effective_message.reply_text("Public market data is temporarily unavailable. Please try again shortly.")


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: /price BTCUSDT")
        return
    symbol = context.args[0].upper().strip()
    if symbol not in ALLOWED_SYMBOLS:
        await update.effective_message.reply_text("Unsupported market. Try BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, or XRPUSDT.")
        return
    try:
        rows = await get_market_overview()
        row = next((item for item in rows if item.get("symbol") == symbol), None)
        if row is None:
            raise RuntimeError("Requested quote was not returned")
        await update.effective_message.reply_text(
            "📍 " + _price_line(row)
            + "\n24h high: $" + f"{float(row['high']):,.4f}"
            + "\n24h low: $" + f"{float(row['low']):,.4f}"
            + "\n\nPublic market data only; no trade has been placed."
        )
    except Exception:
        logger.exception("Telegram /price request failed")
        await update.effective_message.reply_text("That public quote is temporarily unavailable. Please try again shortly.")


def build_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("markets", markets))
    application.add_handler(CommandHandler("price", price))
    return application
