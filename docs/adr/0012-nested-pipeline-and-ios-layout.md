# 0012. Keep the nested pipeline/ and ios/ layout; gate it from a root Makefile

Status: Accepted
Date: 2026-09-17
Deciders: Chelsea Kelly-Reif

## Context

`CODE-QUALITY-STANDARD.md` §4 expects one root `pyproject.toml`, `tests/` at
the repository root, and no monorepo-style nesting unless an ADR declares
it (CQ-24, CQ-25, CQ-26). This repository holds two products built with two
toolchains:

- `pipeline/`: a Python project (uv, pytest) that fetches CDFW's schedule,
  keeps the history, and builds the snapshot and the static site.
- `ios/`: a SwiftUI app and its `PlantingCore` Swift package.

A third directory, `schema/`, holds the snapshot contract both of them use.

The daily publish workflow commits `pipeline/data/history.json` and
`pipeline/data/aliases.json` to `main` and runs the pipeline from
`pipeline/`. `CI-CD-STANDARD.md` §9 allows a nested project to expose its
gates through a root `Makefile` that delegates to it, as an alternative to
moving its configuration to the root.

## Decision

Keep `pipeline/` and `ios/` as they are. The Python project keeps its
single `pyproject.toml`, `uv.lock` and `tests/` inside `pipeline/`. The
repository root carries a `Makefile` whose `verify` target runs every
stage 1-5 gate against `pipeline/` (plus the repository-wide secret scan
and hygiene checks), and `.github/workflows/ci.yml` runs `make verify`.

Moving the Python project's configuration to the root was rejected. The
live publish workflow reads and commits paths under `pipeline/` every day,
and the move would put the Python configuration beside the Swift project
for no change in what is checked.

## Consequences

- `make verify` at the root is the single local gate, and CI runs the same
  target.
- `conformance_check.py` looks for `tests/` and `pyproject.toml` at the
  root, so its `tests_directory` control reports this repository as
  failing and it does not score the Python floors (coverage, lockfile,
  version pin). That is a limit of what the checker can see. It is not a
  missing test suite: `pipeline/tests/` runs in every `make verify`, and
  the floors are in `pipeline/pyproject.toml`.
- The Swift package is gated separately by the `ios` job in `ci.yml`.
