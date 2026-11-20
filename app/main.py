from contextlib import asynccontextmanager
import asyncio
import hashlib
from pathlib import Path
import hmac
import logging
import os
from urllib.parse import urlsplit
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app.market_data import ALLOWED_SYMBOLS, get_order_book
from app.mexc_futures_market_data import get_candles, get_market_overview
from app.market_universe import FOREX_PAIRS, BINARY_PAIRS, CRYPTO_FUTURES
from app.forex_market_data import get_candles as get_forex_candles, get_market_overview as get_forex_market_overview
from app.mexc_market_data import get_market_overview as get_mexc_market_overview, get_candles as get_mexc_candles
from app.mexc_futures_execution import (get_futures_account_info as get_mexc_account_info, MexcFuturesError, MexcFuturesClient, contracts_for_risk, init_auto_db as init_mexc_auto_db, start_auto_strategy as start_mexc_auto_strategy, stop_auto_strategy as stop_mexc_auto_strategy, get_auto_strategy as get_mexc_auto_strategy, list_active_auto_strategies as list_active_mexc_auto_strategies, reserve_auto_order as reserve_mexc_auto_order, update_auto_order as update_mexc_auto_order, set_auto_strategy_error as set_mexc_auto_strategy_error, daily_loss_guard as mexc_daily_loss_guard)
from app.mexc_live_permissions import (init_db as init_mexc_live_permissions_db, get_live_authorization as get_mexc_live_authorization, set_live_authorization as set_mexc_live_authorization, activate_emergency_stop as activate_mexc_emergency_stop, require_live_authorization as require_mexc_live_authorization)
from app.ctrader_oauth import (init_db as init_ctrader_oauth_db, configured as ctrader_oauth_configured, create_authorization as create_ctrader_authorization, complete_authorization as complete_ctrader_authorization, status as ctrader_authorization_status, delete_authorization as delete_ctrader_authorization, CTraderOAuthError)
from app.ctrader_risk import (init_db as init_ctrader_risk_db, update_settings as update_ctrader_risk_settings, set_emergency_stop as set_ctrader_emergency_stop, get_status as get_ctrader_risk_status, CTraderRiskBlocked)
from app.ctrader_permissions import (init_db as init_ctrader_permissions_db, get_permission as get_ctrader_permission, set_demo_permission as set_ctrader_demo_permission, set_live_permission as set_ctrader_live_permission, CTraderPermissionError)
from app.ctrader_open_api import (init_db as init_ctrader_sync_db, discover_demo_accounts as discover_ctrader_demo_accounts, sync_demo_account as sync_ctrader_demo_account, saved_snapshot as get_ctrader_snapshot, clear_snapshot as clear_ctrader_snapshot, discover_demo_symbols as discover_ctrader_demo_symbols, get_demo_candles as get_ctrader_demo_candles, open_demo_trade as open_ctrader_demo_trade, amend_demo_position as amend_ctrader_demo_position, close_demo_position as execute_ctrader_demo_close, get_demo_trade_history as get_ctrader_demo_history, discover_live_accounts as discover_ctrader_live_accounts, discover_live_symbols as discover_ctrader_live_symbols, sync_live_account as sync_ctrader_live_account, saved_live_snapshot as get_ctrader_live_snapshot, open_live_trade as open_ctrader_live_trade, amend_live_position as amend_ctrader_live_position, close_live_position as execute_ctrader_live_close, CTraderOpenAPIError)
from app.mexc_credential_vault import init_db as init_mexc_vault_db, save as save_mexc_credentials, load as load_mexc_credentials, metadata as mexc_credential_metadata, delete as delete_mexc_credentials, MexcVaultError
from app.signals import analyze_candles
from app.signal_history import init_db as init_signal_history_db, record_signal, list_signals, set_signal_result, signal_statistics
from app.backtest import backtest_candles
from app.risk import evaluate_demo_risk
from app.brokers import broker_capabilities
from app.paper_trading import (init_paper_db, open_paper_trade, list_paper_trades, close_paper_trade)
from app.crypto_futures_paper import build_paper_trade_plan

from app.virtual_platforms import init_db as init_virtual_db, snapshot as virtual_snapshot, positions as virtual_positions, open_position as open_virtual_position, settle as settle_virtual_position


from app.auth import (
    authenticate_customer, create_customer, create_session,
    get_customer_for_session, init_auth_db, revoke_session, signup_enabled,
    consume_login_attempt, clear_login_attempts,
)
from app.subscriptions import (
    init_db as init_subscription_db, payment_configured, create_order as create_subscription_order,
    attach_payment, verify_ipn_signature, apply_finished_payment, subscription_for_customer,
    pending_order_for_customer, update_payment_status,
)
from app.referrals import init_db as init_referral_db, attach_signup as attach_referral_signup, dashboard as referral_dashboard, record_paid_order as record_referral_paid_order


load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)
# HTTPX logs full request URLs; Telegram Bot API URLs contain the bot token.
# Suppress request-URL logging so secrets never appear in Render logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
SESSION_COOKIE = "quantum_session"
CTRADER_OAUTH_COOKIE = "quantum_ctrader_oauth_state"
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
    referral_code: str = Field(default="", max_length=32)


class MexcCredentials(BaseModel):
    api_key: str = Field(min_length=1, max_length=256)
    api_secret: str = Field(min_length=1, max_length=512)


class PaperTradeRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=20)
    side: str
    quantity: float = Field(gt=0, le=1000000)

class CryptoPaperAutoRequest(BaseModel):
    symbol: str = Field(min_length=5, max_length=12)
    timeframe: str = Field(default="1h", min_length=2, max_length=3)
    account_balance: float = Field(gt=0, le=1000000)
    risk_percent: float = Field(default=0.5, gt=0, le=1)
    leverage: int = Field(default=1, ge=1, le=20)

class MexcLiveEntryRequest(BaseModel):
    symbol: str = Field(min_length=5, max_length=12)
    timeframe: str = Field(default="1h", min_length=2, max_length=3)
    risk_percent: float = Field(default=0.5, gt=0, le=1)
    leverage: int = Field(default=1, ge=1, le=20)


class MexcLiveAuthorizationRequest(BaseModel):
    enabled: bool
    acknowledge_risk: bool = False
    max_daily_loss_percent: float = Field(default=2.0, ge=1, le=10)


class CTraderAccountSelection(BaseModel):
    account_id: str = Field(min_length=1, max_length=32)


class CTraderDemoOrderRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=32)
    side: str
    lots: float = Field(gt=0, le=0.01)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)


class CTraderLiveOrderRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=32)
    side: str
    lots: float = Field(gt=0, le=0.01)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)


class CTraderLiveAuthorizationRequest(BaseModel):
    enabled: bool
    acknowledge_risk: bool = False


class CTraderDemoProtectionRequest(BaseModel):
    position_id: str = Field(min_length=1, max_length=32)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)


class CTraderDemoCloseRequest(BaseModel):
    position_id: str = Field(min_length=1, max_length=32)


class CTraderRiskSettingsRequest(BaseModel):
    max_daily_loss_pct: float = Field(ge=1, le=10)
    max_lots: float = Field(ge=0.001, le=0.01)
    max_open_positions: int = Field(ge=1, le=3)


class CTraderEmergencyStopRequest(BaseModel):
    enabled: bool

class CTraderDemoAuthorizationRequest(BaseModel):
    enabled: bool
    acknowledge_risk: bool = False


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


def _mexc_live_permission(customer_id: str) -> dict:
    metadata = mexc_credential_metadata(customer_id)
    return get_mexc_live_authorization(customer_id, metadata.get("credential_fingerprint"))


def _session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=7 * 24 * 60 * 60,
        httponly=True, secure=os.getenv("ENVIRONMENT", "development").lower() == "production",
        samesite="lax", path="/",
    )


async def _mexc_auto_monitor_loop():
    """Execute at most one high-confidence entry per completed candle and customer."""
    while True:
        try:
            for strategy in list_active_mexc_auto_strategies():
                customer_id = strategy["customer_id"]
                external_oid = None
                try:
                    if not subscription_for_customer(customer_id).get("active"):
                        stop_mexc_auto_strategy(customer_id)
                        continue
                    credentials = load_mexc_credentials(customer_id)
                    if not credentials:
                        stop_mexc_auto_strategy(customer_id)
                        continue
                    live_permission = _mexc_live_permission(customer_id)
                    if not live_permission["authorized"]:
                        stop_mexc_auto_strategy(customer_id)
                        set_mexc_auto_strategy_error(customer_id, "Live permission missing, revoked, or invalidated by API-key change")
                        continue
                    client = MexcFuturesClient(credentials["api_key"], credentials["api_secret"])
                    account = await client.verify_account()
                    usdt = next((a for a in account["assets"] if a["currency"] == "USDT"), None)
                    balance = float(usdt["available_balance"]) if usdt else 0.0
                    equity = float(usdt["equity"]) if usdt else 0.0
                    if balance <= 0 or equity <= 0:
                        set_mexc_auto_strategy_error(customer_id, "No available USDT futures balance")
                        continue
                    daily_guard = mexc_daily_loss_guard(customer_id, equity, live_permission["max_daily_loss_percent"])
                    if not daily_guard["allowed"]:
                        continue
                    symbol = strategy["symbol"]
                    if await client.get_open_positions(symbol):
                        set_mexc_auto_strategy_error(customer_id, None)
                        continue
                    if await client.get_open_orders(symbol):
                        set_mexc_auto_strategy_error(customer_id, "Existing pending MEXC order detected; waiting for exchange reconciliation")
                        continue
                    candles = await get_candles(symbol, strategy["timeframe"], 100)
                    completed = candles[:-1]
                    if len(completed) < 50:
                        continue
                    analysis = analyze_candles(completed, strategy["timeframe"])
                    if str(analysis.get("signal_strength", "")).lower() != "high":
                        continue
                    direction = analysis.get("direction")
                    if direction not in {"CALL", "PUT"}:
                        continue
                    candle_time = int(completed[-1]["time"])
                    quotes = await get_market_overview()
                    quote = next((x for x in quotes if x["symbol"] == symbol), None)
                    if not quote or float(quote["price"]) <= 0:
                        continue
                    analysis["last_close"] = float(quote["price"])
                    analysis["trade_bias"] = "LONG" if direction == "CALL" else "SHORT"
                    risk = float(strategy["risk_percent"])
                    leverage = int(strategy["leverage"])
                    plan = build_paper_trade_plan(analysis, account_balance=balance,
                                                  risk_percent=risk, leverage=leverage)
                    if plan is None:
                        continue
                    contract = await client.get_contract(symbol)
                    sizing = contracts_for_risk(
                        symbol=symbol, entry_price=plan["entry_price"],
                        stop_loss=plan["stop_loss"], account_balance=balance,
                        risk_percent=risk, contract=contract, leverage=leverage)
                    external_oid = hashlib.sha256(
                        f"qai-auto:{customer_id}:{symbol}:{candle_time}".encode()
                    ).hexdigest()[:32]
                    if not reserve_mexc_auto_order(customer_id, symbol, candle_time, external_oid):
                        continue
                    try:
                        order = await client.place_market_order(
                            symbol=symbol, side=plan["side"], volume=sizing["contracts"],
                            leverage=leverage, stop_loss=plan["stop_loss"],
                            take_profit=plan["take_profit"], external_oid=external_oid)
                        update_mexc_auto_order(external_oid, "submitted", order["order_id"])
                        set_mexc_auto_strategy_error(customer_id, None)
                        logger.info("MEXC auto order submitted for customer %s symbol %s order %s",
                                    customer_id, symbol, order["order_id"])
                    except Exception:
                        update_mexc_auto_order(external_oid, "unknown")
                        set_mexc_auto_strategy_error(
                            customer_id, "Order result uncertain; duplicate entry blocked pending exchange reconciliation")
                        logger.exception("MEXC order result uncertain for customer %s", customer_id)
                except Exception as exc:
                    set_mexc_auto_strategy_error(customer_id, str(exc)[:240])
                    logger.warning("MEXC auto strategy failed for customer %s: %s",
                                   customer_id, str(exc)[:180])
        except Exception:
            logger.exception("MEXC auto-trader monitor loop failed")
        await asyncio.sleep(20)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_auth_db()
    init_subscription_db()
    init_signal_history_db()
    init_paper_db()
    init_virtual_db()
    init_mexc_vault_db()
    init_mexc_auto_db()
    init_mexc_live_permissions_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    init_ctrader_risk_db()
    init_ctrader_permissions_db()
    mexc_auto_task = None
    mexc_auto_mode = os.getenv("QUANTUM_MEXC_AUTO_EXECUTION_MODE", "inline").strip().lower()
    if mexc_auto_mode not in {"inline", "worker"}:
        raise RuntimeError("QUANTUM_MEXC_AUTO_EXECUTION_MODE must be inline or worker")
    if (
        mexc_auto_mode == "inline"
        and os.getenv("QUANTUM_MEXC_LIVE_TRADING_ENABLED", "").strip().lower() == "true"
    ):
        mexc_auto_task = asyncio.create_task(_mexc_auto_monitor_loop())
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
        if mexc_auto_task is not None:
            mexc_auto_task.cancel()
            try:
                await mexc_auto_task
            except asyncio.CancelledError:
                pass
        if bot is not None:
            if bot.running:
                await bot.stop()
            await bot.shutdown()


app = FastAPI(title="QUANTUM AI", version="0.5.0", description="Mobile trading workspace with customer identity foundation", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

class SignalResultRequest(BaseModel):
    result: str = Field(pattern="^(WIN|LOSS|DRAW)$")


class AdsDiagnosticEvent(BaseModel):
    event: str = Field(min_length=3, max_length=40)
    sdk_loaded: bool = False
    init_available: bool = False
    custom_element_defined: bool = False
    banner_has_content: bool = False
    adsense_configured: bool = False
    banner_height: float = Field(default=0, ge=0, le=1000)


@app.get("/api/ads/config")
async def public_ads_config():
    """Expose only public AdSense placement identifiers; never private ad-network credentials."""
    client_id = os.getenv("GOOGLE_ADSENSE_CLIENT_ID", "").strip()
    slot_id = os.getenv("GOOGLE_ADSENSE_BOTTOM_SLOT_ID", "").strip()
    valid_client = client_id.startswith("ca-pub-") and client_id[7:].isdigit()
    valid_slot = slot_id.isdigit()
    return {
        "enabled": bool(valid_client and valid_slot),
        "client_id": client_id if valid_client and valid_slot else "",
        "slot_id": slot_id if valid_client and valid_slot else "",
    }


@app.post("/api/ads/diagnostics")
async def ads_diagnostics(payload: AdsDiagnosticEvent):
    allowed_events = {
        "sdk_load_started", "sdk_load_failed", "sdk_loaded", "sdk_api_missing",
        "sdk_init_failed", "sdk_initialized", "banner_defined", "banner_rendered",
        "banner_empty", "adsense_configured", "adsense_disabled",
        "adsense_load_failed", "adsense_load_started", "frontend_error",
        "frontend_rejection",
    }
    if payload.event not in allowed_events:
        raise HTTPException(status_code=400, detail="Unsupported ad diagnostic event")
    logger.info(
        "ADS_DIAGNOSTIC event=%s sdk_loaded=%s init_available=%s "
        "custom_element_defined=%s banner_has_content=%s adsense_configured=%s banner_height=%.1f",
        payload.event, payload.sdk_loaded, payload.init_available,
        payload.custom_element_defined, payload.banner_has_content,
        payload.adsense_configured, payload.banner_height,
    )
    return {"ok": True}


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
        "price_usd": 30,
        "duration_days": 30,
        "payment_currency": "usdttrc20",
        "payment_configured": payment_configured(),
    }


@app.get("/api/subscription/order")
async def get_subscription_payment_order(request: Request):
    """Return only the signed-in customer's current pending checkout."""
    init_auth_db()
    init_subscription_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"order": pending_order_for_customer(customer["id"])}


@app.post("/api/subscription/checkout")
async def create_subscription_checkout(request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_subscription_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if subscription_for_customer(customer["id"]).get("active"):
        raise HTTPException(status_code=409, detail="Your membership is already active")
    if not payment_configured():
        raise HTTPException(status_code=503, detail="Payment setup is pending durable database and NOWPayments credentials")
    pending = pending_order_for_customer(customer["id"])
    if pending and pending.get("payment_id"):
        return pending
    api_key = os.getenv("NOWPAYMENTS_API_KEY", "").strip()
    public_url = os.getenv("QUANTUM_PUBLIC_URL", "").strip().rstrip("/")
    order_id = create_subscription_order(customer["id"])
    body = {
        "price_amount": "30.00",
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
            if response.is_error:
                # Safe diagnostic: provider response only; never log the API key.
                logger.warning("NOWPayments checkout rejected: HTTP %s; response=%s", response.status_code, response.text[:400])
                response.raise_for_status()
            payment = response.json()
        return attach_payment(order_id, payment)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning("NOWPayments checkout creation failed: %s", str(exc)[:180])
        raise HTTPException(status_code=502, detail="NOWPayments could not create the checkout. No subscription was activated.")


@app.post("/api/subscription/refresh")
async def refresh_subscription_payment(request: Request):
    """Reconcile a pending customer payment directly with NOWPayments if its IPN is delayed."""
    _check_same_origin(request)
    init_auth_db()
    init_subscription_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not payment_configured():
        raise HTTPException(status_code=503, detail="Payment setup is not configured")
    pending = pending_order_for_customer(customer["id"])
    if not pending or not pending.get("payment_id"):
        return {"order": None, "subscription": subscription_for_customer(customer["id"])}
    api_key = os.getenv("NOWPAYMENTS_API_KEY", "").strip()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://api.nowpayments.io/v1/payment/" + str(pending["payment_id"]),
                headers={"x-api-key": api_key},
            )
            response.raise_for_status()
            payment = response.json()
        if (str(payment.get("payment_id") or "") != str(pending["payment_id"])
                or str(payment.get("order_id") or "") != str(pending["order_id"])):
            raise HTTPException(status_code=502, detail="Payment provider returned a mismatched payment record")
        status = str(payment.get("payment_status") or "").lower()
        if not status:
            raise HTTPException(status_code=502, detail="Payment provider returned no payment status")
        if status == "finished":
            result = apply_finished_payment(payment)
            record_referral_paid_order(pending["order_id"])
        else:
            update_payment_status(pending["order_id"], pending["payment_id"], status)
            result = {"accepted": True, "activated": False, "status": status}
        return {
            "order": pending_order_for_customer(customer["id"]),
            "payment": {"payment_status": status, "pay_currency": payment.get("pay_currency")},
            "result": result,
            "subscription": subscription_for_customer(customer["id"]),
        }
    except httpx.HTTPError as exc:
        logger.warning("NOWPayments status refresh failed: %s", str(exc)[:180])
        raise HTTPException(status_code=502, detail="Could not verify payment status with NOWPayments. Try again shortly.")


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
        if str(payload.get("payment_status") or "").lower() == "finished":
            record_referral_paid_order(payload.get("order_id"))
        return {"ok": True, **result}
    except ValueError as exc:
        logger.warning("NOWPayments notification rejected: %s", str(exc)[:180])
        raise HTTPException(status_code=400, detail="Payment notification did not match a valid subscription order")


@app.get("/api/brokers")
async def brokers():
    """Return verified implementation scope; this endpoint never claims a live account."""
    return broker_capabilities()


@app.get("/api/connections/ctrader/status")
async def ctrader_connection_status(request: Request):
    init_auth_db()
    init_ctrader_oauth_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {**ctrader_authorization_status(customer["id"]), "account_snapshot": get_ctrader_snapshot(customer["id"]), "live_account_snapshot": get_ctrader_live_snapshot(customer["id"])}


@app.post("/api/connections/ctrader/start")
async def start_ctrader_authorization(request: Request, response: Response):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        state, authorization_url = create_ctrader_authorization(customer["id"], "trading")
    except CTraderOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    response.set_cookie(
        CTRADER_OAUTH_COOKIE, state, max_age=600, httponly=True,
        secure=os.getenv("ENVIRONMENT", "development").lower() == "production",
        samesite="lax", path="/api/connections/ctrader",
    )
    return {"authorization_url": authorization_url, "expires_in": 600}


@app.get("/api/connections/ctrader/callback")
async def ctrader_authorization_callback(request: Request, code: str = "", error: str = ""):
    state = request.cookies.get(CTRADER_OAUTH_COOKIE, "")
    try:
        if error:
            raise CTraderOAuthError("cTrader authorization was cancelled or declined")
        if not state:
            raise CTraderOAuthError("The secure connection session expired. Please try again.")
        await complete_ctrader_authorization(code, state)
        destination = "/?ctrader=authorized"
    except CTraderOAuthError:
        logger.warning("cTrader OAuth callback could not be completed")
        destination = "/?ctrader=error"
    response = RedirectResponse(destination, status_code=303)
    response.delete_cookie(CTRADER_OAUTH_COOKIE, path="/api/connections/ctrader")
    return response


@app.get("/api/connections/ctrader/accounts")
async def ctrader_demo_accounts(request: Request):
    init_auth_db()
    init_ctrader_oauth_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not ctrader_authorization_status(customer["id"]).get("authorized"):
        raise HTTPException(status_code=409, detail="Authorize cTrader before discovering accounts")
    try:
        accounts = await discover_ctrader_demo_accounts(customer["id"])
        return {"accounts": accounts, "environment": "demo", "demo_execution_available": True, "customer_permission_required": True, "real_execution_enabled": False}
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/api/connections/ctrader/select")
async def select_ctrader_demo_account(payload: CTraderAccountSelection, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not ctrader_authorization_status(customer["id"]).get("authorized"):
        raise HTTPException(status_code=409, detail="Authorize cTrader before selecting an account")
    try:
        return await sync_ctrader_demo_account(customer["id"], payload.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/api/connections/ctrader/snapshot")
async def refresh_ctrader_demo_snapshot(request: Request):
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    snapshot = get_ctrader_snapshot(customer["id"])
    if not snapshot:
        raise HTTPException(status_code=404, detail="Select an IC Markets demo account first")
    try:
        return await sync_ctrader_demo_account(customer["id"], snapshot["account_id"])
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/api/connections/ctrader/markets")
async def ctrader_demo_markets(request: Request):
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return {"markets": await discover_ctrader_demo_symbols(customer["id"]),
                "source": "IC Markets cTrader demo market data", "demo_execution_available": True, "customer_permission_required": True, "real_execution_enabled": False}
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/api/connections/ctrader/candles/{symbol}")
async def ctrader_demo_candles(
    symbol: str,
    request: Request,
    timeframe: str = Query(default="15m"),
    count: int = Query(default=80, ge=20, le=200),
):
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    snapshot = get_ctrader_snapshot(customer["id"])
    if not snapshot or snapshot.get("environment") != "demo":
        raise HTTPException(status_code=409, detail="Connect and sync your IC Markets demo account to use broker candles")
    try:
        return await get_ctrader_demo_candles(customer["id"], symbol, timeframe, count)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/api/connections/ctrader/demo/history")
async def ctrader_demo_trade_history(
    request: Request,
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=100, ge=1, le=100),
):
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    snapshot = get_ctrader_snapshot(customer["id"])
    if not snapshot or snapshot.get("environment") != "demo":
        raise HTTPException(status_code=409, detail="Connect and sync your IC Markets demo account first")
    try:
        return await get_ctrader_demo_history(customer["id"], days, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/api/connections/ctrader/demo/orders")
async def open_ctrader_demo_order(payload: CTraderDemoOrderRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not ctrader_authorization_status(customer["id"]).get("authorized"):
        raise HTTPException(status_code=409, detail="Authorize cTrader and select a demo account first")
    try:
        return await open_ctrader_demo_trade(
            customer["id"], payload.symbol, payload.side, payload.lots,
            payload.stop_loss, payload.take_profit,
        )
    except CTraderPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except CTraderRiskBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.patch("/api/connections/ctrader/demo/positions/protection")
async def amend_ctrader_demo_protection(payload: CTraderDemoProtectionRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await amend_ctrader_demo_position(
            customer["id"], payload.position_id, payload.stop_loss, payload.take_profit
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/api/connections/ctrader/demo/positions/close")
async def close_ctrader_demo_position(payload: CTraderDemoCloseRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await execute_ctrader_demo_close(customer["id"], payload.position_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))




@app.get("/api/connections/ctrader/live/accounts")
async def ctrader_live_accounts(request: Request):
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not ctrader_authorization_status(customer["id"]).get("authorized"):
        raise HTTPException(status_code=409, detail="Authorize cTrader before discovering live accounts")
    try:
        accounts = await discover_ctrader_live_accounts(customer["id"])
        return {"accounts": accounts, "environment": "live",
                "live_session_available": True, "live_execution_enabled":
                os.getenv("QUANTUM_CTRADER_LIVE_TRADING_ENABLED", "").strip().lower() == "true"}
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/connections/ctrader/live/markets")
async def ctrader_live_markets(request: Request):
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return {"markets": await discover_ctrader_live_symbols(customer["id"]),
                "source": "IC Markets cTrader live symbols",
                "environment": "live"}
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/connections/ctrader/live/select")
async def select_ctrader_live_account(payload: CTraderAccountSelection, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not ctrader_authorization_status(customer["id"]).get("authorized"):
        raise HTTPException(status_code=409, detail="Authorize cTrader before selecting a live account")
    try:
        return await sync_ctrader_live_account(customer["id"], payload.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/connections/ctrader/live/snapshot")
async def refresh_ctrader_live_snapshot(request: Request):
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    snapshot = get_ctrader_live_snapshot(customer["id"])
    if not snapshot:
        raise HTTPException(status_code=404, detail="Select your IC Markets live account first")
    try:
        return await sync_ctrader_live_account(customer["id"], snapshot["account_id"])
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/connections/ctrader/live/authorization")
async def get_ctrader_live_authorization(request: Request):
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    init_ctrader_permissions_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    snapshot = get_ctrader_live_snapshot(customer["id"])
    account_id = snapshot.get("account_id") if snapshot else None
    permission = get_ctrader_permission(customer["id"], account_id)
    return {**permission, "environment": "live",
            "customer_authorized": bool(ctrader_authorization_status(customer["id"]).get("authorized")),
            "account_selected": bool(account_id),
            "live_session_enabled": os.getenv("QUANTUM_CTRADER_LIVE_SESSION_ENABLED", "").strip().lower() == "true",
            "live_execution_enabled": os.getenv("QUANTUM_CTRADER_LIVE_TRADING_ENABLED", "").strip().lower() == "true"}


@app.put("/api/connections/ctrader/live/authorization")
async def update_ctrader_live_authorization(payload: CTraderLiveAuthorizationRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    init_ctrader_permissions_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    snapshot = get_ctrader_live_snapshot(customer["id"])
    if not snapshot:
        raise HTTPException(status_code=409, detail="Connect and sync your own verified IC Markets live account first")
    if payload.enabled and os.getenv("QUANTUM_CTRADER_LIVE_TRADING_ENABLED", "").strip().lower() != "true":
        raise HTTPException(status_code=503, detail="Live execution is not enabled by the platform yet")
    try:
        permission = set_ctrader_live_permission(customer["id"], snapshot["account_id"],
                                                 payload.enabled, payload.acknowledge_risk)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {**permission, "environment": "live", "customer_authorized": True,
            "account_selected": True,
            "live_execution_enabled": os.getenv("QUANTUM_CTRADER_LIVE_TRADING_ENABLED", "").strip().lower() == "true"}


@app.post("/api/connections/ctrader/live/orders")
async def open_ctrader_live_order(payload: CTraderLiveOrderRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not ctrader_authorization_status(customer["id"]).get("authorized"):
        raise HTTPException(status_code=409, detail="Authorize cTrader and select your live account first")
    try:
        return await open_ctrader_live_trade(
            customer["id"], payload.symbol, payload.side, payload.lots,
            payload.stop_loss, payload.take_profit)
    except CTraderPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except CTraderRiskBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.patch("/api/connections/ctrader/live/positions/protection")
async def amend_ctrader_live_protection(payload: CTraderDemoProtectionRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await amend_ctrader_live_position(
            customer["id"], payload.position_id, payload.stop_loss, payload.take_profit)
    except CTraderPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/connections/ctrader/live/positions/close")
async def close_ctrader_live_position(payload: CTraderDemoCloseRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await execute_ctrader_live_close(customer["id"], payload.position_id)
    except CTraderPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CTraderOpenAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/connections/ctrader/demo/authorization")
async def get_ctrader_demo_authorization(request: Request):
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    init_ctrader_permissions_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    snapshot = get_ctrader_snapshot(customer["id"])
    account_id = snapshot.get("account_id") if snapshot and snapshot.get("environment") == "demo" else None
    return {**get_ctrader_permission(customer["id"], account_id),
            "customer_authorized": bool(ctrader_authorization_status(customer["id"]).get("authorized")),
            "account_selected": bool(account_id), "live_trading_available": False}


@app.put("/api/connections/ctrader/demo/authorization")
async def update_ctrader_demo_authorization(payload: CTraderDemoAuthorizationRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    init_ctrader_sync_db()
    init_ctrader_permissions_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    snapshot = get_ctrader_snapshot(customer["id"])
    if not snapshot or snapshot.get("environment") != "demo":
        raise HTTPException(status_code=409, detail="Connect and sync your own IC Markets demo account first")
    try:
        permission = set_ctrader_demo_permission(customer["id"], snapshot["account_id"],
                                                 payload.enabled, payload.acknowledge_risk)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {**permission, "customer_authorized": True, "account_selected": True,
            "live_trading_available": False}


@app.get("/api/connections/ctrader/demo/risk")
async def get_ctrader_demo_risk(request: Request):
    init_auth_db()
    init_ctrader_risk_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    snapshot = get_ctrader_snapshot(customer["id"])
    return get_ctrader_risk_status(customer["id"], snapshot.get("account_id") if snapshot else None)


@app.put("/api/connections/ctrader/demo/risk")
async def update_ctrader_demo_risk(payload: CTraderRiskSettingsRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_risk_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        update_ctrader_risk_settings(customer["id"], payload.max_daily_loss_pct,
                                     payload.max_lots, payload.max_open_positions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    snapshot = get_ctrader_snapshot(customer["id"])
    return get_ctrader_risk_status(customer["id"], snapshot.get("account_id") if snapshot else None)


@app.post("/api/connections/ctrader/demo/risk/emergency-stop")
async def set_ctrader_demo_emergency_stop(payload: CTraderEmergencyStopRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_risk_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    set_ctrader_emergency_stop(customer["id"], payload.enabled)
    snapshot = get_ctrader_snapshot(customer["id"])
    return get_ctrader_risk_status(customer["id"], snapshot.get("account_id") if snapshot else None)


@app.delete("/api/connections/ctrader")
async def disconnect_ctrader_account(request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_ctrader_oauth_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    clear_ctrader_snapshot(customer["id"])
    return {"deleted": delete_ctrader_authorization(customer["id"])}


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
        "customer_auth": "available",
        "credential_storage_ready": _persistent_credentials_ready(),
        "ctrader_oauth_configured": ctrader_oauth_configured(),
        "ctrader_account_execution_enabled": False,
        "ctrader_demo_execution_available": True,
        "ctrader_live_execution_enabled": False,
        "mexc_futures_execution_enabled": os.getenv("QUANTUM_MEXC_LIVE_TRADING_ENABLED", "").strip().lower() == "true",
        "mexc_auto_trader_monitor_running": os.getenv("QUANTUM_MEXC_LIVE_TRADING_ENABLED", "").strip().lower() == "true",
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
    init_referral_db()
    attach_referral_signup(customer["id"], payload.referral_code)
    token = create_session(customer["id"])
    _session_cookie(response, token)
    return {"customer": customer, "authenticated": True}


@app.get("/api/referrals")
async def get_referral_dashboard(request: Request):
    init_auth_db()
    init_subscription_db()
    init_referral_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return referral_dashboard(customer["id"], str(request.base_url).rstrip("/"))


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


@app.get("/api/connections/mexc")
async def mexc_connection(request: Request):
    init_auth_db()
    init_mexc_vault_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    metadata = mexc_credential_metadata(customer["id"])
    metadata.pop("credential_fingerprint", None)
    return metadata


@app.post("/api/connections/mexc/verify")
async def verify_and_save_mexc_connection(payload: MexcCredentials, request: Request):
    """Verify MEXC USD-M futures account access using a signed read-only request.

    This endpoint never places or cancels orders. Customers should use an API key
    with futures account/trade-reading permission and IP restrictions.
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
    except MexcFuturesError as exc:
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


@app.get("/api/mexc/futures/positions")
async def mexc_futures_positions(request: Request):
    init_auth_db()
    init_mexc_vault_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    credentials = load_mexc_credentials(customer["id"])
    if not credentials:
        raise HTTPException(status_code=409, detail="MEXC Futures account is not connected")
    try:
        client = MexcFuturesClient(credentials["api_key"], credentials["api_secret"])
        account = await client.verify_account()
        positions = await client.get_open_positions()
        orders = await client.get_open_orders()
        return {"broker": "mexc", "market": "usdt_margined_perpetual_futures",
                "assets": account["assets"], "positions": positions, "open_orders": orders}
    except MexcFuturesError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/api/mexc/futures/auto-entry")
async def execute_mexc_futures_signal(
    payload: MexcLiveEntryRequest,
    request: Request,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
):
    """Execute one customer-requested MEXC USD-M signal with exchange-side TP/SL."""
    _check_same_origin(request)
    if os.getenv("QUANTUM_MEXC_LIVE_TRADING_ENABLED", "").strip().lower() != "true":
        raise HTTPException(status_code=503, detail="MEXC live futures execution is disabled by the server safety switch")
    if not _persistent_credentials_ready():
        raise HTTPException(status_code=503, detail="Durable encrypted credential storage is required")
    init_auth_db()
    init_subscription_db()
    init_mexc_vault_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not subscription_for_customer(customer["id"]).get("active"):
        raise HTTPException(status_code=403, detail="An active QUANTUM AI membership is required")
    symbol = payload.symbol.upper()
    if symbol not in CRYPTO_FUTURES:
        raise HTTPException(status_code=400, detail="Unsupported MEXC USD-M perpetual market")
    if payload.timeframe not in {"1h", "4h", "1d"}:
        raise HTTPException(status_code=400, detail="Timeframe must be 1h, 4h or 1d")
    if not idempotency_key or len(idempotency_key) > 100:
        raise HTTPException(status_code=400, detail="A valid Idempotency-Key header is required")
    credentials = load_mexc_credentials(customer["id"])
    if not credentials:
        raise HTTPException(status_code=409, detail="Connect and verify your own MEXC Futures API key first")
    try:
        live_permission = require_mexc_live_authorization(customer["id"], str(mexc_credential_metadata(customer["id"]).get("credential_fingerprint") or ""))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    try:
        client = MexcFuturesClient(credentials["api_key"], credentials["api_secret"])
        account = await client.verify_account()
        usdt = next((a for a in account["assets"] if a["currency"] == "USDT"), None)
        if not usdt:
            raise HTTPException(status_code=409, detail="No USDT futures wallet was returned by MEXC")
        available = float(usdt["available_balance"])
        if available <= 0:
            raise HTTPException(status_code=409, detail="MEXC Futures available USDT balance is zero")
        equity = float(usdt.get("equity") or available)
        if equity <= 0:
            raise HTTPException(status_code=409, detail="MEXC Futures account equity is unavailable")
        daily_guard = mexc_daily_loss_guard(customer["id"], equity, live_permission["max_daily_loss_percent"])
        if not daily_guard["allowed"]:
            raise HTTPException(status_code=409, detail="Your configured MEXC daily loss limit has been reached")
        positions = await client.get_open_positions(symbol)
        if positions:
            raise HTTPException(status_code=409, detail="An open position already exists for this customer and symbol")
        candles_data = await get_candles(symbol, payload.timeframe, 100)
        analysis = analyze_candles(candles_data[:-1], payload.timeframe)
        quotes = await get_market_overview()
        quote = next((item for item in quotes if item["symbol"] == symbol), None)
        if not quote or float(quote["price"]) <= 0:
            raise HTTPException(status_code=503, detail="No current MEXC futures quote; no order was sent")
        analysis["last_close"] = float(quote["price"])
        analysis["trade_bias"] = ("LONG" if analysis["direction"] == "CALL"
                                  else "SHORT" if analysis["direction"] == "PUT" else "WAIT")
        plan = build_paper_trade_plan(
            analysis, account_balance=available,
            risk_percent=payload.risk_percent, leverage=payload.leverage,
        )
        if plan is None:
            return {"created": False, "reason": "Signal is WAIT or below the high-confidence filter",
                    "analysis": analysis, "mode": "live", "order_sent": False}
        contract = await client.get_contract(symbol)
        sizing = contracts_for_risk(
            symbol=symbol, entry_price=plan["entry_price"], stop_loss=plan["stop_loss"],
            account_balance=available, risk_percent=payload.risk_percent,
            contract=contract, leverage=payload.leverage,
        )
        external_oid = hashlib.sha256(
            (customer["id"] + ":" + idempotency_key).encode()
        ).hexdigest()[:32]
        order = await client.place_market_order(
            symbol=symbol, side=plan["side"], volume=sizing["contracts"],
            leverage=payload.leverage, stop_loss=plan["stop_loss"],
            take_profit=plan["take_profit"], external_oid=external_oid,
        )
        return {"created": True, "mode": "live", "broker": "mexc",
                "market": "usdt_margined_perpetual_futures", "order": order,
                "sizing": sizing, "analysis": analysis,
                "risk_controls": {"risk_percent": payload.risk_percent,
                                  "max_notional_usdt": 500, "max_leverage": 20,
                                  "isolated_margin": True, "exchange_tp_sl_attached": True}}
    except MexcFuturesError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="MEXC market data unavailable; no order was sent")



@app.get("/api/mexc/futures/live-authorization")
async def mexc_live_authorization_status(request: Request):
    init_auth_db()
    init_mexc_vault_db()
    init_mexc_live_permissions_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    metadata = mexc_credential_metadata(customer["id"])
    return {
        **get_mexc_live_authorization(customer["id"], metadata.get("credential_fingerprint")),
        "credentials_connected": bool(metadata.get("connected")),
        "server_kill_switch_enabled": os.getenv("QUANTUM_MEXC_LIVE_TRADING_ENABLED", "").strip().lower() == "true",
        "mode": "live",
    }


@app.put("/api/mexc/futures/live-authorization")
async def update_mexc_live_authorization(payload: MexcLiveAuthorizationRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_subscription_db()
    init_mexc_vault_db()
    init_mexc_live_permissions_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if payload.enabled:
        if not subscription_for_customer(customer["id"]).get("active"):
            raise HTTPException(status_code=403, detail="An active QUANTUM AI membership is required")
        if not _persistent_credentials_ready():
            raise HTTPException(status_code=503, detail="Durable encrypted credential storage is required")
        metadata = mexc_credential_metadata(customer["id"])
        credentials = load_mexc_credentials(customer["id"])
        if not credentials or not metadata.get("credential_fingerprint"):
            raise HTTPException(status_code=409, detail="Connect and verify your own MEXC USD-M Futures API key first")
        try:
            # Read-only verification before recording consent; no order is placed here.
            await MexcFuturesClient(credentials["api_key"], credentials["api_secret"]).verify_account()
            permission = set_mexc_live_authorization(
                customer["id"], str(metadata["credential_fingerprint"]), True,
                payload.acknowledge_risk, payload.max_daily_loss_percent,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except MexcFuturesError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        return {
            **permission, "credentials_connected": True,
            "server_kill_switch_enabled": os.getenv("QUANTUM_MEXC_LIVE_TRADING_ENABLED", "").strip().lower() == "true",
            "note": "Customer live consent saved. Automatic order execution remains blocked until the server kill switch is deliberately enabled after validation. Use an API key with futures trade/read access and withdrawals disabled.",
        }
    permission = set_mexc_live_authorization(
        customer["id"], 0, False, False, payload.max_daily_loss_percent,
    )
    stop_mexc_auto_strategy(customer["id"])
    return {**permission, "credentials_connected": bool(mexc_credential_metadata(customer["id"]).get("connected")),
            "note": "Live permission revoked and new automatic entries stopped. Existing exchange positions are not automatically closed."}


@app.post("/api/mexc/futures/live/emergency-stop")
async def mexc_live_emergency_stop(request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_mexc_auto_db()
    init_mexc_live_permissions_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    permission = activate_mexc_emergency_stop(customer["id"])
    strategy = stop_mexc_auto_strategy(customer["id"])
    return {"live_authorization": permission, "strategy": strategy,
            "note": "New automatic entries are blocked. Existing exchange positions remain open; their exchange-side protection remains in place."}


@app.get("/api/mexc/futures/auto")
async def mexc_auto_status(request: Request):
    init_auth_db()
    init_mexc_vault_db()
    init_mexc_auto_db()
    init_mexc_live_permissions_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"strategy": get_mexc_auto_strategy(customer["id"]),
            "live_authorization": _mexc_live_permission(customer["id"]),
            "execution_enabled": os.getenv("QUANTUM_MEXC_LIVE_TRADING_ENABLED", "").strip().lower() == "true"}


@app.post("/api/mexc/futures/auto/start")
async def mexc_auto_start(payload: MexcLiveEntryRequest, request: Request):
    _check_same_origin(request)
    if os.getenv("QUANTUM_MEXC_LIVE_TRADING_ENABLED", "").strip().lower() != "true":
        raise HTTPException(status_code=503, detail="MEXC live futures execution is disabled by the server safety switch")
    if not _persistent_credentials_ready():
        raise HTTPException(status_code=503, detail="Durable encrypted credential storage is required")
    init_auth_db()
    init_subscription_db()
    init_mexc_vault_db()
    init_mexc_auto_db()
    init_mexc_live_permissions_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not subscription_for_customer(customer["id"]).get("active"):
        raise HTTPException(status_code=403, detail="An active QUANTUM AI membership is required")
    credentials = load_mexc_credentials(customer["id"])
    if not credentials:
        raise HTTPException(status_code=409, detail="Connect and verify your own MEXC Futures API key first")
    try:
        require_mexc_live_authorization(customer["id"], str(mexc_credential_metadata(customer["id"]).get("credential_fingerprint") or ""))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if payload.symbol.upper() not in CRYPTO_FUTURES or payload.timeframe not in {"1h", "4h", "1d"}:
        raise HTTPException(status_code=400, detail="Unsupported futures symbol or timeframe")
    try:
        client = MexcFuturesClient(credentials["api_key"], credentials["api_secret"])
        await client.verify_account()
        await client.get_contract(payload.symbol.upper())
        return {"strategy": start_mexc_auto_strategy(customer["id"], payload.symbol,
                payload.timeframe, payload.risk_percent, payload.leverage),
                "execution_enabled": True, "mode": "live"}
    except (MexcFuturesError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/api/mexc/futures/auto/stop")
async def mexc_auto_stop(request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_mexc_auto_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"strategy": stop_mexc_auto_strategy(customer["id"]),
            "note": "New entries stopped. Existing exchange positions remain open with their attached TP/SL orders."}


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


@app.get("/api/market-universe")
async def market_universe():
    """Return the agreed analysis watchlists; stablecoin assets are excluded."""
    return {
        "forex": FOREX_PAIRS,
        "binary_options": BINARY_PAIRS,
        "crypto_futures": CRYPTO_FUTURES,
        "crypto_quote_currency": "USDT",
        "crypto_source": "MEXC USDT-margined perpetual futures public market data",
        "execution_enabled": False,
    }


@app.get("/api/markets")
async def markets():
    try:
        return {"source": "MEXC USDT-margined perpetual futures public market data", "markets": await get_market_overview()}
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Public market data is temporarily unavailable")


@app.get("/api/orderbook/{symbol}")
async def binance_order_book(symbol: str, limit: int = Query(default=10, ge=5, le=20)):
    """Read-only public Binance USD-M futures order book depth."""
    try:
        return {"source": "Binance USD-M futures public depth", **await get_order_book(symbol, limit)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Binance order book is temporarily unavailable")


@app.get("/api/candles/{symbol}")
async def candles(symbol: str, interval: str = Query(default="1h"), limit: int = Query(default=72, ge=20, le=200)):
    try:
        return {"symbol": symbol.upper(), "interval": interval, "source": "MEXC USDT-margined perpetual futures public candles", "candles": await get_candles(symbol, interval, limit)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Public candle data is temporarily unavailable")


@app.get("/api/signals/crypto/{symbol}")
async def crypto_signal(
    symbol: str,
    request: Request,
    source: str = Query(default="mexc"),
    timeframe: str = Query(default="1h"),
):
    """Calculate a read-only indicator signal from public crypto candles."""
    if timeframe not in {"1h", "4h", "1d"}:
        raise HTTPException(status_code=400, detail="Crypto signal timeframe must be 1h, 4h, or 1d")
    if source not in {"mexc", "binance"}:
        raise HTTPException(status_code=400, detail="Crypto analysis currently uses the MEXC perpetual futures public feed")
    if symbol.upper() not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail="Unsupported crypto market")
    try:
        candle_data = await get_candles(symbol, timeframe, 100)
        result = analyze_candles(candle_data, timeframe)
        result.update({"symbol": symbol.upper(), "category": "crypto",
                       "trade_bias": "LONG" if result["direction"] == "CALL" else "SHORT" if result["direction"] == "PUT" else "WAIT",
                       "source": "MEXC USDT-margined perpetual futures public candles",
                       "execution_enabled": False})
        customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
        if customer:
            result["history_id"] = record_signal(customer["id"], "crypto", symbol.upper(), timeframe,
                result["direction"], result.get("signal_strength", "low"), result.get("score", 0),
                result.get("last_close"), result.get("source", "MEXC"))
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Crypto historical data is temporarily unavailable")


@app.post("/api/paper/crypto/auto")
async def auto_crypto_paper_entry(
    payload: CryptoPaperAutoRequest,
    request: Request,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
):
    """Create at most one high-quality simulated futures entry; never contacts MEXC trading APIs."""
    _check_same_origin(request)
    init_auth_db()
    init_paper_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    symbol = payload.symbol.upper()
    if symbol not in CRYPTO_FUTURES:
        raise HTTPException(status_code=400, detail="Unsupported crypto futures market")
    if payload.timeframe not in {"1h", "4h", "1d"}:
        raise HTTPException(status_code=400, detail="Crypto paper auto-entry timeframe must be 1h, 4h, or 1d")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    try:
        candles_data = await get_candles(symbol, payload.timeframe, 100)
        analysis = analyze_candles(candles_data, payload.timeframe)
        current_quotes = await get_market_overview()
        current_quote = next((item for item in current_quotes if item["symbol"] == symbol), None)
        if not current_quote:
            raise HTTPException(status_code=503, detail="No current MEXC futures quote; no paper trade was created")
        analysis["last_close"] = float(current_quote["price"])
        analysis["trade_bias"] = (
            "LONG" if analysis["direction"] == "CALL"
            else "SHORT" if analysis["direction"] == "PUT"
            else "WAIT"
        )
        plan = build_paper_trade_plan(
            analysis,
            account_balance=payload.account_balance,
            risk_percent=payload.risk_percent,
            leverage=payload.leverage,
        )
        if plan is None:
            return {
                "created": False,
                "reason": "Signal is WAIT or does not meet the high-confidence paper-entry filter",
                "analysis": analysis,
                "mode": "paper",
                "execution": "simulated_only",
                "broker_order_sent": False,
            }
        trade = open_paper_trade(
            customer["id"], symbol, plan["side"], plan["quantity"],
            plan["entry_price"], plan["stop_loss"], plan["take_profit"],
            idempotency_key, leverage=payload.leverage,
        )
        return {
            "created": True,
            "trade": trade,
            "plan": plan,
            "analysis": analysis,
            "mode": "paper",
            "execution": "simulated_only",
            "broker_order_sent": False,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="MEXC futures candles unavailable; no paper trade was created")


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
    if source not in {"mexc", "binance"}:
        raise HTTPException(status_code=400, detail="Crypto backtesting currently uses the MEXC perpetual futures public feed")
    if symbol.upper() not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail="Unsupported crypto market")
    try:
        candle_data = await get_candles(symbol, timeframe, 200)
        result = backtest_candles(candle_data, timeframe, lookahead_candles)
        result.update({"symbol": symbol.upper(), "category": "crypto",
                       "source": source.upper() + " historical candles",
                       "execution_enabled": False})
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Crypto historical data is temporarily unavailable")


@app.get("/api/risk/policy")
async def risk_policy():
    """Return the fixed demo-only risk policy; no order execution is enabled."""
    return evaluate_demo_risk(0.0, 0, 0)


@app.get("/api/market-data/forex/markets")
async def forex_markets():
    try:
        markets = await get_forex_market_overview()
        return {"source": "Yahoo Finance public Forex data", "category": "forex",
                "account_connected": False, "execution_enabled": False, "markets": markets}
    except (ValueError, httpx.HTTPError):
        raise HTTPException(status_code=502, detail="Public Forex market data is temporarily unavailable")


@app.get("/api/market-data/forex/candles/{symbol}")
async def forex_candles(symbol: str, granularity: int = Query(default=900),
                        count: int = Query(default=100, ge=20, le=200)):
    try:
        return {"symbol": symbol, "granularity": granularity,
                "source": "Yahoo Finance public Forex data",
                "candles": await get_forex_candles(symbol, granularity, count),
                "execution_enabled": False}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Public Forex candles are temporarily unavailable")


@app.get("/api/signals/forex/{symbol}")
async def forex_signal(symbol: str, request: Request, timeframe: str = Query(default="15m")):
    intervals = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
                 "1h": 3600, "4h": 14400, "1d": 86400}
    if timeframe not in intervals:
        raise HTTPException(status_code=400, detail="Unsupported signal timeframe")
    try:
        candles = await get_forex_candles(symbol, intervals[timeframe], 100)
        result = analyze_candles(candles, timeframe)
        result.update({"symbol": symbol, "category": "forex", "market_type": "forex",
                       "source": "Yahoo Finance public market candles",
                       "execution_enabled": False})
        customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
        if customer:
            result["history_id"] = record_signal(customer["id"], "forex", symbol, timeframe,
                result["direction"], result.get("signal_strength", "low"), result.get("score", 0),
                result.get("last_close"), result.get("source", "Yahoo Finance"))
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Public Forex data is temporarily unavailable; no signal was generated")


@app.get("/api/signals/history")
async def customer_signal_history(request: Request, limit: int = Query(default=50, ge=1, le=100)):
    init_auth_db()
    init_signal_history_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"signals": list_signals(customer["id"], limit), "statistics": signal_statistics(customer["id"]),
            "result_method": "customer_confirmed", "note": "Win/loss/draw outcomes are manually confirmed by you; they are not verified by a broker."}


@app.post("/api/signals/history/{signal_id}/result")
async def update_customer_signal_result(signal_id: str, payload: SignalResultRequest, request: Request):
    _check_same_origin(request)
    init_auth_db()
    init_signal_history_db()
    customer = get_customer_for_session(request.cookies.get(SESSION_COOKIE))
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        updated = set_signal_result(customer["id"], signal_id, payload.result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Signal not found or already settled")
    return {"signal": updated, "statistics": signal_statistics(customer["id"]),
            "result_method": "customer_confirmed"}


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
