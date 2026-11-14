# QUANTUM AI MetaTrader cloud connections

QUANTUM AI supports a customer choice of MetaTrader 4 (MT4) or MetaTrader 5 (MT5).

## Architecture

- Customers use the QUANTUM AI Android/mobile app.
- QUANTUM AI creates a cloud account through MetaApi.
- The customer enters their MT login and password on MetaApi's hosted configuration page. QUANTUM AI does not collect or store that password.
- MetaApi provisions and operates the remote MT terminal.
- QUANTUM AI stores only the MetaApi account ID, platform, broker and server against the authenticated customer.

## Server setup

1. Create a MetaApi account and obtain a server-side API token.
2. Add `METAAPI_TOKEN` to the Render preview service's private Environment settings. Never commit the token to Git.
3. Ensure the service has durable PostgreSQL storage configured before accepting customer connections.
4. Open Auto Trading in QUANTUM AI, select MT4 or MT5, enter the broker and exact server name, and create the cloud connection.
5. Open the one-day secure configuration link returned by MetaApi and enter the broker account credentials there.
6. Refresh status until MetaApi reports the terminal as deployed and connected.

## Important safety state

This integration provisions cloud connections and exposes connection status only. It does not yet route strategy orders through MetaApi. Do not enable real-money execution until demo order placement, order reconciliation, SL/TP, customer-level risk limits, and emergency stop have passed tests.

MetaApi is a paid third-party service. Review its current subscription and per-account/API usage charges before enabling customer provisioning. MT4/MT5 account availability and broker server recognition can vary.
