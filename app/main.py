from contextlib import asynccontextmanager
from pathlib import Path
import hmac
import logging
import os
from urllib.parse import urlsplit
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app.market_data import ALLOWED_SYMBOLS, get_candles, get_market_overview
from app.mexc_market_data import get_market_overview as get_mexc_market_overview, get_candles as get_mexc_candles
from app.deriv_demo import DerivConfigError, DerivConnectionError, get_demo_status
from app.deriv_market_data import DerivMarketDataError, get_active_markets as get_deriv_markets, get_candles as get_deriv_candles, get_available_contracts as get_deriv_contracts, get_contract_proposal as get_deriv_proposal, get_tick_quotes as get_deriv_tick_quotes
from app.signals import analyze_candles
from app.backtest import backtest_candles
from app.risk import evaluate_demo_risk
from app.brokers import broker_capabilities
from app.paper_trading import (init_paper_db, open_paper_trade, list_paper_trades, close_paper_trade)
from app.credential_vault import (init_vault_db, save_demo, metadata as demo_credential_metadata, delete_demo, VaultError)
from app.auth import (
    authenticate_customer, create_customer, create_session,
    get_customer_for_session, init_auth_db, revoke_session, signup_enabled,
    consume_login_attempt, clear_login_attempts,
)

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)
SESSION_COOKIE = "quantum_session"


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class DerivDemoCredentials(BaseModel):
    account_id: str = Field(min_length=4, max_length=64)
    token: str = Field(min_length=1, max_length=4096)


class PaperTradeRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=20)
    side: str
    quantity: float = Field(gt=0, le=1000000)


def _check_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    try:
        parsed = urlsplit(origin)
        origin_host = parsed.netloc.lower()
        request_host = request.headers.get("host", "").lower()
        valid_scheme = parsed.scheme in {"http", "https"}
        if not valid_scheme or not origin_host or origin_host != request_host:
            raise ValueError("origin mismatch")
    except ValueError:
        raise HTTPException(status_code=403, detail="Cross-origin request rejected")


def _session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=7 * 24 * 60 * 60,
        httponly=True, secure=os.getenv("ENVIRONMENT", "development").lower() == "production",
        samesite="lax", path="/",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_auth_db()
    init_paper_db()
    init_vault_db()
    bot = None
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        from app.telegram_bot import build_application
        bot = build_application(token)
        try:
            await bot.initialize()
            await bot.start()
            if bot.updater is not None:
                await bot.updater.start_polling(allowed_updates=["message"])
            app.state.telegram_bot = bot
            logger.info("QUANTUM AI Telegram bot started with the web service")
        except Exception:
            logger.exception("Telegram bot could not start; keeping the dashboard available")
            try:
                if bot.updater is not None and bot.updater.running:
                    await bot.updater.stop()
                if bot.running:
                    await bot.stop()
                await bot.shutdown()
            except Exception:
                logger.exception("Telegram bot cleanup after startup failure was incomplete")
            bot = None
    else:
        logger.info("Telegram bot is not configured; dashboard will run without it")
    try:
        yield
    finally:
        if bot is not None:
            if bot.updater is not None and bot.updater.running:
                await bot.updater.stop()
            if bot.running:
                await bot.stop()
            await bot.shutdown()


app = FastAPI(title="QUANTUM AI", version="0.5.0", description="Mobile trading workspace with customer identity foundation", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/api/brokers")
async def brokers():
    """Return verified implementation scope; this endpoint never claims a live account."""
    return broker_capabilities()


@app.get("/api/auth/config")
async def auth_config():
    """Expose non-sensitive account availability to the dashboard."""
    return {"registration_enabled": signup_enabled()}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "quantum-ai", "market_data": "public-read-only", "telegram_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()), "deriv_demo_connector": "available", "customer_auth": "available", "order_execution": False, "trading_enabled": False}


@app.post("/api/auth/register")
async def register(payload: Credentials, request: Request, response: Response):
    _check_same_origin(request)
    if not signup_enabled():
        raise HTTPException(status_code=403, detail="Customer registration is not open yet")
    init_auth_db()
    try:
        customer = create_customer(payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    token = create_session(customer["id"])
    _session_cookie(response, token)
    return {"customer": customer, "authenticated": True}


@app.post("/api/auth/login")
async def login(payload: Credentials, request: Request, response: Response):
    _check_same_origin(request)
    init_auth_db()
    client_ip = request.client.host if request.client else "unknown"
    if not consume_login_attempt(payload.email, client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again in 15 minutes.")
    customer = authenticate_customer(payload.email, payload.password)
    if not customer:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    clear_login_attempts(payload.email, client_ip)
    token = create_session(customer["id"])
    _session_cookie(response, token)
    return {"customer": customer, "authenticated": True}


@app.get("/api/auth/me")
async def auth_me(request: Request):
    init_auth_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"customer": customer, "authenticated": True}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    _check_same_origin(request)
    revoke_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax",
                           secure=os.getenv("ENVIRONMENT", "development").lower() == "production")
    return {"authenticated": False}


@app.get("/api/connections/deriv/demo")
async def deriv_demo_connection(request: Request):
    init_auth_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return demo_credential_metadata(customer["id"])


@app.put("/api/connections/deriv/demo")
async def save_deriv_demo_connection(payload: DerivDemoCredentials, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_vault_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return save_demo(customer["id"], payload.account_id, payload.token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except VaultError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.delete("/api/connections/deriv/demo")
async def remove_deriv_demo_connection(request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_vault_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"deleted": delete_demo(customer["id"])}


@app.get("/api/paper/trades")
async def paper_trades(request: Request):
    init_auth_db()
    init_paper_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    trades = list_paper_trades(customer["id"])
    try:
        quotes = {item["symbol"]: float(item["price"]) for item in await get_market_overview()}
    except httpx.HTTPError:
        quotes = {}
    for trade in trades:
        mark = quotes.get(trade["symbol"])
        if trade["status"] == "open" and mark is not None:
            sign = 1 if trade["side"] == "long" else -1
            trade["mark_price"] = mark
            trade["unrealized_pnl"] = (mark - trade["entry_price"]) * trade["quantity"] * sign
    return {"mode": "paper", "trades": trades, "execution": "simulated_only"}


@app.post("/api/paper/trades")
async def create_paper_trade(payload: PaperTradeRequest, request: Request, idempotency_key: str = Header(default="", alias="Idempotency-Key")):
    _check_same_origin(request)
    init_auth_db()
    init_paper_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        markets_data = await get_market_overview()
        quote = next((item for item in markets_data if item["symbol"] == payload.symbol.upper()), None)
        if not quote:
            raise HTTPException(status_code=503, detail="No current public quote for this paper-trading market")
        trade = open_paper_trade(customer["id"], payload.symbol, payload.side, payload.quantity,
                                 float(quote["price"]), None, None, idempotency_key)
        return {"trade": trade, "mode": "paper", "execution": "simulated_only"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Public quote unavailable; paper order was not created")


@app.post("/api/paper/trades/{trade_id}/close")
async def close_paper_trade_endpoint(trade_id: str, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_paper_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    trades = list_paper_trades(customer["id"])
    owned = next((trade for trade in trades if trade["id"] == trade_id and trade["status"] == "open"), None)
    if not owned:
        raise HTTPException(status_code=404, detail="Open paper trade not found")
    try:
        markets_data = await get_market_overview()
        quote = next((item for item in markets_data if item["symbol"] == owned["symbol"]), None)
        if not quote:
            raise HTTPException(status_code=503, detail="No current public quote; paper trade remains open")
        trade = close_paper_trade(customer["id"], trade_id, float(quote["price"]))
        return {"trade": trade, "mode": "paper", "execution": "simulated_only"}
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Public quote unavailable; paper trade remains open")


@app.get("/api/mexc/markets")
async def mexc_markets():
    try:
        return {"source": "MEXC public Spot API", "account_connected": False,
                "execution_enabled": False, "markets": await get_mexc_market_overview()}
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="MEXC public market data is temporarily unavailable")


@app.get("/api/mexc/candles/{symbol}")
async def mexc_candles(symbol: str, interval: str = Query(default="1h"), limit: int = Query(default=72, ge=20, le=200)):
    try:
        return {"symbol": symbol.upper(), "interval": interval, "source": "MEXC public Spot API",
                "candles": await get_mexc_candles(symbol, interval, limit)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="MEXC public candle data is temporarily unavailable")


@app.get("/api/markets")
async def markets():
    try:
        return {"source": "Binance public market data", "markets": await get_market_overview()}
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Public market data is temporarily unavailable")


@app.get("/api/candles/{symbol}")
async def candles(symbol: str, interval: str = Query(default="1h"), limit: int = Query(default=72, ge=20, le=200)):
    try:
        return {"symbol": symbol.upper(), "interval": interval, "source": "Binance public market data", "candles": await get_candles(symbol, interval, limit)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Public candle data is temporarily unavailable")


@app.get("/api/signals/crypto/{symbol}")
async def crypto_signal(
    symbol: str,
    source: str = Query(default="binance"),
    timeframe: str = Query(default="1h"),
):
    """Calculate a read-only indicator signal from public crypto candles."""
    if timeframe not in {"1h", "4h", "1d"}:
        raise HTTPException(status_code=400, detail="Crypto signal timeframe must be 1h, 4h, or 1d")
    if source not in {"binance", "mexc"}:
        raise HTTPException(status_code=400, detail="Crypto source must be binance or mexc")
    if symbol.upper() not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail="Unsupported crypto market")
    try:
        candle_data = (await get_candles(symbol, timeframe, 100) if source == "binance"
                       else await get_mexc_candles(symbol, timeframe, 100))
        result = analyze_candles(candle_data, timeframe)
        result.update({"symbol": symbol.upper(), "category": "crypto",
                       "source": source.upper() + " public candles",
                       "execution_enabled": False})
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Crypto historical data is temporarily unavailable")


@app.get("/api/backtest/crypto/{symbol}")
async def crypto_backtest(
    symbol: str,
    source: str = Query(default="binance"),
    timeframe: str = Query(default="1h"),
    lookahead_candles: int = Query(default=1, ge=1, le=4),
):
    """Evaluate historical crypto signal direction without placing orders."""
    if timeframe not in {"1h", "4h", "1d"}:
        raise HTTPException(status_code=400, detail="Crypto backtest timeframe must be 1h, 4h, or 1d")
    if source not in {"binance", "mexc"}:
        raise HTTPException(status_code=400, detail="Crypto source must be binance or mexc")
    if symbol.upper() not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail="Unsupported crypto market")
    try:
        candle_data = (await get_candles(symbol, timeframe, 200) if source == "binance"
                       else await get_mexc_candles(symbol, timeframe, 200))
        result = backtest_candles(candle_data, timeframe, lookahead_candles)
        result.update({"symbol": symbol.upper(), "category": "crypto",
                       "source": source.upper() + " historical candles",
                       "execution_enabled": False})
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Crypto historical data is temporarily unavailable")


@app.get("/api/backtest/deriv/{symbol}")
async def deriv_backtest(
    symbol: str,
    category: str = Query(default="forex"),
    timeframe: str = Query(default="15m"),
    lookahead_candles: int = Query(default=1, ge=1, le=4),
):
    """Evaluate historical CALL/PUT direction without placing orders."""
    intervals = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
                 "1h": 3600, "4h": 14400, "1d": 86400}
    if category not in {"forex", "synthetic"}:
        raise HTTPException(status_code=400, detail="Category must be forex or synthetic")
    if timeframe not in intervals:
        raise HTTPException(status_code=400, detail="Unsupported backtest timeframe")
    try:
        markets_data = await get_deriv_markets(category)
        if not any(item["symbol"] == symbol for item in markets_data):
            raise HTTPException(status_code=400, detail="Symbol is not in the selected Deriv market category")
        candle_data = await get_deriv_candles(symbol, intervals[timeframe], 200)
        result = backtest_candles(candle_data, timeframe, lookahead_candles)
        result.update({"symbol": symbol, "category": category,
                       "source": "Deriv public historical candles",
                       "execution_enabled": False})
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DerivMarketDataError:
        raise HTTPException(status_code=502, detail="Deriv historical data is temporarily unavailable")


@app.get("/api/risk/policy")
async def risk_policy():
    """Return the fixed demo-only risk policy; no order execution is enabled."""
    return evaluate_demo_risk(0.0, 0, 0)


@app.get("/api/deriv/proposal/{symbol}")
async def deriv_contract_quote(
    symbol: str,
    contract_type: str = Query(default="CALL"),
    amount: float = Query(default=1.0, gt=0, le=2.0),
    duration: int = Query(default=5),
    currency: str = Query(default="USD", min_length=3, max_length=3),
):
    """Return a public binary contract price quote; never purchases the contract."""
    try:
        return await get_deriv_proposal(symbol, contract_type, amount, duration, "m", currency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DerivMarketDataError:
        raise HTTPException(status_code=502, detail="Deriv price quote is temporarily unavailable")


@app.get("/api/signals/deriv/{symbol}")
async def deriv_signal(
    symbol: str,
    category: str = Query(default="forex"),
    timeframe: str = Query(default="15m"),
):
    """Calculate a transparent CALL/PUT/WAIT indicator from Deriv public candles."""
    intervals = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
                 "1h": 3600, "4h": 14400, "1d": 86400}
    if category not in {"forex", "synthetic"}:
        raise HTTPException(status_code=400, detail="Category must be forex or synthetic")
    if timeframe not in intervals:
        raise HTTPException(status_code=400, detail="Unsupported signal timeframe")
    try:
        markets_data = await get_deriv_markets(category)
        if not any(item["symbol"] == symbol for item in markets_data):
            raise HTTPException(status_code=400, detail="Symbol is not in the selected Deriv market category")
        candle_data = await get_deriv_candles(symbol, intervals[timeframe], 100)
        result = analyze_candles(candle_data, timeframe)
        result.update({
            "symbol": symbol,
            "category": category,
            "market_type": "binary_options_underlying" if category == "synthetic" else "forex",
            "source": "Deriv public market candles",
            "execution_enabled": False,
        })
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DerivMarketDataError:
        raise HTTPException(status_code=502, detail="Deriv data is temporarily unavailable; no signal was generated")


@app.get("/api/deriv/markets")
async def deriv_markets(category: str = Query(default="all")):
    """Read-only public Forex and synthetic underlyings available on Deriv."""
    try:
        markets = (await get_deriv_markets(category))[:25]
        quotes = {}
        if markets:
            try:
                quotes = await get_deriv_tick_quotes([item["symbol"] for item in markets])
            except DerivMarketDataError:
                quotes = {}
        for item in markets:
            item["price"] = quotes.get(item["symbol"])
        return {"source": "Deriv public market data", "category": category,
                "account_connected": False, "execution_enabled": False,
                "markets": markets}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DerivMarketDataError:
        raise HTTPException(status_code=502, detail="Deriv public market data is temporarily unavailable")


@app.get("/api/deriv/candles/{symbol}")
async def deriv_candles(symbol: str, granularity: int = Query(default=900), count: int = Query(default=100, ge=20, le=200)):
    """Read-only OHLC candles for a verified active Deriv Forex/synthetic symbol."""
    try:
        return {"symbol": symbol, "granularity": granularity, "source": "Deriv public market data",
                "candles": await get_deriv_candles(symbol, granularity, count),
                "execution_enabled": False}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DerivMarketDataError:
        raise HTTPException(status_code=502, detail="Deriv public candle data is temporarily unavailable")


@app.get("/api/deriv/contracts/{symbol}")
async def deriv_contracts(symbol: str):
    """Discover binary/option contract types; this does not create a proposal or place an order."""
    try:
        return {"source": "Deriv public contract metadata", "execution_enabled": False,
                **await get_deriv_contracts(symbol)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DerivMarketDataError:
        raise HTTPException(status_code=502, detail="Deriv contract information is temporarily unavailable")


@app.get("/api/deriv/demo/status")
async def deriv_demo_status(x_admin_key: str = Header(default="", alias="X-Admin-Key")):
    expected = os.getenv("QUANTUM_ADMIN_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin status check is not configured")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=403, detail="Admin authorization required")
    try:
        return await get_demo_status()
    except DerivConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (DerivConnectionError, httpx.HTTPError):
        raise HTTPException(status_code=502, detail="Deriv demo account check failed; verify demo credentials and permissions")


@app.get("/")
async def dashboard():
    return FileResponse(ROOT / "static" / "index.html")
