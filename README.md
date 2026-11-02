# QUANTUM AI

A mobile-first trading workspace foundation with a custom candlestick dashboard, Telegram entry point, and an initial customer identity layer.

## Current capabilities

- Responsive QUANTUM AI dashboard with a custom Canvas candlestick chart.
- Public, read-only crypto quotes and candles for BTC, ETH, BNB, SOL and XRP from selectable Binance and MEXC Spot feeds.
- Backend market-data endpoints with symbol/interval allowlists and short-lived in-memory caching.
- Telegram bot commands: `/start`, `/help`, `/status`, `/markets`, and `/price BTCUSDT`; market commands use allowlisted public read-only quotes. When `TELEGRAM_BOT_TOKEN` is configured, the bot can run alongside the FastAPI dashboard in one service.
- Deriv demo account status connector using the REST OTP + authenticated WebSocket flow; reads balance and active-symbol count only.
- Customer identity API and dashboard account panel: register, login, current session, and logout.
- Customer-isolated paper-trading ledger with public-quote simulated entries, manual simulated closes, realized/unrealized P/L, idempotency keys, a $500 per-position notional cap, and a five-open-position cap.
- Backend-driven broker capability registry for Deriv, IQ Option, and MEXC; the UI distinguishes implemented read-only scope from pending provider integrations.
- Passwords are salted PBKDF2-SHA256 hashes. Session tokens are random, stored server-side as SHA-256 hashes, and sent in HttpOnly cookies.
- Login attempts are throttled per normalized email + client IP using a persistent 15-minute SQLite bucket; successful login clears the bucket.
- Browser-origin checks reject cross-origin register/login/logout requests when an Origin header is present.
- SQLite customer/session tables with per-customer identifiers as the foundation for tenant-owned resources.

## Not enabled / important limits

- Customer registration is closed by default. Set `ALLOW_CUSTOMER_SIGNUP=true` only when you are ready to accept signups and have deployed HTTPS, persistent storage, and abuse protection.
- No customer broker credential storage or multi-user broker account management yet.
- IQ Option account automation is blocked pending a verified supported retail API; the commonly found community clients are reverse-engineered and are not used. MEXC public Spot quotes/candles are integrated read-only. MEXC account execution remains disabled because its official API connects directly to live trading and does not provide a sandbox; a separate reviewed risk-control gate is required. See the [MEXC API introduction](https://www.mexc.io/api-docs/spot-v3/introduction) and [MEXC API overview](https://www.mexc.com/mexc-api). The broker registry is a roadmap/status display, not proof of connectivity. The initial Deriv connector uses server-side environment secrets for one demo account only.
- Paper trading is a simulation only and is not connected to any broker. No real order placement, auto-trading, binary-options execution, or real-account trading. The Deriv connector never sends proposal, buy, sell, or contract-management requests.
- Public exchange quotes are not broker execution prices and do not guarantee an executable quote.
- SQLite is suitable for the initial single-instance prototype; use managed PostgreSQL and persistent encrypted backups before a multi-instance customer launch.

## Customer authentication API

- `POST /api/auth/register` — create an account and start a session; disabled unless `ALLOW_CUSTOMER_SIGNUP=true`.
- `POST /api/auth/login` — authenticate and set an HttpOnly session cookie.
- `GET /api/auth/me` — return the signed-in customer profile.
- `POST /api/auth/logout` — revoke the current session and clear the cookie.

Registration/login JSON body: `{"email":"you@example.com","password":"at-least-12-characters"}`. Passwords must be 12–256 characters. Use HTTPS in production; cookies are marked Secure when `ENVIRONMENT=production`.

## Deploy on Render

A `render.yaml` Blueprint and production `Dockerfile` are included. In Render, create a new Blueprint from this repository and review the selected service and persistent-disk cost before confirming. The blueprint mounts `/var/data` so the SQLite customer and paper-trade database survives restarts. Keep signup closed until HTTPS, monitoring, backups, and abuse controls have been reviewed.

After creating the service, add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBAPP_URL` as private environment values in Render. Add Deriv demo secrets only if you are using the read-only admin demo status check. Never paste secrets into GitHub source files. The Telegram bot uses polling inside the single web-service instance; do not scale this service to multiple replicas without moving bot polling to a dedicated worker.

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

## Broker capability API

- `GET /api/brokers` — returns the current verified integration scope for Deriv, IQ Option, and MEXC. It never reports a broker as connected merely because it is planned or configured.

## Paper trading API

All routes require a signed-in customer session. Each customer's trade records are isolated by customer ID.

- `GET /api/paper/trades` — list the customer's simulated trades and current mark-to-market P/L when public quotes are available.
- `POST /api/paper/trades` — open a simulated position using the latest public quote; requires an `Idempotency-Key` header. JSON fields: `symbol`, `side` (`long` or `short`), and `quantity`. Stop-loss and take-profit automation is not implemented.
- `POST /api/paper/trades/{trade_id}/close` — close one of the customer's open simulated positions at the latest public quote.

Supported paper symbols: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT. Maximum notional per position is $500 and each customer may have up to five open paper positions. These controls apply only to the simulator.

## Market API

- `GET /health` — service and execution status.
- `GET /api/markets` — allowlisted Binance public crypto market overview.
- `GET /api/mexc/markets` — allowlisted MEXC public Spot market overview.
- `GET /api/mexc/candles/{symbol}?interval=1h&limit=72` — validated MEXC Spot candles.
- `GET /api/candles/{symbol}?interval=1h&limit=72` — validated public candles.

Allowed symbols: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT.

Allowed intervals: 1h, 4h, 1d. Candle limits are bounded to 20–200.

## Safety roadmap

1. Complete customer authentication hardening, email verification, account recovery, and tenant-owned resource coverage. (Initial identity/session layer and isolated paper-trade ledger are present.)
2. Add encrypted credential storage and provider-specific permission checks.
3. Implement a broker demo adapter and verify order/settlement events.
4. Add stake limits, daily loss limits, idempotency, audit logs and emergency stop.
5. Keep real-account execution disabled until demo testing, explicit consent, and provider/legal review are complete.

Never commit `.env`, bot tokens, broker API keys, or customer credentials.
