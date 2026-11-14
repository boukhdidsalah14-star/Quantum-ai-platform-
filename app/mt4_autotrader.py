"""Demo-only JustMarkets MT4 auto-trader driven by completed broker candles."""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

from app.database import sqlite3
from app.market_universe import FOREX_PAIRS
from app.mt4_bridge import (
    ALLOWED_SYMBOLS,
    BridgeAuthError,
    bridge_status,
    enqueue_demo_order,
    get_mt4_candles,
)

ALLOWED_TIMEFRAMES = {"5m", "15m", "30m", "1h", "4h"}
MIN_LOTS = 0.01
MAX_LOTS = 0.10


def _connect():
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def demo_execution_enabled() -> bool:
    return (
        os.getenv("QUANTUM_PERSISTENT_STORAGE", "").strip().lower() == "true"
        and os.getenv("QUANTUM_MT4_DEMO_EXECUTION_ENABLED", "").strip().lower() == "true"
    )


def init_db() -> None:
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS mt4_auto_trader_settings (
            customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
            active INTEGER NOT NULL DEFAULT 0,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            lots REAL NOT NULL,
            stop_atr REAL NOT NULL DEFAULT 1.5,
            target_atr REAL NOT NULL DEFAULT 2.0,
            max_drawdown_pct REAL NOT NULL DEFAULT 10.0,
            last_candle_time INTEGER,
            last_signal TEXT,
            last_message TEXT,
            last_command_id TEXT,
            started_at INTEGER,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mt4_auto_trader_active
            ON mt4_auto_trader_settings(active, updated_at);
        """)


def _clean_settings(symbol: str, timeframe: str, lots: float,
                    stop_atr: float, target_atr: float,
                    max_drawdown_pct: float) -> tuple[str, str, float, float, float, float]:
    symbol = str(symbol or "").strip().upper()
    timeframe = str(timeframe or "").strip()
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError("Choose a supported JustMarkets Forex symbol")
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise ValueError("Choose a supported timeframe from 5m to 4h")
    try:
        lots = float(lots)
        stop_atr = float(stop_atr)
        target_atr = float(target_atr)
        max_drawdown_pct = float(max_drawdown_pct)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid auto-trader risk settings") from exc
    if not math.isfinite(lots) or not MIN_LOTS <= lots <= MAX_LOTS:
        raise ValueError("MT4 demo lot size must be between 0.01 and 0.10")
    if not math.isfinite(stop_atr) or not 0.5 <= stop_atr <= 5:
        raise ValueError("Stop-loss ATR multiplier must be between 0.5 and 5")
    if not math.isfinite(target_atr) or not 0.5 <= target_atr <= 8:
        raise ValueError("Take-profit ATR multiplier must be between 0.5 and 8")
    if not math.isfinite(max_drawdown_pct) or not 1 <= max_drawdown_pct <= 10:
        raise ValueError("Equity drawdown limit must be between 1% and 10%")
    return symbol, timeframe, lots, stop_atr, target_atr, max_drawdown_pct


def get_settings(customer_id: str) -> dict[str, Any]:
    with _connect() as db:
        row = db.execute(
            "SELECT * FROM mt4_auto_trader_settings WHERE customer_id=?",
            (customer_id,),
        ).fetchone()
    if not row:
        return {
            "active": False,
            "symbol": "XAUUSD",
            "timeframe": "15m",
            "lots": 0.01,
            "stop_atr": 1.5,
            "target_atr": 2.0,
            "max_drawdown_pct": 10.0,
            "last_signal": None,
            "last_message": "Auto trader is stopped.",
            "last_command_id": None,
            "execution_mode": "demo_only",
        }
    result = dict(row)
    result["active"] = bool(result["active"])
    result["execution_mode"] = "demo_only"
    return result


def start_auto_trader(customer_id: str, symbol: str, timeframe: str,
                      lots: float, stop_atr: float = 1.5,
                      target_atr: float = 2.0,
                      max_drawdown_pct: float = 10.0) -> dict[str, Any]:
    if not demo_execution_enabled():
        raise PermissionError("MT4 demo auto trading is locked until durable storage and the demo-only server switch are enabled")
    settings = _clean_settings(symbol, timeframe, lots, stop_atr, target_atr, max_drawdown_pct)
    snapshot = bridge_status(customer_id)
    if not snapshot.get("connected") or snapshot.get("mode") != "demo":
        raise ValueError("Connect your JustMarkets MT4 demo terminal before starting auto trading")
    if settings[0] not in snapshot.get("quotes", {}):
        raise ValueError("The connected MT4 terminal has not supplied a current quote for this symbol")
    now = int(time.time())
    with _connect() as db:
        db.execute("""
            INSERT INTO mt4_auto_trader_settings
                (customer_id, active, symbol, timeframe, lots, stop_atr, target_atr,
                 max_drawdown_pct, last_candle_time, last_signal, last_message,
                 last_command_id, started_at, updated_at)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?, NULL, NULL,
                    'Running in JustMarkets demo mode; waiting for the next completed candle.',
                    NULL, ?, ?)
            ON CONFLICT(customer_id) DO UPDATE SET
                active=1, symbol=excluded.symbol, timeframe=excluded.timeframe,
                lots=excluded.lots, stop_atr=excluded.stop_atr,
                target_atr=excluded.target_atr,
                max_drawdown_pct=excluded.max_drawdown_pct,
                last_candle_time=NULL, last_signal=NULL,
                last_message=excluded.last_message, last_command_id=NULL,
                started_at=excluded.started_at, updated_at=excluded.updated_at
        """, (customer_id, *settings, now, now))
    return get_settings(customer_id)


def stop_auto_trader(customer_id: str) -> dict[str, Any]:
    now = int(time.time())
    with _connect() as db:
        db.execute("""
            UPDATE mt4_auto_trader_settings
            SET active=0, last_message='Auto trader stopped. No new commands will be generated.',
                updated_at=?
            WHERE customer_id=?
        """, (now, customer_id))
    return get_settings(customer_id)


def _record_decision(customer_id: str, candle_time: int, signal: str,
                     message: str, command_id: str | None = None,
                     stop: bool = False) -> None:
    with _connect() as db:
        db.execute("""
            UPDATE mt4_auto_trader_settings
            SET last_candle_time=?, last_signal=?, last_message=?,
                last_command_id=COALESCE(?, last_command_id),
                active=CASE WHEN ? THEN 0 ELSE active END,
                updated_at=?
            WHERE customer_id=?
        """, (candle_time, signal, message[:240], command_id, int(stop),
              int(time.time()), customer_id))


def _command_key(customer_id: str, symbol: str, timeframe: str, candle_time: int) -> str:
    material = f"{customer_id}|{symbol}|{timeframe}|{candle_time}".encode()
    return "qai_auto_" + hashlib.sha256(material).hexdigest()[:24]


def process_active_auto_traders() -> None:
    """Evaluate each active customer once per completed broker candle."""
    if not demo_execution_enabled():
        return
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM mt4_auto_trader_settings WHERE active=1 ORDER BY updated_at"
        ).fetchall()

    from app.signals import analyze_candles

    for row in rows:
        config = dict(row)
        customer_id = config["customer_id"]
        symbol = config["symbol"]
        timeframe = config["timeframe"]
        try:
            snapshot = bridge_status(customer_id)
            if not snapshot.get("connected") or snapshot.get("mode") != "demo":
                _record_decision(customer_id, int(config["last_candle_time"] or 0),
                                 "WAIT", "Waiting for a fresh JustMarkets MT4 demo connection.")
                continue
            candles_data = get_mt4_candles(customer_id, symbol, timeframe)
            if not candles_data or len(candles_data.get("candles", [])) < 50:
                _record_decision(customer_id, int(config["last_candle_time"] or 0),
                                 "WAIT", "Waiting for at least 50 fresh completed MT4 candles.")
                continue
            candles = candles_data["candles"]
            candle_time = int(candles[-1]["time"])
            if candle_time <= int(config["last_candle_time"] or 0):
                continue

            positions = snapshot.get("positions", [])
            if len(positions) >= 3:
                _record_decision(customer_id, candle_time, "WAIT",
                                 "Risk guard: maximum of three open MT4 positions reached.")
                continue
            if any(position.get("symbol") == symbol for position in positions):
                _record_decision(customer_id, candle_time, "WAIT",
                                 "An MT4 position is already open for this symbol; waiting for it to close.")
                continue

            balance = float(snapshot.get("balance") or 0)
            equity = float(snapshot.get("equity") or 0)
            drawdown = max(0.0, balance - equity) / balance * 100 if balance > 0 else 0.0
            if drawdown >= float(config["max_drawdown_pct"]):
                _record_decision(customer_id, candle_time, "STOP",
                                 "Equity drawdown limit reached; auto trader has stopped.", stop=True)
                continue

            analysis = analyze_candles(candles, timeframe)
            direction = analysis["direction"]
            if direction not in {"CALL", "PUT"} or analysis["signal_strength"] not in {"moderate", "high"}:
                _record_decision(customer_id, candle_time, direction,
                                 f"{direction}: no sufficiently strong completed-candle setup.")
                continue

            quote = snapshot.get("quotes", {}).get(symbol)
            if not quote:
                _record_decision(customer_id, candle_time, "WAIT",
                                 "No current JustMarkets broker quote for this symbol.")
                continue
            bid, ask = float(quote["bid"]), float(quote["ask"])
            atr = float(analysis["atr_14"])
            if atr <= 0 or ask < bid or (ask - bid) > atr * 0.25:
                _record_decision(customer_id, candle_time, "WAIT",
                                 "Spread or volatility filter rejected this entry.")
                continue

            side = "BUY" if direction == "CALL" else "SELL"
            entry = ask if side == "BUY" else bid
            stop_distance = atr * float(config["stop_atr"])
            target_distance = atr * float(config["target_atr"])
            digits = 2 if symbol == "XAUUSD" else 3 if symbol.endswith("JPY") else 5
            if side == "BUY":
                stop_loss = round(entry - stop_distance, digits)
                take_profit = round(entry + target_distance, digits)
            else:
                stop_loss = round(entry + stop_distance, digits)
                take_profit = round(entry - target_distance, digits)

            command_id = _command_key(customer_id, symbol, timeframe, candle_time)
            queued = enqueue_demo_order(
                customer_id, symbol, side, float(config["lots"]),
                stop_loss, take_profit, command_id=command_id,
            )
            _record_decision(
                customer_id, candle_time, direction,
                f"{direction} {symbol}: demo order queued from completed {timeframe} candle.",
                command_id=queued.get("command_id"),
            )
        except PermissionError as exc:
            _record_decision(customer_id, int(config["last_candle_time"] or 0),
                             "STOP", str(exc), stop=True)
        except (ValueError, BridgeAuthError, KeyError, TypeError) as exc:
            _record_decision(customer_id, int(config["last_candle_time"] or 0),
                             "WAIT", str(exc))
        except Exception as exc:
            _record_decision(customer_id, int(config["last_candle_time"] or 0),
                             "WAIT", f"Auto-trader cycle error: {str(exc)[:180]}")
