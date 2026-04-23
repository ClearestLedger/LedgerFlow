# Implementation Phases

## Phase A

### Internal ledger split

Goal:
- separate bookkeeping truth from customer-facing sales documents

Build:
- new ledger tables
- source-link tables
- migration path from `invoices.record_kind='income_record'`

Do not build yet:
- live bank feeds
- PDF statement parsing

Success test:
- customer invoices remain customer-facing
- internal income records move into ledger-backed bookkeeping records
- reports can read from ledger instead of mixed invoice rows

## Phase B

### Statement import staging

Goal:
- allow manual bookkeeping import without live bank linking

Build:
- CSV import first
- OFX/QFX second if needed
- PDF statement import only as a later reviewed phase

Success test:
- imported rows stay in staging
- no auto-posting into final books
- user can review and map rows before posting

## Phase C

### Reconciliation workflow

Goal:
- connect imported bank rows to invoices, expenses, and ledger entries

Build:
- match rules
- duplicate detection
- unresolved queue
- reviewed / approved posting flow

Success test:
- owner can see what matched, what did not, and why
- audit trail exists for every accepted or rejected match

## Phase D

### Live bank-feed integration

Goal:
- add live connected transaction sync after the internal finance structure is strong

Recommended order:
1. Plaid Transactions
2. optional Stripe Financial Connections support later if ACH/payment-linked bank flows become a larger priority

Success test:
- sync runs are idempotent
- edits from provider updates are traceable
- provider disconnect or relink does not corrupt books

## Phase E

### Financial reporting and close process

Goal:
- make the bookkeeping leg usable for real business review

Build:
- cash flow summary
- profit and loss view
- uncategorized items view
- reconciliation status view
- month close checklist

Success test:
- owner can understand money in, money out, open issues, and job profit without reading raw transaction tables

## Recommended timeline after current invited-client stabilization

- Phase A: 1 to 2 weeks
- Phase B: 1 week
- Phase C: 1 to 2 weeks
- Phase D: 2 to 3 weeks
- Phase E: 1 week

Practical estimate:
- bookkeeping leg without live bank feeds: about 2 to 4 weeks
- bookkeeping leg with live bank feeds and reconciliation: about 5 to 8 weeks
