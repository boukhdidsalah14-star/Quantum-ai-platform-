# QUANTUM AI — JustMarkets MT4 read-only bridge

## Scope and safety

This connector is **read-only**. It syncs a verified JustMarkets MT4 demo account's balance, equity, currency, open positions, quotes, and broker-origin OHLC candles into the signed-in customer's QUANTUM AI workspace.

- The Expert Advisor refuses non-demo accounts and verifies the expected account login, exact server, and JustMarkets company name.
- The bridge token is shown once; only its SHA-256 hash is stored server-side.
- This build contains no order-placement code and no command-polling endpoint. It cannot open, close, or modify broker orders.
- Real-account connection is not supported.
- The server requires durable storage before it will issue a bridge token. The free Render service currently has no confirmed persistent disk, so connection registration may return a storage-required message until that is configured.

## Installation (after durable storage is enabled)

1. Create or use a **JustMarkets MT4 demo account**. Record the numeric account login and exact server name displayed in MT4.
2. Sign in to QUANTUM AI and open **MetaTrader 4**.
3. Enter the demo login and exact server name, then generate the one-time bridge token.
4. Download `/static/mt4/QuantumAI_JustMarkets_MT4.mq4`.
5. On Windows or a Windows VPS running JustMarkets MT4, open **File → Open Data Folder → MQL4 → Experts** and copy the EA file there.
6. Open MetaEditor (F4), compile the EA, and attach it to a chart.
7. In MT4, open **Tools → Options → Expert Advisors** and add `https://quantum-ai-platform-62cz.onrender.com` to the allowed WebRequest URLs.
8. Set `BridgeToken`, `ExpectedAccountLogin`, and `ExpectedServer` in the EA inputs. Keep the account in DEMO mode.
9. Confirm the app reports **CONNECTED** and that the displayed balance, equity, positions, and candles match the MT4 terminal.

## Device limitation

The MetaTrader Android app cannot run MQL4 Expert Advisors. The EA must run in MT4 desktop on Windows or a Windows VPS. You can still open the QUANTUM AI dashboard on Android while the EA runs separately.

## Current scope

The MT4 chart can use fresh broker-origin candles and verified open-position details. No automated trading or real-money order execution is enabled in this integration step.
