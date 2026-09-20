# Roadmap and metrics ledger — Trout Truck

Planned work is tracked as GitHub issues, not in this file. This file holds
what the standards ask to find in one place: the metrics ledger
(`QUALITY-AND-METRICS-STANDARD.md`, "Metrics ledger"), the declaration of
which CI stages apply (`CI-CD-STANDARD.md` §1, §10), and the observability
tier (`OBSERVABILITY-STANDARD.md` §0).

## Metrics ledger

Values are this repository's. The rigor behind each row is in the owning
standard.

| Metric | Target | Measured by | Gate | Owner |
|--------|--------|-------------|------|-------|
| Lockfile drift [CQ-09] | `uv lock --check` passes | `make verify` | AUTO | Chelsea |
| Format, lint, complexity [CQ-04, CQ-05] | 0 findings (ruff, rule set per CQ §2, complexity ≤ 10) | `make verify` | AUTO | Chelsea |
| Static typing [CQ-06] | 0 errors, `mypy --strict` | `make verify` | AUTO | Chelsea |
| Branch coverage [CQ-08] | ≥ 90% (standard floor 85%; measured 94.0% on 2026-09-17) | `make verify` (`fail_under` in `pipeline/pyproject.toml`) | AUTO | Chelsea |
| Bare markers and blanket suppressions [CQ-34, CQ-35] | 0 | `make verify` (`scripts/check_hygiene.py`) | AUTO | Chelsea |
| Dependency vulnerabilities [SEC-11, SEC-13] | 0 known, Python lock | `make verify` (pip-audit `--strict`, osv-scanner) | AUTO | Chelsea |
| SAST [SEC-07, SEC-08] | 0 semgrep findings. 0 CodeQL results at `error` or security-severity ≥ 7.0 | `make verify`; `codeql.yml` | AUTO | Chelsea |
| Secrets [SEC-17, SEC-18, SEC-19] | 0 | pre-commit; `make verify` (gitleaks); weekly TruffleHog over all tiers | AUTO | Chelsea |
| SHA-pinned `uses:` [SEC-25] | 100% | `zizmor.yml` | AUTO | Chelsea |
| Workflow SAST [CICD-19, CICD-20] | 0 high or critical | `zizmor.yml`, `codeql-actions` | AUTO | Chelsea |
| axe violations [A11Y-01] | 0 critical, serious or moderate, on every built page | `tools/site-checks/run.sh` | AUTO | Chelsea |
| pa11y-ci [A11Y-03] | 0 errors, WCAG2AA, axe runner | `tools/site-checks/run.sh` | AUTO | Chelsea |
| Reflow at 320px [A11Y-09] | no page scrolls sideways | `tools/site-checks/run.sh` | AUTO | Chelsea |
| Lighthouse accessibility [A11Y-02] | ≥ 0.90 | `tools/site-checks/run.sh` | AUTO | Chelsea |
| Lighthouse performance and budgets [PERF-02, OBS-23, OBS-25] | ≥ 0.90; LCP ≤ 2.5 s; CLS ≤ 0.1; TBT ≤ 200 ms; first-party script ≤ 45,056 B | `tools/site-checks/run.sh` (`perf/lighthouserc.json`) | AUTO | Chelsea |
| Regression against baseline [PERF-03] | ≤ 10% worse on any metric | `perf/baseline.json` | AUTO | Chelsea |
| Snapshot valid against contract [DG-03] | every run | `cfpa` refuses to publish an invalid snapshot | AUTO | Chelsea |
| Stale or failed daily run surfaced [DG-04] | a failed or timed-out publish opens an issue | `publish.yml` `alert-on-failure` | AUTO | Chelsea |
| Screen-reader and keyboard walkthrough [A11Y-11, A11Y-12] | per release | committed walkthrough record | REVIEW, gap #5 | Chelsea |
| Threat model and residual risks [QM-14, RTF-06] | per new surface | `docs/RESPONSIBLE-TECH-AUDITS.md` §F | REVIEW, gap #9 | Chelsea |

## CI stages 6-8

| Stage | State |
|-------|-------|
| 6 a11y | Applies. `site-checks.yml` runs axe, pa11y-ci and Lighthouse over every page the pipeline builds from the fixture. The review gates are open in #5. |
| 7 perf | Applies. Lighthouse CI budgets and the baseline in `perf/`. k6 (PERF-01) is N/A: GitHub Pages serves static files, and this repository runs no server route whose latency it controls. |
| 8 responsible | Applies. The product's honesty rules are unit tests in `make verify`. A stale or failed fetch is refused and never published as "no plants this week". The history never loses or rewrites a recorded plant. A plant that ages off the page is not recorded as canceled. The site shows the date CDFW's schedule was last checked. There is no AI component, so there are no eval gates. |

## Observability

**Tier: B + C.** The website is a Tier B surface. The pipeline and the iOS
app are Tier C.

- **Website (Tier B).** The lab Core Web Vitals budgets (LCP, CLS, and TBT
  as the stand-in for INP) are gated by Lighthouse CI on every PR. Field CWV
  (RUM): gap, #7. Browser OTel spans and `traceparent`: N/A, because the
  pages make no API calls. They are static HTML, and the only script is the
  GA4 tag.
- **Pipeline (Tier C).** It runs as the scheduled `publish` job. Every run
  prints a coverage line with paired numbers (waters this week against
  waters known, names matched against names seen, rows parsed, weeks of
  history) and lists every unmatched water name. A failed or timed-out run
  opens an issue. OTel is out of scope for the CLI tier. There is no opt-in
  `--log-format json` yet: gap, #7.
- **iOS app (Tier C).** No telemetry, by decision (`docs/DECISIONS.md`
  0011: the app collects nothing). Its state is on the device only.
- SLOs, burn-rate alerts and health probes are Tier A controls: N/A. There
  is no hosted service.

## Scoping: N/A declarations

These mirror the README's Standards Conformance table.

- **AI Evaluation: N/A.** There is no model, prompt, or retrieval surface
  anywhere in the pipeline, the site or the app.
- **Performance, k6 (PERF-01): N/A.** Static hosting. See CI stage 7 above.
- **Observability Tier A controls: N/A.** No hosted service.
