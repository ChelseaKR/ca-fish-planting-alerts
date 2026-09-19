# Responsible-Tech Audits — Trout Truck

This applies `docs/standards/RESPONSIBLE-TECH-FRAMEWORK.md` to this
repository. It records what is true of the product today and which
commitments are enforced by CI (AUTO) or by a person (REVIEW).

**Status: the audit facts are recorded. Every owner sign-off is pending
(#9).** The REVIEW-GATEs below are the owner's to give. Nothing in this file
signs off on her behalf.

Last regenerated: 2026-09-17

## Applicability

- A Ethics: applies.
- B Bias: applies (lite). Nothing ranks or classifies people. The
  segments that matter are geographic coverage and language.
- C Privacy: applies. The app collects nothing, but the website runs
  Google Analytics 4 (DECISIONS 0011).
- D Transparency: applies. Every page makes claims about a state agency's
  schedule.
- E Accessibility: applies. Site and app. Gates and open work are in
  `docs/standards/ACCESSIBILITY-STANDARD.md` and #5.
- F Security: applies.
- AI-EVAL: N/A. There is no model, prompt or retrieval surface anywhere in
  the pipeline, the site or the app.
- I18N: applies, deferred. See `docs/I18N.md` and #6.

## A. Ethics

- **Who is affected.** California anglers are the users. CDFW is the
  source, and this product is not affiliated with it. People at stocked
  waters are also affected, because a planting alert can bring more
  anglers to a small water in the same week.
- **Who could be hurt if this works exactly as intended?** Mostly small
  waters, where more anglers can mean more crowding and harvest. CDFW
  already publishes the same schedule publicly, so the product adds speed
  and history, not new information.
- **Worst plausible failure.** Showing a plant that isn't happening, or
  hiding one that is. Mitigations: plants are shown only as "the week of
  <date>" and "scheduled, not confirmed". A stale or failed fetch is
  refused, not published as "no plants this week". A plant that ages off
  CDFW's page is not recorded as canceled.
- **Non-goals.** This is not CDFW, not a source of fishing regulations or
  licenses, not a day-level prediction, not a claim that every plant is
  listed, and it has no accounts.
- **Kill switch.** Disable `publish.yml` to stop publishing. The site and
  the app then keep the last published snapshot, and each shows the date it
  was built.
- **Accountable owner.** Chelsea Kelly-Reif.
- AUTO: the honesty rules above are unit tests in `make verify`:
  `test_fetch` (stale pages refused), `test_history` (append-only, no false
  removal), `test_parse` (a malformed table is refused).
- REVIEW: owner sign-off on this consequence scan and the non-goals.
  **Pending (#9).**

## B. Bias

- Nothing ranks, recommends or classifies people, and no sensitive
  attribute is collected or inferred.
- **Geographic coverage.** Only waters CDFW lists appear, grouped by
  CDFW's own regions. No water or region is ranked.
- **Language.** English only, which is a real gap for Spanish-speaking
  anglers (#6).
- REVIEW: representational-harm review. The content is waters and fish
  species, not people, so the expected finding is "none". The owner still
  records that finding. **Pending (#9).**

## C. Privacy (DPIA)

| Data | Where it lives | Retention | Who can access |
|---|---|---|---|
| CDFW schedule, history, aliases (L1 public) | `pipeline/data/`, the published snapshot | indefinite (DG-06) | public |
| Favorites, purchase entitlement, notification schedule | the user's device only | until the app is deleted | the user |
| Website page views (GA4) | Google Analytics property `554849409` | 14 months (property setting) | the owner |

- **The app collects nothing.** `PrivacyInfo.xcprivacy` declares no
  tracking and no collected data types. There is no analytics SDK, no
  account, and no server of its own.
- **The website** runs GA4 (DECISIONS 0011). The tag does not load under
  Global Privacy Control or Do Not Track, advertising features are off,
  and Consent Mode defaults deny ad storage everywhere and analytics
  storage in the EEA, the UK and Switzerland. A footer opt-out is
  remembered on the device (PR 31). The privacy page at `/privacy/` states
  all of this and the retention period.
- **Open:** classify the GA4 data under DATA-GOVERNANCE-STANDARD §0 (#8).
- AUTO: gitleaks in pre-commit, in `make verify`, and on the staged diff
  before the daily data commit. The GA4 guard behavior (GPC, DNT, opt-out)
  is executed in node by `test_site_analytics*.py`.
- REVIEW: DPIA sign-off. **Pending (#9).** GA4 reopened it.

## D. Transparency

- Every page and every snapshot carries CDFW attribution and "Schedule is
  subject to change; treat all plants as scheduled, not confirmed".
- Every page says when CDFW's schedule was last checked. The app's About
  screen shows when its snapshot was built.
- The site and the app both say the product is not affiliated with or
  endorsed by CDFW (`test_site.py`; the app's About screen).
- No copy claims "only", "first" or completeness (DECISIONS 0010).
- REVIEW: honesty-of-framing review of the site copy and the App Store
  listing. **Pending (#9).**

## E. Accessibility

See `docs/standards/ACCESSIBILITY-STANDARD.md`. AUTO: axe, pa11y-ci and
Lighthouse on every built page (`site-checks.yml`). REVIEW: the site and app
walkthroughs, the statement, and the third-party (GA4) audit are open in
#5.

## F. Security

**ASVS 5.0: L1 (the floor).** No authentication or authorization surface
exists. The site is static files served by GitHub Pages with no forms. The
app has no account, and its one purchase is verified by StoreKit 2
(`PurchaseManager` accepts only `.verified` transactions). L1 is met by the
AUTO-GATEs below.

**Threat model (STRIDE, by data flow)**

| Flow | Threat | Control | Residual risk |
|---|---|---|---|
| CDFW page → pipeline | Tampered or stale content; format drift | HTTPS; `robots.txt` honored; the stated-week freshness check; the parser refuses any structural surprise; the snapshot is schema-validated before anything is written | CDFW itself publishes a wrong row. That is shown as "scheduled, not confirmed". |
| CDFW text → HTML and `.ics` | Injection (XSS) through a water or species name | Jinja autoescape on every `.html.jinja`; `.ics` escaping in `site.py`; no `|safe` anywhere | Low |
| Pipeline → `main` (daily bot commit) | A secret or a wrong file committed unattended | Explicit paths, never a wildcard `git add` (checked by `make verify`); gitleaks on the staged diff; history integrity check | Low |
| Workflows → Pages | Supply-chain compromise of an action | Every `uses:` pinned to a SHA; zizmor; no cache in the deploy job; least-privilege tokens | A compromised pinned SHA. Renovate cooldown is 72 hours. |
| Site → visitor | Third-party script (gtag.js) compromised | Loads only without GPC, DNT or opt-out. No forms or credentials on the site | gtag.js is dynamic, so SRI is not possible. **Accepted by the owner?** Pending (#9). |
| Snapshot → app | Spoofed or malformed snapshot | HTTPS to an allowlisted host (`SnapshotEndpoint`, `HostAllowlistTests`); strict decoder | A wrong but well-formed snapshot from a compromised Pages deploy |

**§F declarations (SECURITY-AND-SUPPLY-CHAIN §8)**

1. ASVS level: L1.
2. Container scanning: N/A (no Dockerfile).
3. SBOM + signing: not yet. The repository is release-producing (a
   deployed site and an App Store app), and the release pipeline that
   would generate them does not exist (#3).
4. Secret management: the repository holds **no Actions secrets**.
   Workflows use only the short-lived `GITHUB_TOKEN`. Repository variables
   (`SITE_BASE_URL`, `APP_STORE_URL`, `SUPPORT_EMAIL`) are not secret. App
   Store Connect credentials never enter the repository. If a secret is
   ever added, it goes in Actions secrets, is rotated annually, and is
   revoked per INCIDENT-RESPONSE-STANDARD §4. Reviewed annually.
5. VEX: none needed. There is no unfixable HIGH or CRITICAL dependency
   advisory. The site-checks toolchain clears its HIGHs with overrides
   (`perf/README.md`).

- REVIEW: threat-model and residual-risk sign-off. **Pending (#9).**

---

Last verified: 2026-09-17 · Recheck cadence: quarterly, on every release,
and when a new source, third-party script or data flow is added.
