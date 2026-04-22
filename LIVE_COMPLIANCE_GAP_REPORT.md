# LedgerFlow Live Compliance Gap Report

Date: 2026-04-22

Purpose:
- keep LedgerFlow as one unified all-in-one platform
- document the current release-gate status honestly
- identify what is already present, what is partial, and what is still blocking release under the legal checklist

Current release decision:
- BLOCK RELEASE

Why the release is still blocked:
1. Privacy and evidence mapping are not yet complete enough to prove that disclosures match real collection, storage, and sharing behavior.
2. Cross-tenant and role-boundary evidence has not been assembled into a formal release package yet.
3. Third-party vendor inventory and AI-output review artifacts are still incomplete for a final release signoff.

## Pass / Fail Snapshot

### 1. Legal page presence
- Terms of Use page exists: PASS
- Privacy Notice page exists: PASS
- Disclaimer page exists: PASS
- Footer and login links present: PASS

### 2. Terms acceptance / consent
- Mandatory acceptance before signup / onboarding: PASS
- Acceptance stored with user ID, timestamp, policy version, method: PASS
- Re-acceptance after material policy change: PASS

### 3. Positioning / claims
- Product still positioned as a tool, not a CPA replacement: PARTIAL
- Explicit disclaimer now added: PASS
- AI / system outputs still need a dedicated red-team review for advice-style language: FAIL

### 4. Product boundary
- Core tool behavior is still record / organize / summarize oriented: PASS
- Autonomous regulated actions are not intentionally running: PASS

### 5. Payment / billing architecture
- Billing terms visibility before payment: PARTIAL
- Business-side billing now stores labels, last four digits, and hosted billing references instead of full card / bank-account numbers: PASS
- Payment architecture moved to processor-hosted authorization references, but final vendor-specific release evidence is still needed: PARTIAL

### 6. Privacy notice alignment
- Privacy notice page exists: PASS
- Privacy policy to actual data-map comparison is not fully documented: FAIL
- Third-party processor inventory is not fully documented in release artifacts: FAIL

### 7. Data minimization
- Some optional fields are clearly marked optional: PASS
- Payment / sensitive-data minimization improved through hosted-billing references and last4-only storage on the business billing path: PASS

### 8. Authentication / access control
- Protected routes require authentication: PASS
- Role-based routing exists for admin, business user, and worker: PASS
- Formal adversarial test evidence is still needed: FAIL

### 9. Multi-tenant / data isolation
- Tenant-specific route checks exist in code: PARTIAL
- Formal cross-tenant test evidence package is still missing: FAIL

### 10. Security baseline
- HTTPS / Render deployment expected for live use: PARTIAL
- Secrets should not be exposed client-side: PARTIAL
- Upload / file security evidence package is still missing: FAIL

### 11. Audit / logging
- Email delivery and some operational events are logged: PARTIAL
- Terms acceptance logging now exists: PASS
- Formal critical-event audit review is still needed: FAIL

### 12. Incident readiness
- Initial internal runbook created: PASS
- Owners, rehearsal, and customer-notification workflow still need to be finalized: PARTIAL

### 13. Retention / deletion
- Some archive / delete flows exist in product behavior: PARTIAL
- Formal retention rules and deletion policy are still missing: FAIL

### 14. Third-party / vendor inventory
- Hosting / email / deployment are known operationally: PARTIAL
- Formal vendor inventory document tied to privacy notice is still missing: FAIL

### 15. AI / automation
- Needs explicit adversarial review before release signoff: FAIL

### 16. Marketing / website QA
- Marketing claims still need a final truth-to-product pass after the newest invoice / estimate / client workflow changes: PARTIAL
- Unsupported security or compliance superlatives must stay removed: PASS

## Required next compliance phases

1. Add mandatory Terms + Privacy acceptance with versioned server-side logging.
2. Finish the release evidence package:
   - legal-page screenshots
   - signup / acceptance video
   - DB proof of policy acceptance logging
   - proof that business billing stores labels / last4 / hosted references only
   - access-control test results
   - tenant-isolation test results
   - privacy-policy-to-data-map comparison
   - AI red-team prompt results
3. Finalize the vendor inventory and privacy-policy reality map.
4. Run the full release-gate checklist again only after those blockers are fixed.

## Product rule preserved

LedgerFlow remains:
- one unified all-in-one platform for small businesses
- role-separated between admin, business user, and worker
- business-owned for customer relationship workflow

The architecture needs to get cleaner and safer.
The product vision should not be reduced.
