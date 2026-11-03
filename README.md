# QUANTUM AI

A mobile-first trading workspace foundation with a custom candlestick dashboard, Telegram entry point, and an initial customer identity layer.

## Current capabilities

- Responsive QUANTUM AI dashboard with a custom Canvas candlestick chart.
- Public, read-only crypto quotes and candles for BTC, ETH, BNB, SOL and XRP from selectable Binance and MEXC Spot feeds.
- Initial Deriv public market-data adapter for Forex and synthetic underlyings: active symbols, OHLC candles, and available binary/option contract metadata. This uses the official unauthenticated public WebSocket and cannot place trades.
- Backend market-data endpoints with symbol/interval allowlists and short-lived in-memory caching.
- Telegram bot commands: `/start`, `/help`, `/status`, `/markets`, `/price BTCUSDT`, `/forex`, `/binary`, `/signal`, `/quote`, and `/backtest`; market commands use allowlisted public read-only quotes. In production, Telegram updates are delivered through an authenticated HTTPS webhook handled by the FastAPI service.
- Customer-owned Deriv virtual-account verification using the REST OTP + authenticated WebSocket flow; verifies account balance before encrypted storage.
- Demo-only Deriv binary execution engine: obtains an authenticated demo OTP URL, checks USD balance, requests a CALL/PUT proposal, buys by proposal ID, and records the contract ID. A background monitor refreshes contract settlement status while the service is running.
- Customer-isolated Deriv demo trade ledger with idempotency keys, one-open-contract limit, $0.35–$2 stake bounds, a $25 daily net-loss pause, and a three-consecutive-loss pause. The engine is protected by a separate explicit environment kill switch.
- Customer identity API and dashboard account panel: register, login, current session, and logout.
- Customer-isolated paper-trading ledger with public-quote simulated entries, manual simulated closes, realized/unrealized P/L, idempotency keys, a $500 per-position notional cap, and a five-open-position cap.
- Backend-driven broker capability registry for Deriv, IQ Option, and MEXC; the UI distinguishes implemented read-only scope from pending provider integrations.
- Passwords are salted PBKDF2-SHA256 hashes. Session tokens are random, stored server-side as SHA-256 hashes, and sent in HttpOnly cookies.
- Login attempts are throttled per normalized email + client IP using a persistent 15-minute SQLite bucket; successful login clears the bucket.
- Browser-origin checks reject cross-origin register/login/logout requests when an Origin header is present.
- SQLite customer/session tables with per-customer identifiers as the foundation for tenant-owned resources.

## Not enabled / important limits

- Customer registration is closed by default. Set `ALLOW_CUSTOMER_SIGNUP=true` only when you are ready to accept signups and have deployed HTTPS, persistent storage, and abuse protection.
- Customer-owned Deriv demo credentials are accepted only after a read-only balance verification and are encrypted per customer. Configure a private Fernet `QUANTUM_CREDENTIALS_ENCRYPTION_KEY` and attach durable storage before setting `QUANTUM_PERSISTENT_STORAGE=true`. The API never returns stored tokens.
- Deriv demo order execution is code-complete behind two independent gates: `QUANTUM_PERSISTENT_STORAGE=true` and `QUANTUM_DERIV_DEMO_TRADING_ENABLED=true`. Both must remain false until the service has a real persistent disk, the encryption key is set, and a customer's own VRTC account has been verified. The execution endpoint rejects real account IDs and non-demo WebSocket URLs. Real-account order execution remains disabled.
- IQ Option account automation is blocked pending a verified supported retail API; the commonly found community clients are reverse-engineered and are not used. MEXC public Spot quotes/candles are integrated read-only. MEXC account execution remains disabled because its official API connects directly to live trading and does not provide a sandbox; a separate reviewed risk-control gate is required. See the [MEXC API introduction](https://www.mexc.io/api-docs/spot-v3/introduction) and [MEXC API overview](https://www.mexc.com/mexc-api). The broker registry is a capability display, not proof of a live customer connection.
- The crypto paper-trading feature is a simulation only. Deriv binary execution is restricted to a customer-verified VRTC demo account and remains locked by default. No real-account trading is implemented or enabled.
- Public exchange quotes are not broker execution prices and do not guarantee an executable quote.
- SQLite is suitable for the initial single-instance prototype; use managed PostgreSQL and persistent encrypted backups before a multi-instance customer launch.

## Customer authentication API

- `GET /api/auth/config` — return whether customer registration is currently open.
- `POST /api/auth/register` — create an account and start a session; disabled unless `ALLOW_CUSTOMER_SIGNUP=true`.
- `POST /api/auth/login` — authenticate and set an HttpOnly session cookie.
- `GET /api/auth/me` — return the signed-in customer profile.
- `POST /api/auth/logout` — revoke the current session and clear the cookie.

Registration/login JSON body: `{"email":"you@example.com","password":"at-least-12-characters"}`. Passwords must be 12–256 characters. Use HTTPS in production; cookies are marked Secure when `ENVIRONMENT=production`.

## Deploy on Render

A `render.yaml` Blueprint and production `Dockerfile` are included. In Render, create a new Blueprint from this repository and review the selected service and persistent-disk cost before confirming. The blueprint mounts `/var/data` so the SQLite customer and paper-trade database survives restarts. Keep signup closed until HTTPS, monitoring, backups, and abuse controls have been reviewed.

After creating the service, add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBAPP_URL`, and a private random `TELEGRAM_WEBHOOK_SECRET` (at least 32 characters) as private environment values in Render. The app registers the Telegram webhook at `TELEGRAM_WEBAPP_URL/telegram/webhook`; do not run a second polling process with the same bot token. Add Deriv demo secrets only if you are using the read-only admin demo status check. Never paste secrets into GitHub source files.

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

Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBAPP_URL`, and `TELEGRAM_WEBHOOK_SECRET` as private environment variables. `TELEGRAM_WEBAPP_URL` must be the public HTTPS dashboard URL. The FastAPI service registers an authenticated Telegram webhook at `/telegram/webhook`; do not start `run_bot.py` or another `getUpdates` polling process with the same token while the webhook is active.

```bash
python run_bot.py
```

The bot is informational only. It does not execute trades.

## Broker capability API

- `GET /api/brokers` — returns the current verified integration scope for Deriv, IQ Option, and MEXC. It never reports a broker as connected merely because it is planned or configured.

## Customer Deriv demo connection and execution

- `GET /api/connections/deriv/demo` — show whether the signed-in customer's Deriv demo credentials are stored; never returns secrets.
- `PUT /api/connections/deriv/demo` — save `{\"account_id\":\"VRTC...\",\"token\":\"...\"}` encrypted for that customer. Only virtual/demo account IDs are accepted.
- `DELETE /api/connections/deriv/demo` — delete that customer's stored demo credentials.

Set `QUANTUM_CREDENTIALS_ENCRYPTION_KEY` to a privately generated Fernet key before use. Keep it in the hosting provider's private environment settings and back it up securely; losing it makes stored credentials undecryptable. Never commit the key or paste it into chat. The vault does not connect to Deriv or place orders.

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
- `GET /api/deriv/markets?category=forex` — public Deriv Forex symbols with batched live tick prices; use `category=synthetic` for synthetic indices or `all` for both (up to 25 symbols per response).
- `GET /api/deriv/candles/frxEURUSD?granularity=900&count=100` — public Deriv OHLC candles for a verified active Forex/synthetic symbol.
- `GET /api/deriv/contracts/frxEURUSD` — available option contract metadata for a verified active symbol; no proposal or order is sent.
- `GET /api/signals/deriv/frxEURUSD?category=forex&timeframe=15m` — indicator-based CALL/PUT/WAIT analysis from public Deriv candles; no broker order is sent.
- `GET /api/deriv/proposal/R_100?contract_type=CALL&amount=1&duration=5` — public binary contract price preview only; the endpoint never buys a contract.
- `GET /api/backtest/deriv/frxEURUSD?category=forex&timeframe=15m` — no-lookahead historical directional test; no orders or profit forecast.
- `GET /api/signals/crypto/BTCUSDT?source=binance&timeframe=1h` and `GET /api/backtest/crypto/BTCUSDT?source=binance&timeframe=1h` — read-only crypto signals and historical direction tests (Binance or MEXC).
- `GET /api/risk/policy` — demo-only limits: $1 default stake, $2 maximum stake, $25 daily-loss limit, three consecutive losses, and one open contract. Risk monitoring/enforcement is not active yet.

Telegram commands: `/forex`, `/binary`, `/signal SYMBOL 15m forex`, `/signal SYMBOL 5m synthetic`, `/signal BTCUSDT 1h crypto`, `/quote R_100 CALL 1 5`, and `/backtest SYMBOL 15m forex` or `/backtest BTCUSDT 1h crypto`. Quotes are previews only; no orders are placed. Configure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBAPP_URL` privately in the hosting environment to activate the bot.
- `GET /api/mexc/candles/{symbol}?interval=1h&limit=72` — validated MEXC Spot candles.
- `GET /api/candles/{symbol}?interval=1h&limit=72` — validated public candles.

Allowed symbols: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT.

Allowed intervals: 1h, 4h, 1d. Candle limits are bounded to 20–200.

## Safety roadmap

1. Complete customer authentication hardening, email verification, account recovery, and tenant-owned resource coverage. (Initial identity/session layer and isolated paper-trade ledger are present.)
2. Add broker connection verification, provider-specific permission checks, and key-rotation procedures. (Encrypted per-customer Deriv demo credential storage foundation is present.)
3. Implement a broker demo adapter and verify order/settlement events.
4. Enforce the demo risk policy with a trade ledger, daily-loss monitoring, consecutive-loss lockout, idempotency, audit logs and emergency stop. (Policy values are defined; enforcement is not active.)
5. Keep real-account execution disabled until demo testing, explicit consent, and provider/legal review are complete.

Never commit `.env`, bot tokens, broker API keys, or customer credentials.
