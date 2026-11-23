"""Telegram interface for QUANTUM AI public Forex and crypto analysis."""
import logging
import os
import httpx

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.crypto_market_data import ALLOWED_SYMBOLS, get_candles as get_crypto_candles, get_market_overview as get_crypto_markets
from app.forex_market_data import SYMBOLS as FOREX_SYMBOLS, LABELS as FOREX_LABELS, get_candles as get_forex_candles
from app.signals import analyze_candles
from app.backtest import backtest_candles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
WEBAPP_URL = os.getenv("TELEGRAM_WEBAPP_URL", "").strip()
MINI_APP_URL = WEBAPP_URL + "/?v=20261122-clean-market" if WEBAPP_URL.startswith("https://") else WEBAPP_URL


def _forex_symbol(value: str) -> str:
    value = value.strip().upper()
    key = "frx" + (value[3:] if value.startswith("FRX") else value)
    if key not in FOREX_SYMBOLS:
        raise ValueError("Unsupported Forex symbol")
    return key


def _category(symbol: str) -> str:
    value = symbol.strip().upper()
    if value in ALLOWED_SYMBOLS:
        return "crypto"
    return "forex"


def _price_line(row: dict) -> str:
    change = row.get("change_percent")
    change_text = f" ({float(change):+.2f}%)" if change is not None else ""
    return f"{row['symbol']}: ${float(row['price']):,.4f}{change_text}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = ("⚡ QUANTUM AI\nYOUR MARKETS. ONE COMMAND CENTER.\n\n"
               "Open your workspace for Forex and crypto charts, market analysis, and supported account tools. "
               "Signals are research tools; broker execution is limited to the supported app connections.")
    if WEBAPP_URL.startswith("https://"):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 LAUNCH QUANTUM AI", web_app=WebAppInfo(url=MINI_APP_URL))]])
        await update.effective_message.reply_text(message, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(message + "\n\nDashboard link is not configured yet.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "QUANTUM AI commands:\n/start — open the dashboard\n/status — service status\n"
        "/forex — list Forex pairs\n/markets — latest public crypto prices\n"
        "/price BTCUSDT — crypto quote\n/signal EURUSD 15m forex — Forex analysis\n"
        "/signal BTCUSDT 1h crypto — crypto analysis\n"
        "/backtest EURUSD 15m forex — historical Forex direction\n"
        "/backtest BTCUSDT 1h crypto — historical crypto direction\n/help — this message\n\n"
        "Public market data and signals are read-only. No trades are placed by Telegram."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🟢 QUANTUM AI dashboard: available\n📈 Forex and crypto public data: read-only\n"
        "🧠 CALL / PUT / WAIT analysis: available\n🔒 Supported app broker connections: cTrader and IQ Option signals."
    )


async def forex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = [f"{symbol} · {FOREX_LABELS[symbol]}" for symbol in FOREX_SYMBOLS]
    await update.effective_message.reply_text("⚡ QUANTUM AI · FOREX WATCHLIST\n\n" + "\n".join(lines))


async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        rows = await get_crypto_markets()
        await update.effective_message.reply_text(
            "📊 QUANTUM AI · PUBLIC CRYPTO MARKETS\n\n" +
            "\n".join(_price_line(row) for row in rows if row.get("price") is not None) +
            "\n\nIndependent read-only public market data. No exchange account connection."
        )
    except Exception:
        logger.exception("Telegram /markets request failed")
        await update.effective_message.reply_text("Public crypto market data is temporarily unavailable.")


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0].upper() not in ALLOWED_SYMBOLS:
        await update.effective_message.reply_text("Usage: /price BTCUSDT")
        return
    try:
        rows = await get_crypto_markets()
        row = next(item for item in rows if item["symbol"] == context.args[0].upper())
        await update.effective_message.reply_text(_price_line(row) + "\nPublic market data only.")
    except Exception:
        logger.exception("Telegram /price request failed")
        await update.effective_message.reply_text("That crypto quote is temporarily unavailable.")


async def _candles(symbol: str, timeframe: str, category: str, count: int = 100):
    if category == "crypto":
        if timeframe not in {"1h", "4h", "1d"}:
            raise ValueError("Crypto timeframes: 1h, 4h, 1d")
        return await get_crypto_candles(symbol, timeframe, count)
    granularity = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}.get(timeframe)
    if granularity is None:
        raise ValueError("Unsupported Forex timeframe")
    return await get_forex_candles(_forex_symbol(symbol), granularity, count)


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🔒 Premium signals are available only inside QUANTUM AI after account sign-in and an active paid membership. Open the app with /start, then visit Account to subscribe."
    )


async def backtest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🔒 Historical signal analysis is a premium feature. Sign in to QUANTUM AI and activate your membership to use it."
    )


async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Tap /start to open QUANTUM AI or /help to see the available commands.")


async def configure_telegram_menu(application: Application) -> None:
    commands = [
        BotCommand("start", "Open QUANTUM AI"),
        BotCommand("help", "Show commands"),
        BotCommand("status", "Check app status"),
        BotCommand("forex", "List Forex markets"),
        BotCommand("markets", "View crypto markets"),
        BotCommand("price", "Get a crypto price"),
        BotCommand("signal", "Analyze Forex or crypto"),
        BotCommand("backtest", "Test historical signal direction"),
    ]
    try:
        await application.bot.set_my_commands(commands)
    except Exception:
        logger.exception("Telegram command menu could not be configured")
    if WEBAPP_URL.startswith("https://"):
        try:
            await application.bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Open QUANTUM AI", web_app=WebAppInfo(url=MINI_APP_URL)))
        except Exception:
            logger.exception("Telegram Mini App menu button could not be configured")


def build_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    for name, callback in [
        ("start", start), ("help", help_command), ("status", status),
        ("markets", markets), ("price", price), ("forex", forex),
        ("signal", signal), ("backtest", backtest),
    ]:
        application.add_handler(CommandHandler(name, callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
    return application
