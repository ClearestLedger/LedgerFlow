# LedgerFlow Bookkeeping And Bank Architecture

Date: 2026-04-23

Purpose:
- use the Batch 1 observation window for safe sidecar architecture work
- define the right internal bookkeeping design before adding live bank feeds
- keep LedgerFlow as one unified platform without mixing customer invoices, internal bookkeeping, and bank-import staging into one long-term table

## Core decision

LedgerFlow should implement bookkeeping and bank connectivity as a separate internal finance domain, not as an extension of the current customer-facing invoice table.

The current codebase already shows three useful foundations:
- customer-facing sales documents are stored in `invoices` with `record_kind` values like `estimate` and `customer_invoice`
- bookkeeping-only revenue entries are also still being stored in that same `invoices` table with `record_kind='income_record'`
- jobs already carry revenue and cost fields such as `revenue_amount`, `materials_cost_amount`, `labor_cost_amount`, and `other_cost_amount`

That means the product direction is already right, but the finance engine needs a cleaner split.

## Final product rule

LedgerFlow remains one platform with separate internal domains:
- sales documents
- bookkeeping ledger
- jobs and profit
- worker payroll context
- bank and statement import
- reporting

The product should not become a generic accounting clone.
It should become a service-business control platform with a stronger internal finance engine.

## Recommended provider direction

### Primary recommendation for post-launch bank transaction feeds

Use Plaid Transactions as the primary bank-feed provider for the bookkeeping leg.

Why:
- Plaid supports transaction history retrieval with `/transactions/sync`
- Plaid documents up to 24 months of historical transaction data
- Plaid supports incremental sync with cursors and webhook-driven updates
- Plaid is better matched to bookkeeping transaction ingestion than the current Stripe-only billing posture

Official sources:
- [Plaid Transactions overview](https://plaid.com/docs/transactions/)
- [Plaid Transactions API reference](https://plaid.com/docs/api/products/transactions/)

### Secondary recommendation

Use Stripe Financial Connections as an optional secondary bank-data path only if LedgerFlow later wants a tighter Stripe-based ACH and payment-verification experience.

Why:
- Stripe Financial Connections is strong for ownership, balances, and payment-linked bank connection
- Stripe supports transactions data too, but it is more naturally aligned with Stripe’s payment and account-verification ecosystem
- Stripe’s transactions docs describe paginated transaction retrieval and refresh/subscription behavior, but the available history is generally up to the last 180 days depending on the institution

Official sources:
- [Stripe Financial Connections fundamentals](https://docs.stripe.com/financial-connections/fundamentals)
- [Stripe Financial Connections transactions](https://docs.stripe.com/financial-connections/transactions)

## Launch-safe rule

Do not add live bank connectivity during current invited-client stabilization.

Build in this order:
1. internal ledger separation
2. statement import staging
3. reconciliation workflow
4. bank-feed provider integration
5. reporting and close process

## Files in this pack

- `TARGET_DATA_MODEL.md`
- `IMPLEMENTATION_PHASES.md`
- `STATEMENT_IMPORT_RULES.md`
- `PROVIDER_EVALUATION.md`
