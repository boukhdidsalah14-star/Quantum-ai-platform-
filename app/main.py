from pathlib import Path
import hmac
import os
import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.market_data import get_candles, get_market_overview
from app.deriv_demo import DerivConfigError, DerivConnectionError, get_demo_status

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="QUANTUM AI", version="0.3.1", description="Read-only trading workspace foundation")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "quantum-ai", "market_data": "public-read-only", "deriv_demo_connector": "available", "order_execution": False, "trading_enabled": False}

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
