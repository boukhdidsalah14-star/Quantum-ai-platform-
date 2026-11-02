"""Telegram interface for the QUANTUM AI dashboard and public market data.

Commands are informational only. This bot never places trades.
"""
import logging
import os
import httpx

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

from app.market_data import ALLOWED_SYMBOLS, get_candles as get_crypto_candles, get_market_overview
from app.deriv_market_data import DerivMarketDataError, get_active_markets as get_deriv_markets, get_candles as get_deriv_candles, get_contract_proposal as get_deriv_proposal
from app.signals import analyze_candles
from app.backtest import backtest_candles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBAPP_URL = os.getenv("TELEGRAM_WEBAPP_URL", "").strip()

def _normalise_deriv_symbol(symbol: str, category: str) -> str:
    value = symbol.strip().upper()
    if category == "forex":
        return "frx" + (value[3:] if value.startswith("FRX") else value)
    return value


def _infer_market_category(symbol: str) -> str:
    value = symbol.strip().upper()
    if value in ALLOWED_SYMBOLS:
        return "crypto"
    if value.startswith("FRX") or (len(value) == 6 and value.isalpha()):
        return "forex"
    return "synthetic"



def _price_line(item: dict) -> str:
    price = float(item["price"])
    change = float(item["change_percent"])
    return f"{item['symbol']}: ${price:,.4f} ({change:+.2f}%)"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "⚡ QUANTUM AI\n\n"
        "Your trading workspace is ready. Explore Forex, binary-option underlyings, crypto markets, and indicator signals.\n\n"
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
        "/price BTCUSDT — price for a supported crypto market\n"
        "/forex — list Deriv Forex pairs\n"
        "/binary — list Forex and synthetic binary-option underlyings\n"
        "/signal EURUSD 15m forex — analyze Forex (frx prefix optional)\n"
        "/signal R_100 5m synthetic — analyze a binary underlying\n"
        "/signal BTCUSDT 1h crypto — analyze crypto\n"
        "/quote R_100 CALL 1 5 — preview a 1 USD, 5-minute price\n"
        "/backtest frxEURUSD 15m forex — test historical direction\n"
        "/backtest BTCUSDT 1h crypto — test crypto history\n"
        "/help — show this help\n"
        "/status — platform status\n\n"
        "All market data is read-only. This bot cannot open or manage trades."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🟢 Dashboard foundation: available\n"
        "📈 Public Forex, synthetic, and crypto data: read-only\n"
        "🧠 CALL / PUT / WAIT indicator analysis: available\n"
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




async def deriv_market_list(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str) -> None:
    try:
        rows = await get_deriv_markets(category)
        if not rows:
            raise RuntimeError("No active markets returned")
        title = "FOREX MARKETS" if category == "forex" else "BINARY-OPTION UNDERLYINGS" if category == "all" else "SYNTHETIC INDICES"
        lines = [f"{row['symbol']} · {row['name']} · {row['market'].upper()}" for row in rows[:25]]
        await update.effective_message.reply_text(
            "⚡ QUANTUM AI · " + title + "\n\n" + "\n".join(lines)
            + "\n\nUse /signal SYMBOL 15m to analyze a market. Public data only."
        )
    except (DerivMarketDataError, RuntimeError):
        logger.exception("Telegram Deriv market list failed")
        await update.effective_message.reply_text("Deriv public market list is temporarily unavailable.")


async def forex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await deriv_market_list(update, context, "forex")


async def binary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await deriv_market_list(update, context, "all")


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /signal EURUSD 15m forex\n"
            "For synthetic binary underlyings: /signal R_100 5m synthetic"
        )
        return
    symbol = context.args[0].strip()
    timeframe = context.args[1].lower() if len(context.args) > 1 else "15m"
    category = context.args[2].lower() if len(context.args) > 2 else _infer_market_category(symbol)
    symbol = symbol.upper() if category == "crypto" else _normalise_deriv_symbol(symbol, category)
    intervals = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
    if category not in {"forex", "synthetic", "crypto"} or timeframe not in intervals:
        await update.effective_message.reply_text("Use a valid timeframe and category (forex, synthetic, or crypto).")
        return
    try:
        if category == "crypto":
            if timeframe not in {"1h", "4h", "1d"}:
                await update.effective_message.reply_text("Crypto signal timeframes: 1h, 4h, or 1d.")
                return
            candle_data = await get_crypto_candles(symbol, timeframe, 100)
        else:
            markets_data = await get_deriv_markets(category)
            if not any(item["symbol"] == symbol for item in markets_data):
                await update.effective_message.reply_text("That symbol is not currently listed in the selected Deriv market category. Use /forex or /binary to see available symbols.")
                return
            candle_data = await get_deriv_candles(symbol, intervals[timeframe], 100)
        result = analyze_candles(candle_data, timeframe)
        reasons = "\n".join("• " + reason for reason in result["reasons"][:4])
        await update.effective_message.reply_text(
            "⚡ QUANTUM AI · " + ("FOREX" if category == "forex" else "CRYPTO" if category == "crypto" else "BINARY UNDERLYING") + "\n\n"
            + symbol + " · " + timeframe + "\n"
            + "SIGNAL: " + result["direction"] + "\n"
            + "Trend: " + result["trend"] + " · RSI: " + str(result["rsi_14"]) + "\n"
            + "Signal strength: " + result["signal_strength"] + "\n\n"
            + reasons + "\n\n"
            + "Indicator research only. No trade was placed. Test on demo."
        )
    except (DerivMarketDataError, ValueError, httpx.HTTPError):
        logger.exception("Telegram /signal request failed")
        await update.effective_message.reply_text("Market data or signal analysis is temporarily unavailable. No signal was issued.")





async def quote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Usage: /quote R_100 CALL 1 5\n"
            "Arguments: SYMBOL CALL|PUT STAKE_USD DURATION_MINUTES\n"
            "Preview only — this command never buys a contract."
        )
        return
    symbol = context.args[0].strip()
    if symbol.upper().startswith("FRX") or (len(symbol) == 6 and symbol.isalpha()):
        symbol = _normalise_deriv_symbol(symbol, "forex")
    direction = context.args[1].upper().strip()
    try:
        amount = float(context.args[2]) if len(context.args) > 2 else 1.0
        duration = int(context.args[3]) if len(context.args) > 3 else 5
        result = await get_deriv_proposal(symbol, direction, amount, duration, "m", "USD")
        await update.effective_message.reply_text(
            "🧾 QUANTUM AI · DEMO PRICE PREVIEW\n\n"
            + symbol + " · " + direction + " · " + str(duration) + " min\n"
            + "Stake: " + f"{result['stake']:.2f}" + " " + result["currency"] + "\n"
            + "Potential payout: " + f"{result['payout']:.2f}" + " " + result["currency"] + "\n\n"
            + "Quote only. No contract was purchased."
        )
    except (ValueError, DerivMarketDataError) as exc:
        await update.effective_message.reply_text("Quote unavailable: " + str(exc))




async def backtest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: /backtest EURUSD 15m forex")
        return
    symbol = context.args[0].strip()
    timeframe = context.args[1].lower() if len(context.args) > 1 else "15m"
    category = context.args[2].lower() if len(context.args) > 2 else _infer_market_category(symbol)
    symbol = symbol.upper() if category == "crypto" else _normalise_deriv_symbol(symbol, category)
    intervals = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
    if category not in {"forex", "synthetic", "crypto"} or timeframe not in intervals:
        await update.effective_message.reply_text("Choose a supported timeframe and category: forex, synthetic, or crypto.")
        return
    try:
        if category == "crypto":
            if timeframe not in {"1h", "4h", "1d"}:
                await update.effective_message.reply_text("Crypto backtest timeframes: 1h, 4h, or 1d.")
                return
            candles = await get_crypto_candles(symbol, timeframe, 200)
        else:
            markets_data = await get_deriv_markets(category)
            if not any(item["symbol"] == symbol for item in markets_data):
                await update.effective_message.reply_text("That symbol is not listed in the selected market category.")
                return
            candles = await get_deriv_candles(symbol, intervals[timeframe], 200)
        result = backtest_candles(candles, timeframe, 1)
        accuracy = "Not enough directional signals" if result["directional_accuracy_percent"] is None else str(result["directional_accuracy_percent"]) + "%"
        await update.effective_message.reply_text(
            "🧪 QUANTUM AI · HISTORICAL TEST\n\n"
            + symbol + " · " + timeframe + "\n"
            + "Directional accuracy: " + accuracy + "\n"
            + "Wins: " + str(result["wins"]) + " · Losses: " + str(result["losses"]) + "\n"
            + "WAITs: " + str(result["waits"]) + " · Candles: " + str(result["candles_tested"])
            + "\n\nHistorical direction only. Not a profit forecast. No trades placed."
        )
    except (DerivMarketDataError, ValueError, httpx.HTTPError):
        logger.exception("Telegram /backtest request failed")
        await update.effective_message.reply_text("Historical test unavailable. No trades were placed.")


def build_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("markets", markets))
    application.add_handler(CommandHandler("price", price))
    application.add_handler(CommandHandler("forex", forex))
    application.add_handler(CommandHandler("binary", binary))
    application.add_handler(CommandHandler("signal", signal))
    application.add_handler(CommandHandler("quote", quote))
    application.add_handler(CommandHandler("backtest", backtest))
    return application
