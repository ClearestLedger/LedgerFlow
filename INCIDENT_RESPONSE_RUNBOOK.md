# LedgerFlow Incident Response Runbook

Date: 2026-04-21

Purpose:
- provide a minimum documented response flow for security, privacy, access-control, and data-handling incidents
- support the legal release gate with a real operational document

## Incident categories

1. Account / access incident
- suspected cross-tenant access
- unauthorized admin access
- password-reset abuse
- worker or business account misuse

2. Data exposure incident
- financial/business data exposed to the wrong tenant
- exported file contains foreign data
- email sent to the wrong recipient

3. Payment / billing incident
- payment-method data exposure
- unintended billing collection
- payment-link misuse

4. Infrastructure / service incident
- Render outage
- deployment introduces broken auth or data risk
- email delivery provider failure

## Response steps

### 1. Detection
- capture who reported the incident
- record time discovered
- record affected environment: local, staging, or live
- record affected business / user / worker / invite if known

### 2. Triage
- determine severity:
  - Sev 1: cross-tenant exposure, payment-data exposure, or live auth bypass
  - Sev 2: single-tenant data leak, broken access flow, incorrect invoice / estimate delivery
  - Sev 3: contained bug with low data risk

### 3. Containment
- stop new risky actions first
- if needed:
  - pause new invites
  - disable affected route
  - revoke access for impacted user
  - roll back to last hard lock
  - suspend payment workflow if billing data is implicated

### 4. Preservation
- keep logs, screenshots, request details, and impacted record IDs
- do not delete evidence during initial containment
- preserve the last known good hard-lock package

### 5. Investigation
- identify:
  - what data was affected
  - which tenants were affected
  - what code path caused it
  - whether the issue is ongoing or historical

### 6. Communication
- escalate internally to product owner / administrator immediately
- if customer data was impacted:
  - list affected businesses and users
  - prepare a plain-language customer notice draft
  - preserve dates and scope for legal review

### 7. Remediation
- patch the root cause
- verify with targeted regression tests
- create a new hard lock after the fix
- document follow-up actions in the project queue

### 8. Post-incident review
- what happened
- why it happened
- what evidence exists
- what customer communications were required
- what process or architecture change prevents recurrence

## Minimum evidence to collect
- affected route / page
- affected tenant or user IDs
- timestamps
- logs / screenshots
- whether data crossed tenant boundaries
- whether financial or payment-related data was involved

## Ownership placeholders

Until a fuller governance document exists, the minimum owners are:
- Product / release owner: Danielle
- Engineering / implementation owner: active Codex workspace thread
- Legal / compliance reviewer: external adviser when required

## Release note

This runbook is an initial operational baseline.
It does not replace legal breach-notification advice or a formal security program.
