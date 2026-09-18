# perf/

The performance gate for the built site (`docs/standards/PERFORMANCE-STANDARD.md`).
`tools/site-checks/run.sh` runs it, locally and in `.github/workflows/site-checks.yml`.

| File | What it is |
|---|---|
| `lighthouserc.json` | Lighthouse CI assertions. The URLs are passed in by `run.sh`, because the port is chosen at run time. |
| `baseline.json` | The committed comparand for the >10% regression rule (PERF-03), with the commit, date, environment and tool versions it was measured with. |

## Budgets

| Budget | Value | Why |
|---|---|---|
| Lighthouse performance | ≥ 0.90, median of 3 runs | PERF-02 |
| Lighthouse accessibility | ≥ 0.90, median of 3 runs | A11Y-02 |
| Largest Contentful Paint | ≤ 2,500 ms | OBS-23 |
| Cumulative Layout Shift | ≤ 0.1 | OBS-25 |
| Total Blocking Time | ≤ 200 ms | The lab stand-in for INP (OBS-24). INP needs a real user's input, so it can't be measured in a lab run. |
| Script transfer, first-party | ≤ 45,056 B | See below |

**The script budget accounts for Google Analytics without contacting it.**
PERFORMANCE-STANDARD caps critical-path script at 204,800 B. Every page
carries the GA4 tag (`docs/DECISIONS.md` 0011). For a visitor who does not
send Global Privacy Control or Do Not Track, the tag loads `gtag.js`, which
measured 154,391 B over brotli on 2026-09-17. The gate run blocks Google
Analytics, so CI never sends page views to the real property. The
first-party budget is therefore what's left of the 204,800 B, rounded down
with some headroom for `gtag.js` growing: 45,056 B. Today the site loads
no first-party script file at all. Its only script is the small inline GA4
guard in each page's HTML.

**The baseline's `js_kb_gzip` is 0.** The regression rule allows 10% worse
than the baseline, and 10% of 0 is 0. So a pull request that adds any
script file fails PERF-03 until the same PR updates `baseline.json`, which
is the baseline-update ritual in PERFORMANCE-STANDARD §2. That is
deliberate: a script file on this site is a decision.

## The checkers' own dependencies

`tools/site-checks/package.json` pins pa11y-ci 4.1.1, @lhci/cli 0.15.1,
puppeteer 24.43.1 and @axe-core/puppeteer 4.13.0, and `package-lock.json`
locks the rest. As published, that tree carries HIGH advisories in two
places. One is `extract-zip`, reached through `@puppeteer/browsers` 2.x,
which unzips the Chrome download. The other is `tmp`, reached through
`@lhci/cli`'s interactive wizard. `overrides` moves `@puppeteer/browsers`
to 3.2.2, which no longer uses `extract-zip`, and `tmp` to 0.2.7. The full
gate was re-run on the overridden tree and passes. `run.sh` starts with
`npm audit --audit-level=high`, so a HIGH or CRITICAL with a fix fails the
run. Two moderate advisories remain, and they have no fix that these
versions accept.

Overriding `puppeteer` itself to 25.x was tried first and rejected. With it,
`lighthouse` 12.6.1 did not finish its first run.

## N/A

- **k6 latency (PERF-01): N/A.** GitHub Pages serves the site as static
  files. This repository runs no server route whose latency it controls.
- `p95_ms` and the two LLM metrics in `baseline.json` are `null`, which is
  the declared N/A, for the same reason, and because the product has no
  model.

## Updating the baseline

Follow PERFORMANCE-STANDARD §2. When the numbers improve, update the
baseline in the same PR. When a regression is intentional, the owner signs
off in the PR that causes it. When the tools change (Lighthouse or Chrome),
re-baseline in a PR titled as a re-baseline, with the before and after
numbers. `perf/` is routed to the code owner.
