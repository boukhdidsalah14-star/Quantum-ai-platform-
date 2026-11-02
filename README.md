# QUANTUM AI

A mobile-first trading workspace foundation with a custom candlestick dashboard and an informational Telegram bot.

## Current capabilities

- Responsive QUANTUM AI dashboard with a custom Canvas candlestick chart.
- Public, read-only crypto quotes and candles for BTC, ETH, BNB, SOL and XRP.
- Backend market-data endpoints with symbol/interval allowlists and short-lived in-memory caching.
- Telegram bot commands: `/start`, `/help`, and `/status`; when `TELEGRAM_BOT_TOKEN` is configured, the bot can run alongside the FastAPI dashboard in one service.
- Deriv demo account status connector using the current REST OTP + authenticated WebSocket flow; reads balance and active-symbol count only.
- Telegram `/start` can show an Open Dashboard Mini App button when `TELEGRAM_WEBAPP_URL` is configured to an HTTPS URL.

## Not enabled

- No customer credential storage or multi-user broker account management. The initial Deriv connector uses server-side environment secrets for one demo account only.
- No order placement, auto-trading, binary-options execution, or real-account trading. The Deriv connector never sends proposal, buy, sell, or contract-management requests.
- Public exchange quotes are not broker execution prices and do not guarantee an executable quote.

## Run the dashboard

Python 3.10+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

## Run the Telegram bot

Set `TELEGRAM_BOT_TOKEN` as a private environment variable. After deploying the dashboard over HTTPS, set `TELEGRAM_WEBAPP_URL` to its public URL. The FastAPI service starts the Telegram polling bot automatically when the token is present; use a single web-service instance to avoid multiple polling processes.

```bash
python run_bot.py
```

The bot is informational only. It does not execute trades.

## API

- `GET /health` — service and execution status.
- `GET /api/markets` — allowlisted public crypto market overview.
- `GET /api/candles/{symbol}?interval=1h&limit=72` — validated public candles.

Allowed symbols: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT.

Allowed intervals: 1h, 4h, 1d. Candle limits are bounded to 20–200.

## Safety roadmap

1. Add customer authentication and tenant isolation.
2. Add encrypted credential storage and provider-specific permission checks.
3. Implement a broker demo adapter and verify order/settlement events.
4. Add stake limits, daily loss limits, idempotency, audit logs and emergency stop.
5. Keep real-account execution disabled until demo testing, explicit consent, and provider/legal review are complete.

Never commit `.env`, bot tokens, broker API keys, or customer credentials.
