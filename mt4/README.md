# QUANTUM AI — JustMarkets MT4 bridge

## Scope and safety

This Expert Advisor is a demo-first connector. It syncs account balance/equity, open positions, floating P/L and quotes to the customer's QUANTUM AI account. It can receive a demo order command only when **both** the EA input `EnableDemoOrderExecution=true` and server settings `QUANTUM_PERSISTENT_STORAGE=true` plus `QUANTUM_MT4_DEMO_EXECUTION_ENABLED=true` are configured.

- It refuses non-demo accounts and checks the expected account login, exact server and JustMarkets company name.
- Real-account execution is not implemented or enabled.
- Demo orders require a stop-loss and take-profit, are limited to 0.01–0.10 lots and at most three open positions.
- The server applies a 10% equity-drawdown guard by default (`QUANTUM_MT4_MAX_EQUITY_DRAWDOWN_PCT`).
- The bridge token is shown once in the app; only its SHA-256 hash is stored server-side. Never share the token.

## Installation

1. Create or use a **JustMarkets MT4 demo account**. Record the account login and exact server name shown in MT4.
2. In QUANTUM AI, sign in and open **Auto Trading → Connect your MT4 terminal**. Register the demo login/server and copy the one-time EA token.
3. Download `static/mt4/QuantumAI_JustMarkets_MT4.mq4`.
4. On a Windows computer or Windows VPS running the JustMarkets MT4 desktop terminal, open **File → Open Data Folder → MQL4 → Experts** and copy the EA file there.
5. Open MetaEditor (F4), open the EA and compile it. Attach it to a chart.
6. In MT4, open **Tools → Options → Expert Advisors** and add `https://quantum-ai-iqoption-preview.onrender.com` to the allowed WebRequest URLs.
7. In the EA inputs set:
   - `ApiBaseUrl`: the current QUANTUM AI app URL
   - `BridgeToken`: the one-time token copied from the app
   - `ExpectedAccountLogin`: your demo login
   - `ExpectedServer`: the exact demo server
   - `EnableDemoOrderExecution`: leave **false** for the first connection test
8. Enable AutoTrading and confirm the app shows **CONNECTED**. Check that the account balance, equity and open MT4 positions match your terminal.

## Important device limitation

The MetaTrader Android app cannot run MQL4 Expert Advisors. The EA must run inside MT4 desktop on Windows or a Windows VPS. The QUANTUM AI app can be opened on your phone while the terminal/EA runs separately.

## Current deployment limitation

The free preview service does not currently have confirmed durable storage. The bridge can be built and its API tested, but demo order execution remains locked until persistent storage is configured and the server-side demo switch is explicitly enabled. Do not use a live account or change the EA to bypass its demo checks.

## Chart data

The EA uploads broker-origin OHLC candles for the ten supported Forex symbols at the configured `ChartTimeframe` (default M15) every 30 seconds. The app uses fresh JustMarkets candles first, then falls back to public Deriv candles when broker candles are unavailable. It overlays MT4-reported entry, stop-loss, take-profit and floating P/L for matching open positions. Choose the same timeframe in the app and EA for exact candle alignment. Always compare with the actual JustMarkets MT4 terminal.
