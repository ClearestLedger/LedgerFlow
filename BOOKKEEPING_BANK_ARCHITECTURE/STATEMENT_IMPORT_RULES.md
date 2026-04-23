# Statement Import Rules

## Rule 1

CSV first.

Why:
- fastest to support
- easiest to validate
- least ambiguous

## Rule 2

Do not auto-post uploaded statement rows directly into final bookkeeping.

Every imported row should pass through:
- staging
- normalization
- user review
- reconciliation or posting

## Rule 3

Treat PDF bank statements as a later phase.

Why:
- PDF statement extraction is much less reliable than structured CSV or feed data
- OCR and layout differences create parsing risk
- users still need review even when extraction succeeds

## Rule 4

Raw imported bank data must remain preserved.

Store:
- original source file
- normalized row values
- parse warnings
- posting decision

## Rule 5

Do not silently categorize financial transactions without a visible user-review layer.

Allowed:
- suggested category
- suggested job match
- suggested vendor

Not allowed:
- hidden final posting with no review trail

## Rule 6

Imported rows must support duplicate protection.

Use a fingerprint based on values such as:
- account
- amount
- transaction date
- description
- provider transaction id when available

## Rule 7

Service-business-first mapping should exist from day one.

Useful bookkeeping suggestions:
- customer payment
- material purchase
- fuel
- payroll transfer
- subcontractor
- owner draw
- software / subscription
- rent / utilities
- uncategorized
