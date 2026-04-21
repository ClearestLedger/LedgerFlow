# LedgerFlow Phase Queue

## Approved and Locked

- Phase 1: Save Email Settings
- Phase 2: Save Business and Team Member Information
- Phase 3: Business benefits and employer obligations guide with official live links
- Email settings correction: test-email flow now uses the saved LedgerFlow profile as the source of truth when sending a test email.

## Immediate Corrections Completed

- Business email links now normalize the saved base URL correctly.
- Terminated team members lose portal access immediately.
- Canceled or archived businesses are redirected to the comeback page.
- Large forms such as New Business Profile and Email Settings are folded by default.
- Local email encryption now uses a persistent secret key so saved SMTP passwords survive app restarts.
- Invite and test-email failures now show the real cause instead of the generic "Check Email Settings" message.

## Queued Premium Notes

- Live launch priorities re-stabilized on 2026-04-21:
  - 1. Language stability first: keep admin, business, and worker language preferences separate, editable, and enrollment-aware.
  - 2. Finish page-by-page language coverage for the real live client path before broader polish.
  - 3. Verify live email links and business-facing email delivery again after language stabilization.
  - 4. Finalize legal/trust wording and footer coverage for real-client use.
  - 5. Run a full live launch audit and create a fresh hard lock before the next major phase.
- Hard lock rule: create a dated hard backup before each major live-build phase and again after each approved phase.
- Add premium watermark-style marketing quotes, business tips, or trust-building microcopy inside the folded Business Profile area.
- Research the best marketing direction first, then implement a master elite prime presentation instead of generic filler text.
- Treat this as a branded UX phase, not just a decoration pass.
- Revisit AI Guide visual presence later as a dedicated correction phase.
- Current issue to solve later: the live assistant still feels visually static to the user even after multiple motion passes, so it needs a stronger, unmistakable premium-presence redesign rather than more subtle animation tweaks.
- Translator phase follow-up correction: sidebar and shared shells are translating, but more business pages and forms still need full language coverage beyond the navigation rail.
- Language Phase 2 completed on 2026-04-21 for the real business-client path:
  - shared business shell and workspace navigation
  - dashboard
  - welcome center
  - billing center
  - trust / legal page
  - business setup category / structure / tier option labels
  - business profile language edit path
- Language Phase 3 completed on 2026-04-21 for the deeper business workspace surfaces:
  - summary center
  - report center
  - clients and sales
  - invoices and income
  - estimates
  - premium sales workflow wording and copy-link controls
- Language hardening phase completed on 2026-04-21 for login and recovery flows:
  - per-login language changes no longer overwrite the saved business default language
  - guest business invite and rejoin pages now seed from the business default language
  - login, worker login, create-account, forgot-password, reset-password, comeback, and rejoin surfaces now have stronger translation coverage and cleaner password-toggle language handling
- Next language follow-up: verify live email surfaces and the remaining deeper administrator-only pages after the new business workspace translations are deployed.
- Active palette source of truth for the current visual refinement pass:
  - Deep Navy `#151A2C`
  - Soft Navy `#1D2336`
  - Slate Blue-Gray `#72819A`
  - Light Steel Blue `#A8B2C1`
  - Warm Ivory `#F4F2EA`
  - Soft White `#E7E8E6`
  - Clean Background White `#F8F8F6`
- Apply more white than ivory overall, keep the product bright and premium, and avoid gold or heavy warm tones.
- Use Deep Navy and Soft Navy only for key dark emphasis areas, while Soft White and Clean Background White remain the dominant light base throughout the software.
- Trial rollout follow-up: add a decline survey for businesses that choose not to subscribe after the complimentary period, focused on what would have helped them convert.
- Reports follow-up: add more intentional visual graphics/charts across reporting surfaces so reports feel more premium and easier to scan.
- Sales workspace ownership rule: saved clients, estimates, and customer invoices belong to the business-side portal experience, not the administrator-facing side.
- Admin can supervise and manage billing access, but the primary customer relationship workflow should remain attached to each business workspace.
- Business profile expansion note: add support for more than one owner under a business and more than one reusable job scope / service scope entry.
- Business profile expansion phase completed on 2026-04-21:
  - `Mobile Detailing` added as a business category option
  - administrator and business setup flows now save additional owners / owner contacts
  - administrator and business setup flows now save reusable job scope / service scope notes
- Recurring client automation phase completed on 2026-04-21:
  - businesses add saved return clients from `Clients & Sales`
  - recurring service settings can now auto-generate future work-schedule visits
  - the business sales workspace now shows next visit timing and projected recurring revenue
  - recurring visits contribute to schedule planning, but do not auto-post booked income before the work is actually completed
- Mobile readiness note:
  - phone layouts are still not launch-ready
  - mobile-only notice should stay visible while we continue mobile refinement
  - next mobile phase should focus on layout cleanup, spacing, navigation stacking, and form usability on small screens

## Future Pricing Research Note

- Research real market subscription positioning before final pricing approval.
- Consider three ready-to-go subscription levels plus a build-your-own option.
- Explore premium inclusion of live bank connection and check print tools, with lower tiers offering those as add-ons where appropriate.

## Next Planned Phase

- Phase 4: Additional welcome page
  - business name
  - user name
  - owner name
  - welcome message
  - how-to videos section placeholder for future Canva videos
