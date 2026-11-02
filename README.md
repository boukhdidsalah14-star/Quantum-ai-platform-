# QUANTUM AI Platform

A mobile-first trading workspace for crypto, Forex and binary-market integrations, with a Telegram Mini App experience and a custom candlestick chart.

## Current build status
- Premium responsive dashboard and custom Canvas candlestick renderer.
- Live public crypto prices from Binance market-data endpoints (read-only; no account required).
- Forex, binary and broker execution adapters are integrations pending.
- No order placement, automated trading, customer credential storage or profit claims are implemented in this starter.
- No sample trade is presented as a real trade.

## Run locally
```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000.

## Safety roadmap
1. Authenticated customer accounts and tenant isolation.
2. Encrypted credential vault and audited broker connections.
3. Broker-specific demo adapters with verified order and settlement confirmations.
4. Risk limits, idempotency, emergency stop and explicit real-account consent.
5. Real execution only after independent testing and jurisdiction/provider review.

Never commit secrets. Real trading is disabled by design. This software does not provide financial advice or guarantee returns.
