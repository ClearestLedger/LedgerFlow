Launch Verification

Purpose

This folder contains repeatable launch checks for LedgerFlow after the clean reset.

Phase 1 goal

- start from the clean Render migration bundle
- seed one controlled demo business
- verify administrator-supervised business routes
- verify direct business-workspace routes
- write a report before real clients are added

Main file

- `phase1_clean_launch_verify.py`
- `phase2_access_control_verify.py`

What it does

1. copies the clean reset database and runtime files from:
   - `C:\Users\danie\OneDrive\Desktop\LedgerNew_Render_Migration`
2. loads the current working app from:
   - `C:\Users\danie\OneDrive\Desktop\folder for codex\_live_sync_tmp\app.py`
3. seeds one demo business, one business login, one customer, one worker, one location, one job, and one invoice
4. logs in as administrator and as the business user
5. sweeps the core routes
6. writes:
   - `PHASE1_RESULTS.json`
   - `PHASE1_REPORT.md`

How to run

```powershell
python "C:\Users\danie\OneDrive\Desktop\folder for codex\LAUNCH_VERIFICATION\phase1_clean_launch_verify.py"
```

Pass rule

Phase 1 passes only if:

- admin login succeeds
- business login succeeds
- all supervised routes return 200 with the expected page marker
- all direct business routes return 200 with the expected page marker

Use

Run this before:

- re-adding real businesses
- making structural changes to routing
- changing operations templates
- changing owner view or business navigation

Phase 2 goal

- seed two isolated businesses on the clean reset baseline
- verify admin can supervise both cleanly
- verify one business user cannot cross into another business workspace
- verify worker routes stay isolated from business/admin routes
- verify public invoice tokens only resolve to their own documents

Phase 2 outputs

- `PHASE2_RESULTS.json`
- `PHASE2_REPORT.md`

Phase 2 pass rule

Phase 2 passes only if:

- admin can open both supervised business contexts
- business users stay pinned to their own tenant even when a foreign `client_id` is supplied
- business users are blocked from admin-only pages
- workers are blocked from business/admin pages and from other-worker pay stubs
- invalid public invoice tokens fail cleanly
