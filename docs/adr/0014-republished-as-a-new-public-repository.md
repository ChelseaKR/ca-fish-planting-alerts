# 0014. Republished as a new public repository

Status: Accepted
Date: 2026-09-18
Deciders: Chelsea Kelly-Reif

## Context

This repository was created private on 2026-09-13. Its history held business
notes that were never meant to be public: one research file, from the first
commit on, and a few passages that quoted it in `README.md`,
`docs/DECISIONS.md` and `docs/APP-STORE.md`.

Rewriting the history and force-pushing it would not have been enough.
GitHub keeps every pull request's commits reachable through
`refs/pull/N/head`, and a repository owner cannot delete those refs. All 30
pull requests carried the old history, so the notes would have stayed
readable on each pull request page after the repository went public.

The same day, after the first new repository went public, a review found
App Store search research still in `docs/APP-STORE.md` and
`docs/APP-STORE-LISTING.md`. A pull request had already been opened there,
so the same reasoning applied, and the repository was republished a second
time.

## Decision

Publish a new repository under the same name, and keep the original private.

- The original repository was renamed `ca-fish-planting-alerts-archive`. It
  stays private, with Actions disabled and Pages removed. It keeps the full
  original history, all 30 pull requests and their discussions. The first
  new repository was renamed `ca-fish-planting-alerts-archive-2` and made
  private the same way.
- The history was rewritten with `git filter-repo`. The research file was
  removed from every commit, and each passage that quoted it now reads
  `[moved to private strategy notes]`. The second rewrite removed the App
  Store search research from every commit in the same way. Authors, dates
  and commit subjects are unchanged. Every commit SHA changed both times.
- Only `main` was pushed to the new repository. It carries no pull request
  refs and no tags.
- The open issues were transferred from the original, and then again from
  the first new repository in the same order, so they are #1 to #9 here.
- A license was added at the same time: the Elastic License 2.0 for the code,
  with CDFW's data credited in `NOTICE`.

## Consequences

- The site's URL did not change:
  `https://chelseakr.github.io/ca-fish-planting-alerts/`. The daily `publish`
  job keeps committing `pipeline/data/` to `main`, and the history it records
  carried over whole.
- "PR N" in `CHANGELOG.md` and the docs means pull request N in the original
  repository, which is private. Those references are written without `#`, so
  GitHub does not link them to this repository's unrelated issues. The
  "(#N)" at the end of older commit subjects has the same meaning, and it
  cannot be changed.
- Commit SHAs quoted in documents written before 2026-09-18 name commits in
  the original history. The owner keeps the old-to-new SHA map with the
  private notes.
- Any clone made before the second republication carries old history. Push
  only from a fresh clone of this repository.
