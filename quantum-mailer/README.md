# QUANTUM AI Mailer

Private owner-only campaign workspace for QUANTUM AI.

## Backend
- Node.js 20+, PostgreSQL (Neon), AWS SES v2 adapter.
- Server-side sessions, contact/campaign persistence, revenue settings.
- Consent-required sending eligibility and suppression list.
- Signed unsubscribe links and suppression of unsubscribed recipients.
- Signed click redirects with total and unique click reporting.
- Consent-gated website attribution: page views, signup events, purchase events, UTM source/campaign, Live Traffic and pseudonymous Buyer Radar.
- Owner-directed SES test email endpoint; manual campaign batches remain capped at 25.
- Campaign sending is deliberately limited to 25 opted-in recipients per manual batch. This is a pilot control, not bulk-scale infrastructure.
- No send is possible until SES credentials, verified sender identity/domain and public app URL are configured.

## Render
Root directory: `quantum-mailer`
Build: `npm install`
Start: `npm start`

Required environment:
- ADMIN_PASSWORD
- SESSION_SECRET
- DATABASE_URL
- NODE_ENV=production

Optional SES environment (all required for sending):
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- AWS_REGION
- MAIL_FROM (verified SES sender)
- PUBLIC_APP_URL (this app's HTTPS origin)

Never put provider keys in frontend code or Git. Use only opted-in contacts; do not import purchased, scraped or unsolicited lists. Verify SPF, DKIM and DMARC and monitor complaints/bounces before any scale-up. This app does not provide 500M/month delivery capacity; that would require provider approval, separate queue workers, quota increases and substantial deliverability validation.

## Website attribution

Only add the tracker after the visitor has granted the analytics consent required by your privacy notice. The script uses a random browser identifier in local storage and records page path, UTM source/campaign and explicitly triggered conversions. It does not collect visitor names or email addresses.

```html
<script src="https://quantum-ai-mailer.onrender.com/tracker.js" defer></script>
```

After a successful registration, call:

```js
window.QAITrack('signup');
```

After your payment provider confirms a successful payment (not merely a checkout click), call:

```js
window.QAITrack('purchase', 29.99);
```

The Mailer reports the amount passed by your site; it does not independently verify payments. Replace the app origin if the Mailer is deployed to another domain. UTM parameters `utm_source` and `utm_campaign` are recorded for attribution.
