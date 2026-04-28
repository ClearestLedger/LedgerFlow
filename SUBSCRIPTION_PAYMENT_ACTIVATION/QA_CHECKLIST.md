# Subscription Payment QA Checklist

Generated: 2026-04-28

## Test Mode

- Stripe test secret key is entered in Render
- test Price IDs are entered in Render
- Stripe webhook secret is entered in Render
- Render service restarted after variables are saved
- Billing Center shows Stripe ready/test mode

## Checkout

- open RDS Billing Center
- click `Open Secure Stripe Checkout`
- Stripe-hosted page opens
- business name/email appear correctly where Stripe supports it
- test card completes checkout
- user returns to LedgerFlow
- subscription status updates after webhook

## Customer Portal

- after successful checkout, `Open Stripe Customer Portal` appears
- portal opens hosted Stripe page
- payment method can be updated in Stripe
- user returns to Billing Center

## Webhook

- `checkout.session.completed` is received
- `customer.subscription.updated` is received
- `invoice.payment_succeeded` is received
- duplicate webhook events do not create duplicate processing
- failed payment marks subscription past due
- canceled subscription marks subscription canceled

## LedgerFlow Records

- `stripe_customer_id` saved
- `stripe_subscription_id` saved
- `stripe_checkout_session_id` saved
- `stripe_price_id` saved
- subscription status updates
- default billing method shows Stripe hosted subscription
- no full card number is stored in LedgerFlow

## Go-Live Gate

Do not use live cards until:
- test checkout passes
- webhook passes
- payout bank account is verified in Stripe
- first payout timing is understood
- legal/trust wording still accurately says card data is handled by hosted processor
