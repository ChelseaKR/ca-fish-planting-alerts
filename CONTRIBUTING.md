# Contributing

## The local gate

```sh
make verify
```

`make verify` is the single local gate. CI's `verify` job runs the same
target and nothing else, so a green `make verify` on your machine makes the
same claim as the green check on a pull request
(`docs/standards/CI-CD-STANDARD.md` §9). It runs, in order: lockfile drift,
format, lint, strict type checks, tests with a branch-coverage floor, an
offline build of the site from a fixture, the wheel build, a dependency
audit, semgrep, gitleaks, and a hygiene check.

It needs `uv`, `gitleaks` and `osv-scanner` on your `PATH`. On macOS:

```sh
brew install uv gitleaks osv-scanner
```

The Swift package has its own gate:

```sh
cd ios/PlantingCore && swift test
```

The site's accessibility and performance gates (axe, pa11y-ci, Lighthouse
CI, and the `perf/` baseline) run over a build of the site. They need Node
22 or newer, and Chrome from puppeteer:

```sh
(cd tools/site-checks && npm ci && npx puppeteer browsers install chrome)
tools/site-checks/run.sh
```

Optional pre-commit hooks catch problems before a commit exists:

```sh
pre-commit install --hook-type pre-commit --hook-type pre-push
```

## Pull requests

- All work lands through a pull request into `main`. The one exception is
  the daily publish job, which commits `pipeline/data/*.json` itself.
- Every required check must be green before merge. There is one
  maintainer, so merging is the owner's decision on a green head
  (`docs/standards/CODE-QUALITY-STANDARD.md` §7.1).
- Commit subjects are lowercase conventional commits, for example
  `fix(pipeline): …`, `docs: …`, `ci: …`.
- Stage files by name. Never `git add -A`, and never `git add .`.
- A pull request that changes a workflow, a threshold, the data contract in
  `schema/`, or `pipeline/data/` goes to the code owner (`.github/CODEOWNERS`).
  If it makes an expensive-to-reverse decision, it adds an ADR.

## Decisions

Decisions are recorded in `docs/adr/`, one file each, numbered and never
rewritten (`docs/adr/0000-record-architecture-decisions.md`). The older
decisions stay in `docs/DECISIONS.md`.

## Standards

This repository follows the portfolio standards. A copy is vendored,
unedited, in `docs/standards/` and pinned in
`docs/standards/.standards-version`. Renovate bumps the pin. Never edit the
vendored files by hand. The
[Standards Conformance table](README.md#standards-conformance) in the README
says which standards apply here, and where each one has an open gap.
