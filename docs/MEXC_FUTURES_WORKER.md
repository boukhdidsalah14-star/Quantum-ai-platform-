# QUANTUM AI MEXC futures worker

The MEXC automation loop must run in a dedicated, always-on Render Background Worker for dependable execution. A Free Render Web Service sleeps after inactivity and is not an execution host.

## Safe rollout

1. Keep the current web service in its existing inline mode while no worker exists. The worker entrypoint is locked unless both environment flags are explicitly set.
2. Provision a paid Background Worker only after approving its recurring cost.
3. Configure the worker with the same PostgreSQL DATABASE_URL, QUANTUM_CREDENTIALS_ENCRYPTION_KEY, and application secrets as the web service. Do not use separate SQLite files for the two processes.
4. Set QUANTUM_MEXC_AUTO_EXECUTION_MODE=worker on the web service to prevent the web process from launching the automation loop.
5. Set the same mode and QUANTUM_MEXC_LIVE_TRADING_ENABLED=true on the worker. Per-customer subscription, credential fingerprint, explicit consent, emergency-stop, daily-loss, and order-size checks remain enforced by the strategy code.
6. Verify worker logs, account reconciliation, and exchange-side order state with a dedicated test account before allowing customer use.

Suggested worker start command: python -m app.mexc_futures_worker.

Do not switch the web service to worker mode until the background worker is deployed and healthy; doing so intentionally stops inline automation.