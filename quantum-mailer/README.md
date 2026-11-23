# QUANTUM AI Mailer

A private, mobile-friendly campaign workspace for the owner's QUANTUM AI launch.

## Current MVP
- Owner-only password login (configured with server environment variables)
- Mobile-responsive dashboard
- Contact list, manual add, CSV import/export
- Explicit consent tracking and unsubscribed-contact status
- Campaign drafts and reusable templates
- Revenue target tracking for the $29.99/month subscription
- Sending setup checklist and delivery status placeholder

## Important current limitations
- This first MVP stores working dashboard records in browser localStorage. It is a prototype, not yet a multi-device production database.
- No email is sent by this build. The send action is intentionally absent until an approved provider is connected, domain authentication is verified, unsubscribe/bounce/complaint processing is in place, and the audience is permission-based.
- Do not import purchased, scraped, or otherwise unsolicited email lists.
- 500 million/month is a long-term infrastructure target, not a promised delivery volume.

## Render deployment
Runtime: Node 20+
Build command: `npm install`
Start command: `npm start`
Root directory: `quantum-mailer`

Required environment variables:
- `ADMIN_PASSWORD`: strong owner-only password
- `SESSION_SECRET`: random secret of at least 32 characters
- `NODE_ENV=production`

The app is not ready for a public deployment until those secrets are configured. Before production use, add a managed Postgres database for shared persistent records and connect an approved email service such as Amazon SES using provider credentials stored only in service environment variables.

## Email sending roadmap
1. Add managed database persistence and secure server-side contact storage.
2. Verify a QUANTUM AI sending domain with SPF, DKIM and DMARC.
3. Connect an approved ESP account and provider event webhooks.
4. Implement suppression, one-click unsubscribe, bounce and complaint handling.
5. Add a low-volume, consent-based pilot and rate limits.
6. Scale only when provider approval and deliverability metrics support it.
