# Subscription Payment Activation

Generated: 2026-04-28

Status: Implemented in code, inactive until Stripe environment variables are configured.

## Purpose

LedgerFlow now has the foundation for real subscription collection through hosted Stripe Checkout.

This is different from bank connection or direct deposit:
- this is customer subscription payment
- card entry happens on Stripe-hosted checkout
- LedgerFlow stores Stripe references and subscription status
- Stripe sends payouts to the bank account configured inside the Stripe account

## What Was Added

- Secure Stripe Checkout button on Billing Center
- Stripe Customer Portal button after a Stripe customer is connected
- Stripe API helper using hosted checkout, not local card capture
- Stripe webhook endpoint at `/stripe/webhook`
- subscription status sync from Stripe events
- database fields for Stripe customer, subscription, checkout session, price, and webhook event tracking
- safe fallback when Stripe is not configured

## What LedgerFlow Does Not Store

- full card number
- CVV
- raw bank account number for subscription billing

## Required Stripe Setup

See `STRIPE_RENDER_SETUP.md`.

## Verification

Local safety checks passed:
- billing page loads when Stripe is not configured
- checkout is blocked safely when keys are missing
- fake configured checkout redirects to hosted Stripe URL
- webhook simulation updates subscription status to active

## Launch Rule

Test with Stripe test mode first.

Do not switch to live Stripe keys until:
- test checkout passes
- webhook test passes
- payout bank account is confirmed in Stripe
- subscription plans/prices match LedgerFlow tiers
