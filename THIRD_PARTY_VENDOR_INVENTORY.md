# LedgerFlow Third-Party Vendor Inventory

Date: 2026-04-22

Purpose:
- document the outside services the platform depends on
- support privacy, security, and release-gate review

## Current vendor inventory

### 1. Render

Role:
- application hosting
- web runtime
- persistent disk storage

Data involved:
- application database
- email runtime config
- local secret key
- server-side logs and runtime state

Configuration evidence:
- `DATA_DIR`
- production import status page
- live deployment path

Status:
- active infrastructure dependency

### 2. SMTP email provider

Role:
- outbound transactional email delivery

Current code posture:
- defaults to Gmail SMTP settings in code
- configurable through Email Settings

Data involved:
- recipient email address
- recipient name
- message subject/body
- invite/reset/billing/invoice/receipt content
- delivery status and tracking metadata

Status:
- active dependency
- current clean launch baseline is configured for Gmail SMTP
- if the live email provider changes later, this inventory and the public legal page should be reviewed again

### 3. OpenAI

Role:
- optional AI guide functionality

Current code posture:
- provider defaults to `openai`
- only active when AI settings are configured and used

Data involved:
- admin/user question
- local workflow context snapshot
- optional custom system prompt

Status:
- optional dependency
- current clean launch baseline keeps this dependency disabled
- should remain disclosed only as an optional configured processor unless enabled in live use

### 4. Hosted billing processor chosen by administrator

Role:
- external payment-method authorization and hosted billing setup

Current code posture:
- LedgerFlow stores only references and optional hosted billing links
- processor itself is not hardcoded in the app

Data involved:
- method label
- last four digits
- processor / mandate reference
- hosted billing setup URL

Status:
- external dependency by business choice / administrator setup
- exact processor name must be added to release evidence once selected for live use

## Current non-vendors / not observed as bundled integrations

These were not observed as built-in code dependencies in the reviewed source:
- direct bank-feed provider
- analytics / ad tracking vendor
- SMS vendor
- customer support SaaS widget
- cloud object-storage SDK
- direct embedded checkout SDK

## Release-note guidance

Before public launch, confirm and document:
1. whether the live SMTP provider still matches the current Gmail SMTP baseline
2. whether the optional AI guide is enabled in production
3. which hosted billing processor the administrator actually uses for live businesses

That final confirmation should be folded back into:
- `LIVE_COMPLIANCE_GAP_REPORT.md`
- the public privacy notice if naming vendors is part of the chosen disclosure approach
