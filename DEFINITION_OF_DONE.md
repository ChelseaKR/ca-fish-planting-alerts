# Definition of Done — Trout Truck

What "done" means for a change to this repository
(`docs/standards/QUALITY-AND-METRICS-STANDARD.md`, "Definition of Done").
This file is routed to the code owner. It is reviewed quarterly and
whenever a gate is added or removed.

Last reviewed: 2026-09-17 · Recheck cadence: quarterly

## AUTO-GATE: every pull request, in CI

A change is not done while any of these is red. None of them is bypassed
by a comment, a `|| true`, or `continue-on-error`.

| # | Gate | Where it runs | Standard |
|---|------|---------------|----------|
| 1 | Lockfile drift, format, lint (complexity ≤ 10) | `make verify` → `ci.yml` `verify` | CODE-QUALITY |
| 2 | `mypy --strict`, zero errors | `make verify` | CODE-QUALITY |
| 3 | Tests, branch coverage ≥ 90%; offline fixture build of the site; wheel build | `make verify` | CODE-QUALITY |
| 4 | pip-audit and osv-scanner (0 known vulnerabilities), semgrep, gitleaks; CodeQL (python, actions) with no `error` or security-severity ≥ 7.0 result | `make verify`; `codeql.yml` | SECURITY |
| 5 | zizmor, 0 high or critical findings; every `uses:` SHA-pinned | `zizmor.yml` | CI-CD |
| 6 | axe 0 critical/serious/moderate and pa11y-ci 0 errors on every built page; no sideways scroll at 320px; Lighthouse accessibility ≥ 0.90 | `site-checks.yml` | ACCESSIBILITY |
| 7 | i18n | N/A until Spanish is in scope (`docs/I18N.md`, #6) | I18N |
| 8 | ai-eval | N/A: no model, prompt or retrieval surface | AI-EVALUATION |
| 9 | observability: the publish run prints its coverage line; a failed or timed-out run opens an issue | `publish.yml` | OBSERVABILITY |
| 10 | Lighthouse performance ≥ 0.90, lab Core Web Vitals and script budgets, ≤ 10% regression against `perf/baseline.json` | `site-checks.yml` | PERFORMANCE |
| 11 | Swift package tests for the app's data layer | `ci.yml` `ios` | CODE-QUALITY |

`make verify` runs gates 1-4 locally, in the same way CI does.
`tools/site-checks/run.sh` runs gates 6 and 10.

## REVIEW-GATE: the owner's decision, recorded in the PR

- The PR says what changed and why, links its issue, and names the ISO
  25010 characteristic(s) it touches (functional suitability, reliability,
  security, interaction capability…).
- Docs updated: README, `pipeline/README.md`, `schema/README.md`,
  CHANGELOG, as relevant.
- A change to the snapshot contract (`schema/`) or to what gets written to
  `pipeline/data/` carries a rollback plan. The app decodes the contract
  strictly, and the history is append-only.
- A new external surface (a new fetched source, a new third-party script,
  a new endpoint the app calls) adds a data card or updates the threat
  model and privacy audit in `docs/RESPONSIBLE-TECH-AUDITS.md`.
- A new interactive element on the site or in the app gets a keyboard
  and screen-reader check.
- An expensive-to-reverse decision adds an ADR in `docs/adr/`.

## RELEASE-GATE: an App Store build or a release tag

Release machinery does not exist yet (#3). Until it does, an App Store
submission needs, at minimum:

- a green `main` at the commit the build is made from, recorded with the
  build number;
- the app's accessibility walkthrough (#5) done or explicitly accepted as
  open;
- the App Store privacy label matching `PrivacyInfo.xcprivacy`;
- a CHANGELOG entry for what users will see.

## Merging

There is one maintainer. A pull request merges when every required check
is green and the owner decides to merge it. That decision is the review
(`docs/standards/CODE-QUALITY-STANDARD.md` §7.1). Branch protection that
makes this mechanical is open in #4.
