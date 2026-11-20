from app.mexc_futures_worker import worker_is_enabled

def test_worker_requires_explicit_worker_mode_and_live_enablement():
    assert worker_is_enabled({"QUANTUM_MEXC_AUTO_EXECUTION_MODE": "worker", "QUANTUM_MEXC_LIVE_TRADING_ENABLED": "true"})

def test_worker_is_disabled_by_default_and_in_inline_mode():
    assert not worker_is_enabled({})
    assert not worker_is_enabled({"QUANTUM_MEXC_AUTO_EXECUTION_MODE": "inline", "QUANTUM_MEXC_LIVE_TRADING_ENABLED": "true"})

def test_worker_mode_still_requires_explicit_live_enablement():
    assert not worker_is_enabled({"QUANTUM_MEXC_AUTO_EXECUTION_MODE": "worker", "QUANTUM_MEXC_LIVE_TRADING_ENABLED": "false"})