"""Dedicated process entrypoint for MEXC futures automation.

Run this only as a separately provisioned, always-on background worker.
The web service must use QUANTUM_MEXC_AUTO_EXECUTION_MODE=worker so the same
strategy loop is never started in both processes.
"""
from __future__ import annotations
import asyncio
import os
import signal

def worker_is_enabled(env: dict[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    return (
        values.get("QUANTUM_MEXC_AUTO_EXECUTION_MODE", "").strip().lower() == "worker"
        and values.get("QUANTUM_MEXC_LIVE_TRADING_ENABLED", "").strip().lower() == "true"
    )

async def run_worker() -> None:
    if not worker_is_enabled():
        raise RuntimeError("MEXC worker is locked: execution mode and explicit live enablement are required")
    from app.auth import init_auth_db
    from app.subscriptions import init_db as init_subscription_db
    from app.mexc_credential_vault import init_db as init_mexc_vault_db
    from app.mexc_futures_execution import init_auto_db as init_mexc_auto_db
    from app.mexc_live_permissions import init_db as init_mexc_live_permissions_db
    from app.main import _mexc_auto_monitor_loop
    init_auth_db()
    init_subscription_db()
    init_mexc_vault_db()
    init_mexc_auto_db()
    init_mexc_live_permissions_db()
    await _mexc_auto_monitor_loop()

async def main() -> None:
    if not worker_is_enabled():
        raise RuntimeError("MEXC worker is disabled; explicit worker mode and live enablement are required")
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass
    worker_task = asyncio.create_task(run_worker(), name="quantum-mexc-auto-worker")
    stop_task = asyncio.create_task(stop_event.wait(), name="quantum-worker-shutdown")
    done, pending = await asyncio.wait({worker_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    if worker_task in done:
        await worker_task
        raise RuntimeError("MEXC automation loop exited unexpectedly")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    for task in pending:
        task.cancel()

if __name__ == "__main__":
    asyncio.run(main())