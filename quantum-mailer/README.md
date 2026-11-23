# QUANTUM AI Mailer

Private owner-only campaign workspace for QUANTUM AI.

## Backend
- Node.js 20+, PostgreSQL (Neon), AWS SES v2 adapter.
- Server-side sessions, contact/campaign persistence, revenue settings.
- Consent-required sending eligibility and suppression list.
- Signed unsubscribe links.
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
