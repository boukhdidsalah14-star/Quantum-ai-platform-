from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.market_data import get_candles, get_market_overview

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="QUANTUM AI", version="0.2.0", description="Read-only trading workspace foundation")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "quantum-ai", "market_data": "public-read-only", "order_execution": False, "trading_enabled": False}

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

@app.get("/")
async def dashboard():
    return FileResponse(ROOT / "static" / "index.html")
