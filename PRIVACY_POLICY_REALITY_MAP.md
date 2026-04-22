# LedgerFlow Privacy Policy Reality Map

Date: 2026-04-22

Purpose:
- map what LedgerFlow actually collects and stores today
- compare those behaviors to what the live legal pages should disclose
- identify where external processors are involved

## 1. Account and access data

Primary sources:
- `users`
- `legal_acceptances`
- Flask session data

Examples:
- email
- password hash
- full name
- role
- linked business ID
- preferred language
- legal acceptance versions and timestamps
- session preference state such as preferred language and CSRF/session markers

Purpose:
- authentication
- role-based routing
- legal acceptance tracking
- session continuity

External sharing:
- none by default
- may be included in outbound email workflows only when a business or worker email is used for account notices

## 2. Business profile data

Primary sources:
- `clients`
- `client_profile_history`

Examples:
- business name
- business type / category / specialty
- contact name
- phone
- email
- address
- EIN and payroll-contact references
- subscription tier and status
- business language preference
- onboarding state
- archive/reactivation metadata

Purpose:
- business workspace setup
- administrator supervision
- subscription and onboarding management
- payroll / reporting context

External sharing:
- SMTP provider for invite, onboarding, billing, and support emails

## 3. Customer relationship and sales-document data

Primary sources:
- `customer_contacts`
- `invoices`
- `invoice_line_items`
- `invoice_mileage_entries`
- `service_locations`
- `service_types`
- `job_templates`

Examples:
- customer names
- customer emails and phone numbers
- service addresses
- invoice / estimate details
- line items
- public customer-view tokens
- optional public payment links

Purpose:
- client list
- estimates
- customer invoices
- hosted customer view pages
- recurring customer workflow

External sharing:
- SMTP provider for invoice / estimate / receipt email delivery
- customer browser access through public estimate / invoice links
- optional hosted external payment page only if an admin/business user pastes a payment URL

## 4. Worker and payroll-related data

Primary sources:
- `workers`
- `worker_profile_history`
- `worker_payments`
- `worker_time_entries`
- `worker_time_off_requests`
- worker tax / pay-stub rendering routes

Examples:
- worker name
- address
- phone
- email
- preferred language
- SSN
- hours worked
- payment amounts and references

Purpose:
- team management
- payroll context
- pay-stub and tax-form generation
- worker portal access

External sharing:
- SMTP provider when worker login or notification emails are sent

## 5. Operations and scheduling data

Primary sources:
- `work_schedule_entries`
- `jobs`
- `job_assignments`
- `worker_availability`
- `job_activity_log`
- reminder tables

Examples:
- scheduled dates and times
- job titles
- service scope
- assigned workers
- addresses
- internal notes
- job revenue and cost fields

Purpose:
- dispatch
- agenda / scheduling
- team coordination
- job-profit workflow
- operational history

External sharing:
- none by default

## 6. Messaging and support data

Primary sources:
- `internal_messages`
- `worker_messages`
- `email_delivery_log`
- `business_invites`
- `account_activity_log`

Examples:
- internal admin/business chat content
- worker/manager messages
- invite email metadata
- email delivery status
- tracking tokens
- message timestamps

Purpose:
- administrator support
- invite management
- email history
- basic audit and activity visibility

External sharing:
- SMTP provider for outbound mail
- recipient mailbox providers when emails are delivered externally

## 7. Billing and payment-descriptor data

Primary sources:
- `clients`
- `business_payment_methods`
- `business_payment_items`

Examples:
- subscription status
- next billing date
- payment-method label
- card/bank/processor descriptor
- last four digits
- account type
- processor / mandate reference
- hosted billing setup link
- administrator fee records

Purpose:
- subscription billing management
- administrator-fee workflow
- payment-method status visibility

External sharing:
- external hosted billing processor chosen by the administrator

Important boundary:
- LedgerFlow no longer collects or stores full card numbers, routing numbers, or bank-account numbers in the business billing flow

## 8. File and import data

Primary sources:
- one-time Render migration upload route
- persistent disk storage under `DATA_DIR`

Examples:
- migration ZIP bundle
- database file
- email runtime config file
- local secret key file

Purpose:
- controlled migration / restoration
- runtime configuration

External sharing:
- none by default beyond the hosting environment

## 9. Optional AI assistant data

Primary sources:
- `ai_assistant_profile`
- outbound request to OpenAI Responses API when the AI guide is configured

Examples:
- configured provider name
- encrypted API key
- assistant model and prompt settings
- admin question
- selected local workflow context snapshot

Purpose:
- optional in-app AI guide support

External sharing:
- OpenAI API only when the AI guide is configured and used

## 10. Current external processors / environments reflected in code

1. Render
- app hosting
- persistent disk / data directory

2. SMTP mail provider
- currently defaults to Gmail SMTP in code, but settings are configurable
- used for invites, resets, billing emails, invoice emails, and related notices

3. OpenAI
- optional AI guide provider when configured

4. Hosted billing processor selected by the administrator
- not bundled directly in the codebase
- represented only through hosted setup links / authorization references

## 11. Not currently observed as bundled code dependencies

These are not currently shown as built-in platform processors in the reviewed code:
- analytics SDKs
- cookie-tracking SDKs
- Plaid or direct bank-feed providers
- Twilio / SMS provider
- Stripe Elements / embedded checkout
- file-scanning vendor

## 12. Privacy-policy alignment status

Current status:
- stronger than before
- not final

What the live privacy notice should clearly continue to say:
- LedgerFlow stores business, worker, billing-reference, message, and account-access data needed to operate the portal
- customer-facing invoices and estimates may be delivered by email and public tokenized links
- hosted billing authorization occurs through an external billing processor, not by entering full bank/card numbers directly into LedgerFlow
- optional AI guide traffic goes to OpenAI only when that feature is configured and used

What still needs final signoff:
- exact third-party naming approach in the public privacy notice
- final retention / deletion language
