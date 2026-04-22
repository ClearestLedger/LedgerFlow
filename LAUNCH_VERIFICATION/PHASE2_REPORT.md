# Phase 2 Access Control and Tenant Isolation Report

Generated: 2026-04-22 17:06:14

## Result

- Admin supervision checks passed: 2/2
- Business isolation checks passed: 8/8
- Worker boundary checks passed: 6/6
- Public document isolation checks passed: 3/3
- Overall pass: YES

## Seeded Tenants

- Alpha business: Phase 2 Alpha Painting LLC (phase2.alpha@ledgerflow.local)
- Beta business: Phase 2 Beta Cleaning LLC (phase2.beta@ledgerflow.local)
- Alpha worker: Alpha Worker (phase2.worker.alpha@ledgerflow.local)

## Admin Login

- Status: 302
- Redirect: /legal-acceptance?next=/cpa-dashboard

## Alpha Login

- Status: 302
- Redirect: /legal-acceptance?next=/dashboard

## Beta Login

- Status: 302
- Redirect: /legal-acceptance?next=/dashboard

## Worker Login

- Status: 302
- Redirect: /worker-portal/time-summary

## Admin Supervision

- PASS | Admin opens Alpha Billing Center | /business-payments?client_id=1 | status=200 | final=/business-payments | expected_text_found=True | final_path_ok=True
- PASS | Admin opens Beta Billing Center | /business-payments?client_id=2 | status=200 | final=/business-payments | expected_text_found=True | final_path_ok=True

## Business Isolation

- PASS | Alpha own billing center | /business-payments | status=200 | final=/business-payments | expected_text_found=True | forbidden_text_absent=True | final_path_ok=True
- PASS | Alpha tries Beta billing center | /business-payments?client_id=2 | status=200 | final=/business-payments | expected_text_found=True | forbidden_text_absent=True | final_path_ok=True
- PASS | Alpha tries Beta owner view | /dashboard?client_id=2 | status=200 | final=/dashboard | expected_text_found=True | forbidden_text_absent=True | final_path_ok=True
- PASS | Alpha tries Beta clients and sales | /clients-sales?client_id=2 | status=200 | final=/clients-sales | expected_text_found=True | forbidden_text_absent=True | final_path_ok=True
- PASS | Alpha blocked from admin dashboard | /cpa-dashboard | status=403
- PASS | Beta own billing center | /business-payments | status=200 | final=/business-payments | expected_text_found=True | forbidden_text_absent=True | final_path_ok=True
- PASS | Beta tries Alpha billing center | /business-payments?client_id=1 | status=200 | final=/business-payments | expected_text_found=True | forbidden_text_absent=True | final_path_ok=True
- PASS | Beta tries Alpha reports | /reports?client_id=1 | status=200 | final=/reports | expected_text_found=True | forbidden_text_absent=True | final_path_ok=True

## Worker Boundaries

- PASS | Worker opens own time summary | /worker-portal/time-summary | status=200 | final=/worker-portal/time-summary | expected_text_found=True | final_path_ok=True
- PASS | Worker opens own pay stub | /worker-portal/pay-stubs/1 | status=200 | final=/worker-portal/pay-stubs/1 | expected_text_found=True | final_path_ok=True
- PASS | Worker blocked from other business pay stub | /worker-portal/pay-stubs/2 | status=404
- PASS | Worker blocked from business dashboard | /dashboard?client_id=1 | status=302 | location=/login
- PASS | Worker blocked from admin dashboard | /cpa-dashboard | status=302 | location=/login
- PASS | Business user blocked from worker portal pay stub route | /worker-portal/pay-stubs/1 | status=302 | location=/worker-login

## Public Document Isolation

- PASS | Public alpha invoice token resolves only alpha invoice | /customer-invoice/phase2-alpha-public-token | status=200 | final=/customer-invoice/phase2-alpha-public-token | expected_text_found=True | forbidden_text_absent=True | final_path_ok=True
- PASS | Public beta invoice token resolves only beta invoice | /customer-invoice/phase2-beta-public-token | status=200 | final=/customer-invoice/phase2-beta-public-token | expected_text_found=True | forbidden_text_absent=True | final_path_ok=True
- PASS | Invalid public invoice token returns not found | /customer-invoice/not-a-real-token | status=404
