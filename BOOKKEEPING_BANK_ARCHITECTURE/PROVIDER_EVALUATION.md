# Provider Evaluation

## Recommendation

### Best primary provider for LedgerFlow bookkeeping feeds

Plaid Transactions

Reason:
- better aligned with transaction ingestion and sync as the main bookkeeping feed
- official docs describe up to 24 months of transaction history
- official docs describe cursor-based incremental sync with webhook updates

Official sources:
- [Plaid Transactions overview](https://plaid.com/docs/transactions/)
- [Plaid Transactions API reference](https://plaid.com/docs/api/products/transactions/)

## Secondary option

### Best secondary option if Stripe-based payments and ACH become central

Stripe Financial Connections

Reason:
- strong for balances, ownership, bank verification, and payment-linked bank setup
- transactions are supported, but the product is more naturally connected to Stripe’s financial account and payment ecosystem
- official docs describe transaction refreshes, subscriptions, and retrieval of up to the last 180 days depending on the institution

Official sources:
- [Stripe Financial Connections fundamentals](https://docs.stripe.com/financial-connections/fundamentals)
- [Stripe Financial Connections transactions](https://docs.stripe.com/financial-connections/transactions)

## Recommended product decision

Use:
- Plaid for bookkeeping transaction feeds
- Stripe Financial Connections only if you later want bank-linked payment verification, ACH setup, ownership checks, or Stripe-native bank-data workflows

## Do not do yet

- do not commit to both providers in the first implementation phase
- do not mix provider rollout with current invited-client stabilization
- do not promise live bank sync in public marketing until the provider is implemented, tested, and legally reviewed
