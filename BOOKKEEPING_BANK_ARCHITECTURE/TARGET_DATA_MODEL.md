# Target Data Model

## Current problem

The current `invoices` table is overloaded.

It is holding:
- estimates
- customer invoices
- bookkeeping-only income records

That is workable for launch, but not safe enough for a full bookkeeping leg.

## Required target split

### 1. Sales documents domain

Keep customer-facing sales documents separate:

- `sales_estimates`
- `sales_estimate_line_items`
- `sales_invoices`
- `sales_invoice_line_items`
- `sales_receipts`
- `sales_document_events`

Purpose:
- customer communication
- hosted estimate pages
- hosted invoice pages
- reminder history
- payment-link history

### 2. Bookkeeping ledger domain

Create the internal bookkeeping engine:

- `ledger_accounts`
- `ledger_journal_entries`
- `ledger_entry_lines`
- `ledger_period_closes`
- `ledger_source_links`

Purpose:
- internal finance truth
- debits and credits
- source traceability
- period-based reporting

Minimum account groups for launch:
- cash
- accounts receivable
- income
- materials expense
- labor expense
- fuel / mileage
- other operating expense
- owner draws / adjustments

### 3. Bank connection domain

- `bank_connections`
- `bank_accounts`
- `bank_sync_runs`
- `bank_transactions`
- `bank_transaction_events`

Purpose:
- provider link state
- connected account metadata
- sync cursor / refresh state
- raw bank transaction storage
- audit trail for transaction changes

### 4. Statement import domain

- `statement_import_batches`
- `statement_import_files`
- `statement_import_rows`
- `statement_parse_warnings`

Purpose:
- CSV / OFX / later PDF upload handling
- staging before ledger posting
- parser warnings
- retryable import runs

### 5. Reconciliation domain

- `reconciliation_sessions`
- `reconciliation_matches`
- `reconciliation_exceptions`

Purpose:
- match bank transactions to ledger or sales items
- flag duplicates
- hold unresolved items
- preserve user review decisions

### 6. Expense evidence domain

- `expense_records`
- `expense_attachments`
- `vendor_contacts`

Purpose:
- track expenses separately from bank imports
- hold receipt images or uploaded files
- support manual plus imported expense workflows

## Job-profit relationship

Jobs already contain:
- revenue
- materials cost
- labor cost
- other cost

That should remain the operational profit layer.

But jobs should also be able to create linked ledger events:
- recognize revenue
- recognize direct costs
- support per-job profit reporting

## Golden rule

No raw bank import should post directly into final bookkeeping without a reviewable source path.

The safe sequence is:
- ingest
- normalize
- stage
- reconcile
- post to ledger
