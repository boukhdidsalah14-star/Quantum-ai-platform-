from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="QUANTUM AI", version="0.1.0", description="Trading workspace foundation")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "quantum-ai", "trading_enabled": False}

@app.get("/")
async def dashboard():
    return FileResponse(ROOT / "static" / "index.html")
