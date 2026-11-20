"""Customer-scoped cTrader Forex automation engine.

Strategies are OFF by default. Each customer must explicitly start a strategy
for a selected demo or live account. One entry maximum per completed candle.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from app.database import sqlite3
from app.signals import analyze_candles
from app.ctrader_open_api import (
    get_demo_candles, get_live_candles, sync_demo_account, sync_live_account,
    open_demo_trade, open_live_trade,
)
from app.ctrader_permissions import require_demo_permission, require_live_permission, CTraderPermissionError

ALLOWED_TIMEFRAMES = {"5m", "15m", "30m", "1h", "4h"}
MAX_SYMBOLS = 5
ENGINE_MAX_LOTS = 0.01


def _db():
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=20)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with _db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS ctrader_auto_strategies (
          customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
          account_id TEXT NOT NULL, environment TEXT NOT NULL,
          symbols_json TEXT NOT NULL, timeframe TEXT NOT NULL,
          lots REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
          last_candles_json TEXT NOT NULL DEFAULT '{}',
          last_signal TEXT, last_error TEXT, last_trade_json TEXT,
          started_at INTEGER, updated_at INTEGER NOT NULL,
          PRIMARY KEY(customer_id, account_id, environment))""")


def _row(row):
    if not row:
        return None
    try:
        symbols = json.loads(row["symbols_json"])
        candles = json.loads(row["last_candles_json"])
        trade = json.loads(row["last_trade_json"]) if row["last_trade_json"] else None
    except (ValueError, TypeError):
        symbols, candles, trade = [], {}, None
    return {
        "customer_id": row["customer_id"], "account_id": row["account_id"],
        "environment": row["environment"], "symbols": symbols,
        "timeframe": row["timeframe"], "lots": float(row["lots"]),
        "enabled": bool(row["enabled"]), "last_candles": candles,
        "last_signal": row["last_signal"], "last_error": row["last_error"],
        "last_trade": trade, "started_at": row["started_at"],
        "updated_at": int(row["updated_at"]),
    }


def get_strategy(customer_id: str, account_id: str, environment: str):
    with _db() as db:
        return _row(db.execute(
            "SELECT * FROM ctrader_auto_strategies WHERE customer_id=? AND account_id=? AND environment=?",
            (customer_id, str(account_id), environment),
        ).fetchone())


def list_active_strategies():
    with _db() as db:
        rows = db.execute("SELECT * FROM ctrader_auto_strategies WHERE enabled=1").fetchall()
    return [item for item in (_row(row) for row in rows) if item]


def start_strategy(customer_id: str, account_id: str, environment: str,
                   symbols: list[str], timeframe: str, lots: float):
    env = str(environment or "").lower()
    if env != "demo":
        raise ValueError("Only cTrader demo automation is available in this release")
    if not str(account_id).isdigit():
        raise ValueError("Sync your selected cTrader account first")
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise ValueError("Choose a supported timeframe from 5m to 4h")
    cleaned = list(dict.fromkeys(str(s).strip() for s in symbols if str(s).strip()))
    if not cleaned or len(cleaned) > MAX_SYMBOLS:
        raise ValueError("Choose between 1 and 5 Forex symbols")
    try:
        size = float(lots)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Trade size must be valid") from exc
    if not 0.001 <= size <= ENGINE_MAX_LOTS:
        raise ValueError("Automated trade size must be between 0.001 and 0.01 lots")
    require_demo_permission(customer_id, account_id)
    now = int(time.time())
    with _db() as db:
        db.execute("""INSERT INTO ctrader_auto_strategies
          (customer_id,account_id,environment,symbols_json,timeframe,lots,enabled,
           last_candles_json,last_signal,last_error,last_trade_json,started_at,updated_at)
          VALUES (?,?,?,?,?,?,1,'{}',NULL,NULL,NULL,?,?)
          ON CONFLICT(customer_id,account_id,environment) DO UPDATE SET
          symbols_json=excluded.symbols_json,timeframe=excluded.timeframe,lots=excluded.lots,
          enabled=1,last_error=NULL,started_at=excluded.started_at,updated_at=excluded.updated_at""",
          (customer_id, str(account_id), env, json.dumps(cleaned), timeframe, size, now, now))
    return get_strategy(customer_id, account_id, env)


def stop_strategy(customer_id: str, account_id: str, environment: str):
    with _db() as db:
        db.execute("""UPDATE ctrader_auto_strategies SET enabled=0,updated_at=?
          WHERE customer_id=? AND account_id=? AND environment=?""",
          (int(time.time()), customer_id, str(account_id), environment))
    return get_strategy(customer_id, account_id, environment)


def _update(customer_id, account_id, environment, *, candles=None, signal=None,
            error=None, trade=None):
    with _db() as db:
        row = db.execute("""SELECT last_candles_json,last_trade_json FROM ctrader_auto_strategies
          WHERE customer_id=? AND account_id=? AND environment=?""",
          (customer_id, str(account_id), environment)).fetchone()
        if not row:
            return
        candle_json = json.dumps(candles if candles is not None else json.loads(row["last_candles_json"] or "{}"))
        trade_json = json.dumps(trade) if trade is not None else row["last_trade_json"]
        db.execute("""UPDATE ctrader_auto_strategies SET last_candles_json=?,
          last_signal=COALESCE(?,last_signal),last_error=?,last_trade_json=?,updated_at=?
          WHERE customer_id=? AND account_id=? AND environment=?""",
          (candle_json, signal, error, trade_json, int(time.time()),
           customer_id, str(account_id), environment))


async def process_strategy(strategy: dict):
    customer_id = strategy["customer_id"]
    account_id = strategy["account_id"]
    environment = strategy["environment"]
    if environment != "demo":
        raise CTraderPermissionError("Live Forex automation is disabled in this release")
    if not strategy["enabled"]:
        return
    # Revalidate customer consent on every cycle; revocation stops automation.
    if environment == "demo":
        require_demo_permission(customer_id, account_id)
        snapshot = await sync_demo_account(customer_id, account_id)
    else:
        require_live_permission(customer_id, account_id)
        snapshot = await sync_live_account(customer_id, account_id)
    # The first release deliberately runs one position at a time per account.
    # Existing positions are left untouched and must be closed at the broker
    # before the engine will consider another entry.
    if snapshot.get("open_positions"):
        _update(customer_id, account_id, environment,
                signal="PAUSED · existing account position must be closed first", error=None)
        return
    for symbol in strategy["symbols"]:
        current = get_strategy(customer_id, account_id, environment)
        if not current or not current["enabled"]:
            return
        candle_data = (await get_demo_candles(customer_id, symbol, strategy["timeframe"], 100)
                       if environment == "demo"
                       else await get_live_candles(customer_id, symbol, strategy["timeframe"], 100))
        completed = (candle_data.get("candles") or [])[:-1]
        if len(completed) < 55:
            continue
        candle_time = str(int(completed[-1]["time"]))
        latest = current.get("last_candles") or {}
        if latest.get(symbol) == candle_time:
            continue
        # Persist the candle checkpoint before execution to prevent duplicate entries
        # if the broker response or process becomes uncertain.
        latest[symbol] = candle_time
        _update(customer_id, account_id, environment, candles=latest, error=None)
        analysis = analyze_candles(completed, strategy["timeframe"])
        direction = analysis.get("direction")
        if str(analysis.get("signal_strength", "")).lower() != "high" or direction not in {"CALL", "PUT"}:
            _update(customer_id, account_id, environment, signal="WAIT · filters not aligned", error=None)
            continue
        entry = float(completed[-1]["close"])
        atr = float(analysis.get("atr_14") or 0)
        if entry <= 0 or atr <= 0:
            continue
        side = "BUY" if direction == "CALL" else "SELL"
        stop_distance = atr * 1.5
        target_distance = atr * 2.25
        sl = entry - stop_distance if side == "BUY" else entry + stop_distance
        tp = entry + target_distance if side == "BUY" else entry - target_distance
        if sl <= 0 or tp <= 0:
            continue
        if environment == "demo":
            result = await open_demo_trade(customer_id, symbol, side, strategy["lots"], sl, tp)
        else:
            result = await open_live_trade(customer_id, symbol, side, strategy["lots"], sl, tp)
        if not result.get("broker_confirmed"):
            raise RuntimeError("Broker did not confirm automated order")
        _update(customer_id, account_id, environment,
                signal=f"{side} · {symbol} · {strategy['timeframe']}",
                error=None, trade=result)
        return


async def engine_loop():
    import asyncio
    while True:
        for strategy in list_active_strategies():
            try:
                await process_strategy(strategy)
            except CTraderPermissionError as exc:
                stop_strategy(strategy["customer_id"], strategy["account_id"], strategy["environment"])
                _update(strategy["customer_id"], strategy["account_id"],
                        strategy["environment"], error="Automation stopped: account permission was revoked")
            except Exception as exc:
                _update(strategy["customer_id"], strategy["account_id"],
                        strategy["environment"], error=str(exc)[:240])
        await asyncio.sleep(15)
