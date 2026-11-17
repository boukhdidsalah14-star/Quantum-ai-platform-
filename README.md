# QUANTUM AI

## Android beta distribution

- Customer information and download page: `/static/download.html` (after the feature branch is deployed).
- Public GitHub release page: https://github.com/boukhdidsalah14-star/Quantum-ai-platform-/releases
- The Android GitHub Actions workflow builds an installable debug-signed beta APK and publishes it as a prerelease asset when the workflow runs.
- The debug APK is for evaluation only. Before commercial distribution, create a private production signing key, store signing material only in protected GitHub Actions secrets, build a signed release APK/AAB, and test upgrades and Play Protect behavior. Never commit keystores or passwords.
- Customer support: supportveloxlabs@gmail.com.


A mobile-first trading workspace foundation with a custom candlestick dashboard, Telegram entry point, and an initial customer identity layer.

## Current capabilities

- Responsive QUANTUM AI dashboard with a custom Canvas candlestick chart.
- Public, read-only USDT-margined perpetual futures quotes and candles for the approved crypto watchlist through the MEXC Futures API; separate MEXC Spot endpoints remain available for spot data.
- Customer-scoped MEXC USD-M Futures API credentials are encrypted at rest; signed account verification, contract-rule lookup, open-position reads, market-order placement, and market close primitives are implemented.
- MEXC auto-trading can be explicitly started/stopped per active member. The worker evaluates completed 1h/4h/1d candles, allows one strategy per customer, blocks duplicate entries per candle, sizes orders from exchange contract size/volume steps, caps risk at 1% and notional at $500 per entry, uses isolated margin, and attaches exchange-side stop-loss/take-profit. A persistent 10% UTC-day equity drawdown guard stops new entries.
- Live MEXC trading requires `QUANTUM_MEXC_LIVE_TRADING_ENABLED=true`, durable encrypted storage, a customer-owned API key with Futures order permission, and an active subscription. Stopping a strategy prevents new entries but does not close existing positions; attached exchange TP/SL remains active. An uncertain order submission is recorded as unknown and is not blindly retried.
- Initial Deriv public market-data adapter for Forex and synthetic underlyings: active symbols, OHLC candles, and available binary/option contract metadata. This uses the official unauthenticated public WebSocket and cannot place trades.
- Backend market-data endpoints with symbol/interval allowlists and short-lived in-memory caching.
- Telegram bot commands: `/start`, `/help`, `/status`, `/markets`, `/price BTCUSDT`, `/forex`, `/binary`, `/signal`, `/quote`, and `/backtest`; market commands use allowlisted public read-only quotes. In production, Telegram updates are delivered through an authenticated HTTPS webhook handled by the FastAPI service.
- Customer-owned Deriv virtual-account verification using the REST OTP + authenticated WebSocket flow; verifies account balance before encrypted storage.
- Demo-only Deriv binary execution engine: obtains an authenticated demo OTP URL, checks USD balance, requests a CALL/PUT proposal, buys by proposal ID, and records the contract ID. A background monitor refreshes contract settlement status while the service is running.
- Customer-isolated Deriv demo trade ledger with idempotency keys, one-open-contract limit, $0.35–$2 stake bounds, a $25 daily net-loss pause, and a three-consecutive-loss pause. The engine is protected by a separate explicit environment kill switch.
- Customer identity API and dashboard account panel: register, login, current session, and logout.
- Customer-isolated paper-trading ledger with public-quote simulated entries, manual simulated closes, realized/unrealized P/L, idempotency keys, a $500 per-position notional cap, and a five-open-position cap.
- Backend-driven broker capability registry for Deriv, Olymp Trade, and MEXC; the UI distinguishes implemented read-only scope from pending provider integrations.
- Passwords are salted PBKDF2-SHA256 hashes. Session tokens are random, stored server-side as SHA-256 hashes, and sent in HttpOnly cookies.
- Login attempts are throttled per normalized email + client IP using a persistent 15-minute SQLite bucket; successful login clears the bucket.
- Browser-origin checks reject cross-origin register/login/logout requests when an Origin header is present.
- Customer/session tables with per-customer identifiers as the foundation for tenant-owned resources. SQLite is used for local development; when `DATABASE_URL` is configured, customer, subscription, encrypted credential, paper-trading, virtual-account, and Deriv demo ledgers use Neon PostgreSQL.

## Olymp Trade integration foundation

Olymp Trade is represented as a signal-and-paper-trading candidate. The initial module in `app/olymp_trade.py` reuses the transparent candle-based indicator engine and explicitly reports that the broker account and market-data feed are not connected. It accepts completed candles only from a separately verified market-data source. Paper execution is a simulation and does not send orders.

Olymp Trade's help center says trading robots are allowed subject to conditions, but this does not establish a supported public third-party order API. Quantum AI does not collect Olymp Trade passwords, extract browser session tokens, reverse-engineer private WebSocket messages, or automate the broker website. Demo and real broker order placement remain disabled until Olymp Trade supplies written authorization and documented integration credentials/endpoints. See the [Olymp Trade robot policy](https://plus.olymptrade.com/en/help/category/trading/can-i-use-robots-when-trading-on-the-platform).

## Olymp Trade signal and paper workflow

The authenticated application API now exposes:
- `POST /api/olymp-trade/analyze` for indicator analysis of completed candles supplied by the caller (minimum 30). The candle source is not verified by this endpoint.
- `GET /api/olymp-trade/paper/trades` for the signed-in customer's isolated paper ledger.
- `POST /api/olymp-trade/paper/trades` to open a simulated CALL/PUT position using a caller-supplied reference price and required idempotency key.
- `POST /api/olymp-trade/paper/trades/{trade_id}/settle` to settle a simulation using a supplied exit reference price.

Paper risk limits: $2 maximum stake, three open simulated positions, supported expiries of 1/5/15/30/60 minutes, and a $10 rolling 24-hour realized-loss pause. The API returns `broker_order_sent: false`; these routes never connect to Olymp Trade. Caller-supplied candles and prices are not independently verified, so this is a development simulator, not broker-grade execution or a performance guarantee.

### Customer-configured paper risk controls

Each customer must configure a paper account balance before opening an Olymp Trade paper position. The customer chooses each trade amount (minimum $0.10); an individual position and the combined open positions cannot exceed the configured balance. The system pauses new paper positions when realized losses in the rolling previous 24 hours reach 10% of that configured balance. For example, a $100 configured balance gives a $10 loss threshold; a $500 balance gives a $50 threshold. The balance is a manually configured simulation value, not a verified Olymp Trade account balance. These controls do not protect or control any real broker account.

## Not enabled / important limits

- Customer registration is closed by default. Set `ALLOW_CUSTOMER_SIGNUP=true` only when you are ready to accept signups and have deployed HTTPS, persistent storage, and abuse protection.
- Customer-owned Deriv demo credentials are accepted only after a read-only balance verification and are encrypted per customer. Configure a private Fernet `QUANTUM_CREDENTIALS_ENCRYPTION_KEY` and attach durable storage before setting `QUANTUM_PERSISTENT_STORAGE=true`. The API never returns stored tokens.
- Deriv demo order execution is code-complete behind two independent gates: `QUANTUM_PERSISTENT_STORAGE=true` and `QUANTUM_DERIV_DEMO_TRADING_ENABLED=true`. Both must remain false until the service has a real persistent disk, the encryption key is set, and a customer's own VRTC account has been verified. The execution endpoint rejects real account IDs and non-demo WebSocket URLs. Real-account order execution remains disabled.
- IQ Option account automation is blocked pending a verified supported retail API; the commonly found community clients are reverse-engineered and are not used. MEXC public Spot quotes/candles are integrated read-only. MEXC account execution remains disabled because its official API connects directly to live trading and does not provide a sandbox; a separate reviewed risk-control gate is required. See the [MEXC API introduction](https://www.mexc.io/api-docs/spot-v3/introduction) and [MEXC API overview](https://www.mexc.com/mexc-api). The broker registry is a capability display, not proof of a live customer connection.
- The crypto paper-trading feature is a simulation only. Deriv binary execution is restricted to a customer-verified VRTC demo account and remains locked by default. No real-account trading is implemented or enabled.
- Public exchange quotes are not broker execution prices and do not guarantee an executable quote.
- Production persistence uses Neon PostgreSQL through `DATABASE_URL`. Keep the connection string private in the hosting provider's secret environment. Before customer launch, verify backups, restore procedures, encryption keys, and all tenant-isolation flows.

## Subscription payments (NOWPayments)

The membership price is **exactly $30 USD equivalent in USDT TRC20 for 30 days**. Authenticated customers create a payment through `POST /api/subscription/checkout`. The server requests a NOWPayments payment using `pay_currency=usdttrc20`, a unique customer-owned order ID and the public IPN endpoint `POST /api/payments/nowpayments/ipn`. Repeated checkout taps reuse the existing pending payment instead of creating duplicate payment requests.

Only a valid HMAC-SHA512 signed NOWPayments IPN, or a server-authenticated payment-status lookup, can update an order. Activation requires the matching internal order ID and payment ID, `payment_status=finished`, `price_amount=30`, `price_currency=usd`, and `pay_currency=usdttrc20`. When NOWPayments supplies `actually_paid`, an amount below the requested crypto amount is rejected. Activation is idempotent; duplicate callbacks never grant extra days. Renewals extend from the later of the current time or the existing expiry.

Customer endpoints:
- `GET /api/subscription` — current membership status and whether checkout is configured.
- `GET /api/subscription/order` — the signed-in customer's pending payment only.
- `POST /api/subscription/checkout` — create or resume a $30 USDT TRC20 payment.
- `POST /api/subscription/refresh` — reconcile the customer's pending payment directly with NOWPayments if an IPN is delayed.
- `POST /api/payments/nowpayments/ipn` — public signed payment notification endpoint.

**Durable storage is mandatory before checkout can be enabled.** Set `QUANTUM_PERSISTENT_STORAGE=true` and configure `DATABASE_URL` to the production Neon PostgreSQL database. The payment ledger intentionally refuses to accept funds against ephemeral local SQLite storage. Keep the database URL private in Render.

Configure these private Render environment values:
- `DATABASE_URL` — Neon PostgreSQL connection string.
- `QUANTUM_PERSISTENT_STORAGE=true` — confirms that durable storage is ready.
- `NOWPAYMENTS_API_KEY` — API key from NOWPayments.
- `NOWPAYMENTS_IPN_SECRET` — IPN secret from NOWPayments.
- `QUANTUM_PUBLIC_URL` — canonical HTTPS public app URL, matching the deployed Render service.

In the NOWPayments dashboard, add the merchant's payout wallet, generate the API key and IPN secret, and configure the IPN callback URL to `https://YOUR-APP-HOST/api/payments/nowpayments/ipn`. The wallet address is managed by NOWPayments and is not hard-coded in the app. Confirm the payout-wallet and IPN settings before accepting customer funds. The app never asks customers to send money to an address copied from an unverified message, and it does not hold wallet private keys.

The membership panel shows the payment amount, TRC20 network, payment ID, internal order reference and provider status. Customers can copy the address and manually refresh status; the server verifies status with NOWPayments and activates only after confirmed completion. Expired/failed orders do not activate access. The system does not initiate refunds or payouts.

Do not enable customer registration or advertise checkout as live until the Render secrets, Neon persistence, NOWPayments dashboard, IPN delivery and a real low-value end-to-end payment have all been verified. NOWPayments documentation: [API and endpoint description](https://nowpayments.zendesk.com/hc/en-us/articles/21345824322717-API-and-endpoint-description) and [IPN setup](https://nowpayments.zendesk.com/hc/en-us/articles/21395546303389-IPN-and-how-to-setup).

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

- `GET /api/brokers` — returns the current verified integration scope for supported broker candidates; IQ Option is not included. It never reports a broker as connected merely because it is planned or configured.

## Customer Deriv demo connection and execution

- `POST /api/connections/deriv/demo/verify` — verify a customer's VRTC account with a read-only balance request; credentials are encrypted and saved only when durable storage is configured.
- `GET /api/connections/deriv/demo` — show connection metadata; never returns secrets.
- `DELETE /api/connections/deriv/demo` — delete that customer's stored demo credentials.
- `POST /api/deriv/demo/trades` — request a CALL/PUT contract on a verified VRTC demo account; requires an `Idempotency-Key`.
- `GET /api/deriv/demo/trades` — list that customer's demo trade history and risk state.

Deriv demo order execution uses the current REST OTP + authenticated demo WebSocket workflow: verify a USD demo balance, request a CALL/PUT proposal, buy by proposal ID, then monitor the returned contract ID. An uncertain buy is marked `unknown` and blocks further entries rather than risking a duplicate. Open contracts are refreshed every 15 seconds by the single-instance service monitor.

The engine has two independent safety gates: set `QUANTUM_PERSISTENT_STORAGE=true` only after attaching durable storage at `QUANTUM_DB_PATH`, and set `QUANTUM_DERIV_DEMO_TRADING_ENABLED=true` only after the encryption key and a customer's own demo account are configured. Both default to false. Real-account order execution is not implemented.

Set `QUANTUM_CREDENTIALS_ENCRYPTION_KEY` to a privately generated Fernet key before use. Keep it in the hosting provider's private environment settings and back it up securely; losing it makes stored credentials undecryptable. Never commit the key or paste it into chat.

## Paper trading API

All routes require a signed-in customer session. Each customer's trade records are isolated by customer ID.

- `GET /api/paper/trades` — list the customer's simulated trades and current mark-to-market P/L when public quotes are available.
- `POST /api/paper/trades` — open a simulated position using the latest public quote; requires an `Idempotency-Key` header. JSON fields: `symbol`, `side` (`long` or `short`), and `quantity`. Stop-loss and take-profit automation is not implemented.
- `POST /api/paper/trades/{trade_id}/close` — close one of the customer's open simulated positions at the latest public quote.

Supported paper symbols: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT. Maximum notional per position is $500 and each customer may have up to five open paper positions. These controls apply only to the simulator.

## Market API

- `GET /health` — service and execution status.
- `GET /api/markets` — allowlisted MEXC USDT-margined perpetual futures market overview.
- `GET /api/mexc/markets` — allowlisted MEXC public Spot market overview.
- `GET /api/deriv/markets?category=forex` — public Deriv Forex symbols with batched live tick prices; use `category=synthetic` for synthetic indices or `all` for both (up to 25 symbols per response).
- `GET /api/deriv/candles/frxEURUSD?granularity=900&count=100` — public Deriv OHLC candles for a verified active Forex/synthetic symbol.
- `GET /api/deriv/contracts/frxEURUSD` — available option contract metadata for a verified active symbol; no proposal or order is sent.
- `GET /api/signals/deriv/frxEURUSD?category=forex&timeframe=15m` — indicator-based CALL/PUT/WAIT analysis from public Deriv candles; no broker order is sent.
- `GET /api/deriv/proposal/R_100?contract_type=CALL&amount=1&duration=5` — public binary contract price preview only; the endpoint never buys a contract.
- `GET /api/backtest/deriv/frxEURUSD?category=forex&timeframe=15m` — no-lookahead historical directional test; no orders or profit forecast.
- `GET /api/signals/crypto/BTCUSDT?source=binance&timeframe=1h` and `GET /api/backtest/crypto/BTCUSDT?source=binance&timeframe=1h` — read-only crypto futures signals and historical direction tests using the MEXC perpetual futures feed. The legacy `source=binance` query value is retained for API compatibility.
- `GET /api/risk/policy` — static demo risk policy. Deriv customer demo execution has a separate per-customer ledger and enforces its limits only when its explicit safety gates are enabled.

Telegram commands: `/forex`, `/binary`, `/signal SYMBOL 15m forex`, `/signal SYMBOL 5m synthetic`, `/signal BTCUSDT 1h crypto`, `/quote R_100 CALL 1 5`, and `/backtest SYMBOL 15m forex` or `/backtest BTCUSDT 1h crypto`. Quotes are previews only; no orders are placed. Configure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBAPP_URL` privately in the hosting environment to activate the bot.
- `GET /api/mexc/candles/{symbol}?interval=1h&limit=72` — validated MEXC Spot candles.
- `GET /api/candles/{symbol}?interval=1h&limit=72` — validated public candles.

Allowed symbols: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT.

Allowed intervals: 1h, 4h, 1d. Candle limits are bounded to 20–200.

## Safety roadmap

1. Complete customer authentication hardening, email verification, account recovery, and tenant-owned resource coverage. (Initial identity/session layer and isolated paper-trade ledger are present.)
2. Add broker connection verification, provider-specific permission checks, and key-rotation procedures. (Encrypted per-customer Deriv demo credential storage foundation is present.)
3. Broker demo adapter, order submission, idempotency, customer trade ledger, and contract status monitor are implemented for Deriv VRTC binary contracts; live demo use remains locked pending durable storage and configuration.
4. Extend monitoring with reconciliation for uncertain buys, audit export, manual emergency stop, and broader end-to-end demo testing.
5. Keep real-account execution disabled until demo testing, explicit consent, and provider/legal review are complete.

Never commit `.env`, bot tokens, broker API keys, or customer credentials.


## Live execution foundation (not activated)

The branch `feature/broker-execution-foundation` adds `app/mexc_live_execution.py`, a signed MEXC Spot account-verification and market-order adapter. It requires both the server-side `QUANTUM_MEXC_LIVE_TRADING_ENABLED=true` kill switch and explicit per-customer consent, limits each order to 10 USDT, and returns an unknown-outcome error on a timeout. MEXC has no sandbox, so this adapter is intentionally not wired to customer routes, Telegram, or automatic strategy execution. Before wiring it, implement encrypted per-customer API-key storage, durable idempotency reservations, order reconciliation, customer-level daily loss limits, and integration tests against read-only account permissions. Start with API keys that have withdrawals disabled and IP restrictions enabled.

Deriv's current engine remains demo-only. The official API provides separate authenticated demo and real WebSocket endpoints; real execution needs a separately verified CR account, trade-scoped token/OAuth authorization, real OTP session creation, a real-account ledger, and reconciliation. Do not change the existing VRTC checks to make a real account pass them.

IQ Option has been removed from the product scope and is not listed as a broker.

No live order is placed by this branch, and the production service is not changed until this branch is reviewed, tested, and merged.


## Persistent database

The application keeps SQLite as its local-test fallback. Production services use Neon PostgreSQL when `DATABASE_URL` is present. The database adapter translates the existing repository queries to PostgreSQL, keeps customer rows as dictionary-style records, and serializes the existing critical idempotent order paths with a transaction-scoped advisory lock. Do not set `QUANTUM_PERSISTENT_STORAGE=true` until the Neon-backed deployment has passed end-to-end auth, subscription, vault, and trading-ledger tests.


## Step 2 market analysis

The analysis layer uses conservative, read-only indicators: EMA 9/21/50, MACD, RSI(14), ADX(14), ATR(14), Bollinger Bands and a volume filter where volume is supplied. It returns CALL, PUT or WAIT with reasons; it does not place orders and does not promise profitable outcomes.

The requested Forex chart universe contains EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, NZD/USD, EUR/JPY, GBP/JPY and XAU/USD. The binary-options analysis shortlist is EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CHF, USD/CAD, EUR/JPY and GBP/JPY.

The crypto futures watchlist contains BTC, ETH, BNB, XRP, SOL, TRX, DOGE, ADA, BCH and LINK. MEXC USDT-margined perpetual futures public candles and tickers are used for crypto signals; USDT is only the quote/settlement currency, not a selectable asset. This adapter is read-only and does not place futures orders. MEXC futures order execution requires a separate authenticated, risk-controlled integration and exchange/account eligibility checks.

All analysis endpoints are read-only. Broker order execution remains separately gated and must be verified through broker demo testing before any live use.


## JustMarkets MT4 bridge foundation

The JustMarkets MT4 Expert Advisor source is in `static/mt4/QuantumAI_JustMarkets_MT4.mq4`; installation notes are in `mt4/README.md`. The authenticated bridge binds one customer token to an exact MT4 demo login and server, syncs broker-reported positions/quotes and OHLC candles for all ten Forex symbols, and exposes an app chart overlay for entry, SL, TP and floating P/L.

The bridge is demo-only. It refuses live accounts. Demo order commands remain disabled unless durable storage and the explicit `QUANTUM_MT4_DEMO_EXECUTION_ENABLED=true` server switch are configured. The EA also requires `EnableDemoOrderExecution=true`. The current preview has not yet been connected to a real JustMarkets MT4 desktop terminal, and the MQL4 source still needs compilation in MetaEditor and broker-demo verification. The MT4 Android app cannot run Expert Advisors.


## JustMarkets MT4 demo auto-trader

The preview now includes a customer-specific demo auto-trader control and server monitor. After a customer has an active membership and a connected JustMarkets MT4 demo terminal, they can choose one of the ten supported Forex symbols, a timeframe, a 0.01–0.10 lot size, ATR-based stop/target distances, and a 1–10% equity-drawdown stop.

The strategy reads completed MT4 broker candles, applies the conservative multi-indicator signal engine, and queues at most one idempotent command per completed candle. It waits on weak/unclear signals, avoids opening a second position on the same symbol, and pauses when the configured equity-drawdown limit is reached. The EA also refuses non-demo accounts and has its own EnableDemoOrderExecution input, which defaults to false.

The persistent Neon database is connected and the bridge/auto-trader tables are initialized. The server-side MT4 demo execution switch remains OFF pending end-to-end verification with a compiled EA on a real JustMarkets demo terminal. No live-account execution is implemented. The MQL4 source still requires MetaEditor compilation and broker-demo verification before the demo auto-trader can be called complete.


## Bottom banner advertising

The mobile web dashboard includes a fixed, responsive bottom banner above the bottom navigation. Google AdSense is loaded only when both public placement values are configured in the hosting environment:

- `GOOGLE_ADSENSE_CLIENT_ID` — the approved publisher client ID in the `ca-pub-…` format.
- `GOOGLE_ADSENSE_BOTTOM_SLOT_ID` — the numeric responsive display-ad unit ID created for the bottom banner.

Create and verify the site in Google AdSense, wait for approval, create a responsive display ad unit, then add those two values to the Render service environment. Until then, the app shows a clearly labelled ad-placement placeholder and does not make ad requests. Ad blockers, consent requirements, invalid IDs, and provider fill rates can prevent ads from appearing. The native Android APK requires a separate Google AdMob SDK integration and app/ad unit IDs; the web AdSense slot is not represented as native APK advertising.
