from contextlib import asynccontextmanager
import asyncio
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
from app.market_data import ALLOWED_SYMBOLS, get_candles, get_market_overview, get_order_book
from app.mexc_market_data import get_market_overview as get_mexc_market_overview, get_candles as get_mexc_candles
from app.mexc_live_execution import get_account_info as get_mexc_account_info, MexcExecutionError
from app.mexc_credential_vault import init_db as init_mexc_vault_db, save as save_mexc_credentials, metadata as mexc_credential_metadata, delete as delete_mexc_credentials, MexcVaultError
from app.deriv_demo import DerivConfigError, DerivConnectionError, get_demo_status, get_demo_status_for_credentials
from app.deriv_market_data import DerivMarketDataError, get_active_markets as get_deriv_markets, get_candles as get_deriv_candles, get_available_contracts as get_deriv_contracts, get_contract_proposal as get_deriv_proposal, get_tick_quotes as get_deriv_tick_quotes
from app.signals import analyze_candles
from app.backtest import backtest_candles
from app.risk import evaluate_demo_risk
from app.brokers import broker_capabilities
from app.paper_trading import (init_paper_db, open_paper_trade, list_paper_trades, close_paper_trade)
from app.credential_vault import (init_vault_db, save_demo, load_demo, metadata as demo_credential_metadata, delete_demo, VaultError)
from app.deriv_trading import (init_deriv_trading_db, reserve_trade, mark_trade_failed, mark_trade_open, list_customer_trades, list_open_trades, risk_snapshot, execute_demo_binary_trade, get_demo_contract_status, apply_contract_update, DerivExecutionError)

from app.virtual_platforms import init_db as init_virtual_db, snapshot as virtual_snapshot, positions as virtual_positions, open_position as open_virtual_position, settle as settle_virtual_position

from app.olymp_paper import (init_db as init_olymp_paper_db, open_trade as open_olymp_paper_trade, list_trades as list_olymp_paper_trades, settle_trade as settle_olymp_paper_trade, set_account_balance as set_olymp_paper_balance, get_risk_snapshot as olymp_paper_risk_snapshot)

from app.auth import (
    authenticate_customer, create_customer, create_session,
    get_customer_for_session, init_auth_db, revoke_session, signup_enabled,
    consume_login_attempt, clear_login_attempts,
)
from app.subscriptions import (
    init_db as init_subscription_db, payment_configured, create_order as create_subscription_order,
    attach_payment, verify_ipn_signature, apply_finished_payment, subscription_for_customer,
)

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)
# HTTPX logs full request URLs; Telegram Bot API URLs contain the bot token.
# Suppress request-URL logging so secrets never appear in Render logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
SESSION_COOKIE = "quantum_session"
TELEGRAM_TOKEN_ENV_NAMES = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "BOT_TOKEN")


def _configured_telegram_token() -> tuple[str, str]:
    for name in TELEGRAM_TOKEN_ENV_NAMES:
        value = os.getenv(name, "").strip()
        if value:
            return value, name
    return "", ""


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class DerivDemoCredentials(BaseModel):
    account_id: str = Field(min_length=4, max_length=64)
    token: str = Field(min_length=1, max_length=4096)


class MexcCredentials(BaseModel):
    api_key: str = Field(min_length=1, max_length=256)
    api_secret: str = Field(min_length=1, max_length=512)


class PaperTradeRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=20)
    side: str
    quantity: float = Field(gt=0, le=1000000)


class OlympSignalRequest(BaseModel):
    candles: list[dict] = Field(min_length=30, max_length=500)
    timeframe: str = Field(min_length=2, max_length=3)


class OlympPaperTradeRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=30)
    direction: str
    stake: float = Field(gt=0, le=1000000000)
    expiry_minutes: int = Field(ge=1, le=60)
    reference_price: float = Field(gt=0)
    price_source: str = Field(min_length=3, max_length=80)


class OlympPaperBalanceRequest(BaseModel):
    account_balance: float = Field(gt=0, le=1000000000)


class OlympPaperSettlementRequest(BaseModel):
    exit_price: float = Field(gt=0)
    payout_rate: float = Field(gt=0, le=1, default=0.82)


class DerivDemoTradeRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=30)
    contract_type: str = Field(min_length=3, max_length=4)
    stake: float = Field(gt=0, le=2)
    duration_minutes: int = Field(ge=1, le=60)


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


def _persistent_credentials_ready() -> bool:
    return (
        os.getenv("QUANTUM_PERSISTENT_STORAGE", "").strip().lower() == "true"
        and bool(os.getenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", "").strip())
    )


def _demo_execution_enabled() -> bool:
    return (
        _persistent_credentials_ready()
        and os.getenv("QUANTUM_DERIV_DEMO_TRADING_ENABLED", "").strip().lower() == "true"
    )


def _session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=7 * 24 * 60 * 60,
        httponly=True, secure=os.getenv("ENVIRONMENT", "development").lower() == "production",
        samesite="lax", path="/",
    )


async def _deriv_demo_monitor_loop():
    """Refresh open customer demo contracts while the service is running."""
    while True:
        try:
            for trade in list_open_trades():
                if trade.get("status") != "open" or not trade.get("contract_id"):
                    continue
                credentials = load_demo(trade["customer_id"])
                if not credentials:
                    continue
                try:
                    contract = await get_demo_contract_status(
                        credentials["token"], credentials["account_id"],
                        os.getenv("DERIV_APP_ID", "").strip(), trade["contract_id"],
                    )
                    apply_contract_update(trade["customer_id"], trade["id"], contract)
                except Exception as exc:
                    logger.warning("Deriv demo contract refresh failed for trade %s: %s", trade["id"], str(exc)[:180])
        except Exception:
            logger.exception("Deriv demo monitor loop failed")
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_auth_db()
    init_subscription_db()
    init_paper_db()
    init_olymp_paper_db()
    init_virtual_db()
    init_vault_db()
    init_mexc_vault_db()
    if _persistent_credentials_ready():
        init_deriv_trading_db()
    monitor_task = None
    if _demo_execution_enabled():
        monitor_task = asyncio.create_task(_deriv_demo_monitor_loop())
    bot = None
    token, token_env_name = _configured_telegram_token()
    if token:
        from app.telegram_bot import build_application
        bot = build_application(token)
        try:
            await bot.initialize()
            from app.telegram_bot import configure_telegram_menu
            telegram_identity = await bot.bot.get_me()
            logger.info("Telegram token authenticated from %s for bot @%s", token_env_name, telegram_identity.username)
            await configure_telegram_menu(bot)
            webhook_base = os.getenv("TELEGRAM_WEBAPP_URL", "").strip().rstrip("/")
            webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
            if not webhook_base.startswith("https://"):
                raise RuntimeError("TELEGRAM_WEBAPP_URL must be an HTTPS public URL")
            if len(webhook_secret) < 32:
                raise RuntimeError("TELEGRAM_WEBHOOK_SECRET must be configured with at least 32 characters")
            # Webhooks avoid competing getUpdates pollers and work reliably with one Render web service.
            await bot.start()
            await bot.bot.set_webhook(
                url=webhook_base + "/telegram/webhook",
                secret_token=webhook_secret,
                allowed_updates=["message"],
                drop_pending_updates=False,
            )
            app.state.telegram_bot = bot
            app.state.telegram_webhook_secret = webhook_secret
            logger.info("QUANTUM AI Telegram webhook registered successfully")
        except Exception:
            logger.exception("Telegram bot could not start; keeping the dashboard available")
            try:
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
        if monitor_task is not None:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        if bot is not None:
            if bot.running:
                await bot.stop()
            await bot.shutdown()


app = FastAPI(title="QUANTUM AI", version="0.5.0", description="Mobile trading workspace with customer identity foundation", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    secret_header: str = Header(default="", alias="X-Telegram-Bot-Api-Secret-Token"),
):
    bot = getattr(request.app.state, "telegram_bot", None)
    expected = getattr(request.app.state, "telegram_webhook_secret", "")
    if bot is None or not expected or not hmac.compare_digest(secret_header, expected):
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook")
    try:
        from telegram import Update
        payload = await request.json()
        update = Update.de_json(payload, bot.bot)
        await bot.process_update(update)
    except Exception:
        logger.exception("Telegram webhook update processing failed")
        raise HTTPException(status_code=400, detail="Telegram update could not be processed")
    return {"ok": True}


@app.get("/api/subscription")
async def get_subscription(request: Request):
    init_auth_db()
    init_subscription_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {
        **subscription_for_customer(customer["id"]),
        "price_usd": 20,
        "duration_days": 30,
        "payment_currency": "usdttrc20",
        "payment_configured": payment_configured(),
    }


@app.post("/api/subscription/checkout")
async def create_subscription_checkout(request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_subscription_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not payment_configured():
        raise HTTPException(status_code=503, detail="NOWPayments is not fully configured on the server")
    api_key = os.getenv("NOWPAYMENTS_API_KEY", "").strip()
    public_url = os.getenv("QUANTUM_PUBLIC_URL", "").strip().rstrip("/")
    order_id = create_subscription_order(customer["id"])
    body = {
        "price_amount": 20,
        "price_currency": "usd",
        "pay_currency": "usdttrc20",
        "ipn_callback_url": public_url + "/api/payments/nowpayments/ipn",
        "order_id": order_id,
        "order_description": "QUANTUM AI 30-day subscription",
        "is_fixed_rate": False,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.nowpayments.io/v1/payment",
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
            payment = response.json()
        checkout = attach_payment(order_id, payment)
        return checkout
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("NOWPayments checkout creation failed: %s", str(exc)[:180])
        raise HTTPException(status_code=502, detail="NOWPayments could not create the checkout. No subscription was activated.")


@app.post("/api/payments/nowpayments/ipn")
async def nowpayments_ipn(
    request: Request,
    signature: str = Header(default="", alias="x-nowpayments-sig"),
):
    init_subscription_db()
    secret = os.getenv("NOWPAYMENTS_IPN_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Payment notifications are not configured")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payment notification")
    if not isinstance(payload, dict) or not verify_ipn_signature(payload, signature, secret):
        raise HTTPException(status_code=401, detail="Invalid payment notification signature")
    try:
        result = apply_finished_payment(payload)
        return {"ok": True, **result}
    except ValueError as exc:
        logger.warning("NOWPayments notification rejected: %s", str(exc)[:180])
        raise HTTPException(status_code=400, detail="Payment notification did not match a valid subscription order")


@app.get("/api/brokers")
async def brokers():
    """Return verified implementation scope; this endpoint never claims a live account."""
    return broker_capabilities()


@app.get("/api/auth/config")
async def auth_config():
    """Expose non-sensitive account availability to the dashboard."""
    return {"registration_enabled": signup_enabled()}


@app.get("/health")
async def health(request: Request):
    bot = getattr(request.app.state, "telegram_bot", None)
    return {
        "status": "ok",
        "service": "quantum-ai",
        "market_data": "public-read-only",
        "telegram_configured": bool(_configured_telegram_token()[0]),
        "telegram_bot_running": bool(bot and bot.running),
        "telegram_webhook_active": bool(bot and getattr(request.app.state, "telegram_webhook_secret", "")),
        "webapp_url_configured": os.getenv("TELEGRAM_WEBAPP_URL", "").strip().startswith("https://"),
        "deriv_demo_connector": "available",
        "customer_auth": "available",
        "credential_storage_ready": _persistent_credentials_ready(),
        "deriv_demo_execution_enabled": _demo_execution_enabled(),
        "deriv_demo_monitor_running": bool(_demo_execution_enabled()),
        "order_execution": False,
        "trading_enabled": False,
    }


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


@app.post("/api/connections/deriv/demo/verify")
async def verify_and_save_deriv_demo_connection(payload: DerivDemoCredentials, request: Request):
    """Verify the customer's virtual Deriv account before storing its encrypted token."""
    _check_same_origin(request)
    init_auth_db()
    init_vault_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    app_id = os.getenv("DERIV_APP_ID", "").strip()
    if not app_id:
        raise HTTPException(status_code=503, detail="Deriv application ID is not configured on the server")
    try:
        verified = await get_demo_status_for_credentials(payload.token, payload.account_id, app_id)
        persistent_storage_ready = _persistent_credentials_ready()
        if not persistent_storage_ready:
            return {
                **verified,
                "credential_saved": False,
                "persistence_required": True,
                "note": "Account verified, but credentials were not saved because persistent encrypted storage is not configured.",
            }
        saved = save_demo(customer["id"], payload.account_id, payload.token)
        return {**verified, "credential_saved": saved.get("connected", False), "persistence_required": False}
    except DerivConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DerivConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
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


@app.get("/api/connections/mexc")
async def mexc_connection(request: Request):
    init_auth_db()
    init_mexc_vault_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return mexc_credential_metadata(customer["id"])


@app.post("/api/connections/mexc/verify")
async def verify_and_save_mexc_connection(payload: MexcCredentials, request: Request):
    """Verify MEXC account access using a signed read-only request.

    MEXC Spot has no sandbox. This endpoint never places or cancels orders.
    Customers should use an API key with read-only permission and IP restrictions.
    """
    _check_same_origin(request)
    init_auth_db()
    init_mexc_vault_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        verified = await get_mexc_account_info(payload.api_key, payload.api_secret)
        if not _persistent_credentials_ready():
            return {**verified, "credential_saved": False, "persistence_required": True,
                    "note": "Account key verified with a read-only request; credentials were not saved because durable encrypted storage is unavailable."}
        saved = save_mexc_credentials(customer["id"], payload.api_key, payload.api_secret)
        return {**verified, "credential_saved": saved.get("connected", False),
                "persistence_required": False,
                "note": "Account verified and credentials encrypted. No order was placed."}
    except MexcExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except MexcVaultError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.delete("/api/connections/mexc")
async def remove_mexc_connection(request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_mexc_vault_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"deleted": delete_mexc_credentials(customer["id"])}


@app.get("/api/deriv/demo/trades")
async def deriv_demo_trades(request: Request):
    if not _persistent_credentials_ready():
        raise HTTPException(status_code=503, detail="Durable encrypted storage is required for demo trade history")
    init_auth_db()
    init_deriv_trading_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {
        "mode": "demo",
        "execution_enabled": _demo_execution_enabled(),
        "risk": risk_snapshot(customer["id"]),
        "trades": list_customer_trades(customer["id"]),
    }


@app.post("/api/deriv/demo/trades")
async def create_deriv_demo_trade(
    payload: DerivDemoTradeRequest,
    request: Request,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
):
    _check_same_origin(request)
    if not _demo_execution_enabled():
        raise HTTPException(
            status_code=503,
            detail="Deriv demo execution is locked until persistent encrypted storage and the explicit demo-trading switch are enabled",
        )
    init_auth_db()
    init_vault_db()
    init_deriv_trading_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    credentials = load_demo(customer["id"])
    if not credentials:
        raise HTTPException(status_code=409, detail="Connect and verify your own Deriv demo account first")
    try:
        active = await get_deriv_markets("all")
        market = next((item for item in active if item["symbol"] == payload.symbol and not item["is_suspended"]), None)
        if not market:
            raise HTTPException(status_code=400, detail="Selected Deriv market is not currently available")
        reserved, duplicate = reserve_trade(
            customer["id"], credentials["account_id"], payload.symbol,
            payload.contract_type, payload.stake, payload.duration_minutes,
            idempotency_key,
        )
        if duplicate:
            return {"trade": reserved, "duplicate": True, "mode": "demo",
                    "note": "This idempotency key was already used; no second order was sent."}
        try:
            result = await execute_demo_binary_trade(
                credentials["token"], credentials["account_id"],
                os.getenv("DERIV_APP_ID", "").strip(), payload.symbol,
                payload.contract_type, payload.stake, payload.duration_minutes,
            )
            trade = mark_trade_open(customer["id"], reserved["id"], result)
            return {"trade": trade, "duplicate": False, "mode": "demo",
                    "note": "Deriv demo contract purchased. Contract settlement is monitored by the service."}
        except DerivExecutionError as exc:
            mark_trade_failed(customer["id"], reserved["id"], str(exc), uncertain=exc.uncertain)
            if exc.uncertain:
                raise HTTPException(status_code=409, detail=str(exc) + ". The order is marked UNKNOWN and new trades are blocked until reconciled.")
            raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DerivMarketDataError:
        raise HTTPException(status_code=502, detail="Could not verify the selected Deriv market")


@app.post("/api/olymp-trade/analyze")
async def analyze_olymp_trade_signal(payload: OlympSignalRequest, request: Request):
    """Analyze caller-supplied completed candles; no broker connection is made."""
    init_auth_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    from app.olymp_trade import analyze_signal
    try:
        result = analyze_signal(payload.candles, payload.timeframe)
        result["customer_visible_data_note"] = "Candles were supplied by the caller and have not been verified against Olymp Trade."
        return result
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/olymp-trade/paper/settings")
async def get_olymp_paper_settings(request: Request):
    init_auth_db()
    init_olymp_paper_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"broker": "olymp_trade", "mode": "paper",
            "risk": olymp_paper_risk_snapshot(customer["id"])}


@app.put("/api/olymp-trade/paper/settings")
async def update_olymp_paper_settings(payload: OlympPaperBalanceRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_olymp_paper_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return {"broker": "olymp_trade", "mode": "paper",
                "risk": set_olymp_paper_balance(customer["id"], payload.account_balance)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/olymp-trade/paper/trades")
async def olymp_trade_paper_trades(request: Request):
    init_auth_db()
    init_olymp_paper_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"broker": "olymp_trade", "mode": "paper", "execution": "simulated_only",
            "trades": list_olymp_paper_trades(customer["id"])}


@app.post("/api/olymp-trade/paper/trades")
async def create_olymp_trade_paper_trade(payload: OlympPaperTradeRequest, request: Request,
                                         idempotency_key: str = Header(default="", alias="Idempotency-Key")):
    _check_same_origin(request)
    init_auth_db()
    init_olymp_paper_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        trade = open_olymp_paper_trade(customer["id"], payload.symbol, payload.direction,
            payload.stake, payload.expiry_minutes, payload.reference_price, idempotency_key, payload.price_source)
        return {"broker": "olymp_trade", "mode": "paper", "execution": "simulated_only",
                "broker_order_sent": False, "trade": trade}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/olymp-trade/paper/trades/{trade_id}/settle")
async def settle_olymp_trade_paper_trade(trade_id: str, payload: OlympPaperSettlementRequest,
                                         request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_olymp_paper_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        trade = settle_olymp_paper_trade(customer["id"], trade_id, payload.exit_price, payload.payout_rate)
        if not trade:
            raise HTTPException(status_code=404, detail="Open Olymp Trade paper position not found")
        return {"broker": "olymp_trade", "mode": "paper", "execution": "simulated_only",
                "broker_order_sent": False, "trade": trade}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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


@app.get("/api/orderbook/{symbol}")
async def binance_order_book(symbol: str, limit: int = Query(default=10, ge=5, le=20)):
    """Read-only public Binance spot order book depth."""
    try:
        return {"source": "Binance public spot depth", **await get_order_book(symbol, limit)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Binance order book is temporarily unavailable")


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
        higher_map = {"1h": "4h", "4h": "1d"}.get(timeframe)
        higher_data = {}
        if higher_map:
            try:
                higher_data[higher_map] = (await get_candles(symbol, higher_map, 100) if source == "binance"
                                           else await get_mexc_candles(symbol, higher_map, 100))
            except (ValueError, httpx.HTTPError):
                higher_data = {}
        result = analyze_candles(candle_data, timeframe, higher_timeframes=higher_data,
                                 asset=symbol.upper())
        result.update({"symbol": symbol.upper(), "category": "crypto",
                       "source": source.upper() + " public candles",
                       "higher_timeframe_data": "confirmed" if higher_data else "unavailable_or_not_applicable",
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
        higher_tf = {"1m": "5m", "5m": "15m", "15m": "1h", "30m": "4h",
                     "1h": "4h", "4h": "1d"}.get(timeframe)
        higher_data = {}
        if higher_tf:
            try:
                higher_data[higher_tf] = await get_deriv_candles(symbol, intervals[higher_tf], 100)
            except (ValueError, DerivMarketDataError):
                higher_data = {}
        result = analyze_candles(candle_data, timeframe, higher_timeframes=higher_data,
                                 asset=symbol)
        result.update({
            "higher_timeframe_data": "confirmed" if higher_data else "unavailable_or_not_applicable",
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


@app.head("/", include_in_schema=False)
async def dashboard_head():
    # Render and uptime monitors commonly probe the root with HEAD.
    # Return a clean 200 without downloading the dashboard HTML.
    return Response(status_code=200)


@app.get("/")
async def dashboard():
    return FileResponse(ROOT / "static" / "index.html")


class VirtualPositionRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=30)
    side: str
    stake: float = Field(gt=0, le=1000000000)
    entry_price: float = Field(gt=0)
    expiry_minutes: int = Field(default=5, ge=1, le=60)


class VirtualSettlementRequest(BaseModel):
    exit_price: float = Field(gt=0)


@app.get("/api/virtual/accounts")
async def get_virtual_accounts(request: Request):
    init_auth_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Sign in to access your private virtual accounts")
    return {"accounts": virtual_snapshot(customer["id"]), "execution": "virtual_simulation_only"}


@app.get("/api/virtual/{platform}/positions")
async def get_virtual_positions(platform: str, request: Request):
    init_auth_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return {"platform": platform, "positions": virtual_positions(customer["id"], platform),
                "execution": "virtual_simulation_only"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/virtual/{platform}/positions")
async def create_virtual_position(platform: str, payload: VirtualPositionRequest, request: Request,
                                  idempotency_key: str = Header(default="", alias="Idempotency-Key")):
    _check_same_origin(request)
    init_auth_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        position = open_virtual_position(customer["id"], platform, payload.symbol, payload.side,
                                          payload.stake, payload.entry_price, payload.expiry_minutes,
                                          idempotency_key)
        return {"position": position, "accounts": virtual_snapshot(customer["id"]),
                "execution": "virtual_simulation_only", "broker_order_sent": False}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/virtual/{platform}/positions/{position_id}/settle")
async def close_virtual_position(platform: str, position_id: str, payload: VirtualSettlementRequest,
                                 request: Request):
    _check_same_origin(request)
    init_auth_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        position = settle_virtual_position(customer["id"], platform, position_id, payload.exit_price)
        if not position:
            raise HTTPException(status_code=404, detail="Open virtual position not found")
        return {"position": position, "accounts": virtual_snapshot(customer["id"]),
                "execution": "virtual_simulation_only", "broker_order_sent": False}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
