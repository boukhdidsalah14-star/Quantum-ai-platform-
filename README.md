# QUANTUM AI

QUANTUM AI is a mobile-first **web trading workspace** with Forex and crypto market charts, technical analysis, signal history, customer accounts, subscriptions, and supported broker tools. The web app is the primary product and works independently; Telegram is not required to use QUANTUM AI.

## Current product scope

- **IC Markets through cTrader:** secure account authorization, account discovery and sync, market data, demo manual order controls, risk settings, and cTrader auto-strategy controls already present in the app. This integration is pending Spotware approval of the Open API application. Live actions remain behind their existing server-side and customer-consent gates.
- **IQ Option:** Forex CALL / PUT / WAIT signal analysis. IQ Option account authorization and order execution are not connected.
- **Forex:** public read-only candles and market overview, ten chart symbols, eight selected binary-analysis pairs, and signal/backtest endpoints.
- **Crypto:** selectable ten-coin watchlist, public market data, candlestick charts, timeframes, signals and backtesting. Public market data is read-only and does not require a crypto exchange account or send crypto orders.
- **Customer accounts, membership, payment validation, referral tracking, and responsive advertising placement.**
- **Optional Telegram integration:** informational commands only. It is separate from the web app and is not required for web-app operation.

The approved app appearance and bottom navigation are preserved. The supported platform directory contains only IC Markets/cTrader and IQ Option.

## Market data API

- `GET /health` — service health and supported execution state.
- `GET /api/market-universe` — Forex, binary-analysis and crypto watchlists.
- `GET /api/market-data/forex/markets` — public Forex overview.
- `GET /api/market-data/forex/candles/{symbol}?granularity=900&count=100` — Forex OHLC candles.
- `GET /api/markets` — public crypto market overview.
- `GET /api/candles/{symbol}?interval=1h&limit=100` — crypto OHLC candles; supported intervals are 1h, 4h and 1d.
- `GET /api/signals/forex/{symbol}?timeframe=15m` — Forex signal analysis.
- `GET /api/signals/crypto/{symbol}?timeframe=1h` — crypto signal analysis.
- `GET /api/backtest/crypto/{symbol}?timeframe=1h` — historical crypto signal-direction test.
- `GET /api/brokers` — supported integration capability list.

Crypto symbols include BTCUSDT, ETHUSDT, BNBUSDT, XRPUSDT, SOLUSDT, TRXUSDT, DOGEUSDT, ADAUSDT, BCHUSDT and LINKUSDT. USDT is a display quote unit, not an exchange connection.

## Optional Telegram commands

- `/start` — open the QUANTUM AI workspace.
- `/help` — list available commands.
- `/status` — app status.
- `/forex` — Forex watchlist.
- `/markets` — public crypto market overview.
- `/price BTCUSDT` — crypto quote.
- `/signal EURUSD 15m forex` or `/signal BTCUSDT 1h crypto` — signal analysis.
- `/backtest EURUSD 15m forex` or `/backtest BTCUSDT 1h crypto` — historical directional test.

Telegram is informational and does not place orders. The web app does not depend on it.

## Run locally

Python 3.10+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

## Render deployment

A Render Blueprint and production Dockerfile are included. Configure secrets only in Render's private environment settings. Keep customer registration closed until persistence, backups, authentication, monitoring, and payment callbacks have been verified.

Required environment values depend on enabled features. Never commit bot tokens, database credentials, cTrader credentials, or customer data.

## Safety

Market analysis is informational and does not guarantee profitable results. Public market prices are not necessarily executable broker prices. The app keeps its existing cTrader safety checks and authorization gates; do not enable live execution until account-specific demo testing and operational review are complete. IQ Option is signals-only. Crypto market charts and signals are read-only and do not place crypto orders.
