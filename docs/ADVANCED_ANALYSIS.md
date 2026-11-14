# Advanced QUANTUM AI market analysis

The signal API now uses `app.advanced_signals.analyze_market` through the existing `app.signals.analyze_candles` entry point. Existing Olymp Trade analysis and any callers using the shared signal module therefore use the same upgraded engine.

## Inputs and safety

- Supply at least 30 completed OHLC candles for the selected asset and timeframe.
- Candle values must be positive and internally consistent. Caller must ensure bars are closed and timestamps are ordered.
- Use broker-native or otherwise independently verified quotes before making any decision. Public exchange data is not interchangeable with broker execution prices.
- Analysis is research-only; the engine never places orders.

## Factors

- EMA 9/21/50/200 trend alignment (EMA 200 falls back to EMA 50 when fewer than 200 bars are supplied).
- RSI(14), MACD (12/26/9) histogram, ATR(14), ADX(14), Bollinger position and 20-bar breakout checks.
- Candle body strength and optional higher-timeframe EMA 9/21 bias.
- Regime labels: trending, high volatility, or ranging/weak trend. High-volatility conditions are filtered to WAIT.
- Conflicting supplied higher-timeframe biases block a directional entry.

## Signal interpretation

- CALL / PUT requires a multi-factor score threshold; otherwise WAIT.
- `confluence_score` is a rule-based confluence score, **not** a calibrated probability of winning.
- The engine deliberately does not promise a win rate. Measure directional accuracy, payout-adjusted expectancy and drawdown separately for every asset, timeframe, broker feed and expiry.

## Validation still required before production

1. Verify the market-data feed, completed-bar semantics, timestamps and symbol mapping for each asset.
2. Run rolling walk-forward tests with strictly chronological splits and no future leakage.
3. Include spread, payout, commission, slippage, rejected orders and execution latency in the simulator.
4. Keep an untouched out-of-sample period; report sample size, coverage, accuracy, expectancy, profit factor, drawdown and confidence intervals by asset/timeframe.
5. Calibrate probabilities only on held-out data and monitor drift/regime changes. Do not convert the confluence score into a probability label.
6. Keep real-money execution disabled until the relevant broker integration is documented, authorized, risk-tested and explicitly enabled.

The simple legacy backtest is a directional diagnostic only; it is not a payout-aware binary-options profitability test.
