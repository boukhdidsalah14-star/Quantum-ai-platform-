# QUANTUM AI — Professional Product Roadmap

This roadmap is the delivery checklist for the current QUANTUM AI platform. It preserves the existing blue/black mobile-first design and the selected platform scope: IQ Option, MEXC, cTrader and IC Markets.

## Delivery rules

- Do not replace or regress the current app design without an explicit request.
- Do not label simulated balances, demo positions or research signals as real money or live execution.
- Every broker capability must be verified against its supported API and account permissions.
- Never store broker secrets in browser storage or ship secrets in the Android APK.
- Every feature must have a test or an explicit manual acceptance checklist before it is called complete.
- Prefer graceful unavailable/error states over fake data, fake connection badges or silent failures.

## Phase 1 — Reliability and release engineering

- [ ] Build Android debug APK in GitHub Actions and retain a downloadable artifact.
- [ ] Verify Android manifest, overlay permission flow, foreground service lifecycle and stop action.
- [ ] Test floating assistant on a physical Android device over IQ Option app and Chrome.
- [ ] Verify signal API response parsing, supported symbols, timeframe mapping, timeout and error states.
- [ ] Add persistent local signal history and prevent duplicate result submissions.
- [ ] Add automated API smoke tests for health, Forex markets, candles and signals.
- [ ] Add deploy health checks and document rollback procedure.
- [ ] Add app version/build number display and a release checklist.

## Phase 2 — Professional market terminal

- [ ] Reliable market watchlist with clear market-open/stale/unavailable states.
- [ ] Custom candlestick chart with timeframe selection, crosshair and indicator overlays.
- [ ] Signal detail view: direction, strength, indicator rationale, source and candle timestamp.
- [ ] Signal history with pair, timeframe, expiry, generated time and user-confirmed outcome.
- [ ] Configurable alerts and notification preferences.
- [ ] Responsive loading, empty, offline and error states on every market screen.
- [ ] Clear distinction between research signals, paper trades and broker-executed orders.

## Phase 3 — Customer account and subscription experience

- [ ] Secure sign-up, login, session expiry and account recovery.
- [ ] Profile, subscription status, invoices/order history and plan entitlements.
- [ ] Referral dashboard with verified sign-ups, verified paid conversions and reward ledger.
- [ ] Customer support/contact flow and service-status page.
- [ ] Accessible onboarding that explains broker connection permissions and risk.
- [ ] Rate limits, abuse protection and server-side entitlement checks.

## Phase 4 — Broker integrations

- [ ] IQ Option: verify official supported integration options before offering account connection or execution.
- [ ] MEXC: test read-only market/account features separately from any live-trading permission.
- [ ] cTrader: complete OAuth/account discovery and demo order lifecycle tests.
- [ ] IC Markets: validate the exact supported cTrader/MT integration route and account region.
- [ ] Enforce per-customer encrypted credentials/tokens, least privilege and revocation.
- [ ] Add explicit demo/live mode confirmation, position limits, loss limits and emergency stop.
- [ ] No live execution until broker authorization, risk controls, audit logs and end-to-end tests pass.

## Phase 5 — Operations and monetization

- [ ] Admin dashboard for customer, subscription, referral and support operations.
- [ ] Revenue and conversion analytics with privacy-conscious event tracking.
- [ ] HypeLab placement approval and real impression/fill verification before showing ad inventory status.
- [ ] Payment provider webhook signature, idempotency, retry and reconciliation tests.
- [ ] Monitoring for API latency, market-data failures, crashes and failed payments.
- [ ] Backup/restore drills and documented incident response.

## Phase 6 — Launch readiness

- [ ] Security review of authentication, authorization, secrets, API limits and dependencies.
- [ ] Full regression test on small Android screens and common browsers.
- [ ] Physical-device overlay testing across Android versions and battery-management settings.
- [ ] Terms, privacy policy, risk disclosure and broker/platform compatibility review.
- [ ] Signed release APK/AAB, release notes, support process and staged rollout.
- [ ] Verify all public claims against the actual shipped capabilities.

## Current floating assistant scope

Implemented in the Android source branch: draggable overlay circle, pair/expiry selectors, signal request, countdown and manual WIN/LOSS/DRAW confirmation. It is informational only: it does not place IQ Option orders, inspect the broker screen or automatically detect the result.

**Current status:** source committed; Android APK build and physical-device behavior still require verification.