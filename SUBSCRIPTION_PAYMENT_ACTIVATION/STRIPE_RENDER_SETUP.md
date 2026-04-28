# Stripe And Render Setup

Generated: 2026-04-28

## Stripe Dashboard

Create three monthly recurring Prices:

- Essential: `$59/mo`
- Growth: `$99/mo`
- Premium: `$149/mo`

Copy each Stripe Price ID.

Typical format:
- `price_...`

## Render Environment Variables

Add these to the Render service:

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_SELF_SERVICE`
- `STRIPE_PRICE_ASSISTED_SERVICE`
- `STRIPE_PRICE_PREMIUM_PRINCIPAL`

Optional aliases also supported:
- `STRIPE_PRICE_ESSENTIAL`
- `STRIPE_PRICE_GROWTH`
- `STRIPE_PRICE_PREMIUM`

Optional:
- `STRIPE_ALLOW_PROMOTION_CODES=1`

## Webhook URL

Add this endpoint in Stripe:

`https://ledgerflow-vprm.onrender.com/stripe/webhook`

Subscribe to these events:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_succeeded`
- `invoice.payment_failed`

## Payouts To Danielle Account

Payouts do not happen inside LedgerFlow.

Payouts happen from Stripe to the bank account configured in the Stripe Dashboard.

Before live launch:
- complete Stripe business verification
- add payout bank account
- confirm payout schedule
- test with Stripe test mode
- switch Render variables from test keys to live keys only when ready

## Important

Adding a card inside the old LedgerFlow method-on-file form does not charge the card.

The real charge happens only through:

`Open Secure Stripe Checkout`
