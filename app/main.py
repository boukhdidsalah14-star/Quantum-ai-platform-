from contextlib import asynccontextmanager
from pathlib import Path
import hmac
import logging
import os
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app.market_data import get_candles, get_market_overview
from app.deriv_demo import DerivConfigError, DerivConnectionError, get_demo_status
from app.auth import (
    authenticate_customer, create_customer, create_session,
    get_customer_for_session, init_auth_db, revoke_session, signup_enabled,
)

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)
SESSION_COOKIE = "quantum_session"


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


def _session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=7 * 24 * 60 * 60,
        httponly=True, secure=os.getenv("ENVIRONMENT", "development").lower() == "production",
        samesite="lax", path="/",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_auth_db()
    bot = None
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        from app.telegram_bot import build_application
        bot = build_application(token)
        await bot.initialize()
        await bot.start()
        if bot.updater is not None:
            await bot.updater.start_polling(allowed_updates=["message"])
        app.state.telegram_bot = bot
        logger.info("QUANTUM AI Telegram bot started with the web service")
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "quantum-ai", "market_data": "public-read-only", "telegram_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()), "deriv_demo_connector": "available", "customer_auth": "available", "order_execution": False, "trading_enabled": False}


@app.post("/api/auth/register")
async def register(payload: Credentials, response: Response):
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
async def login(payload: Credentials, response: Response):
    init_auth_db()
    customer = authenticate_customer(payload.email, payload.password)
    if not customer:
        raise HTTPException(status_code=401, detail="Invalid email or password")
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
    revoke_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax",
                           secure=os.getenv("ENVIRONMENT", "development").lower() == "production")
    return {"authenticated": False}


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
