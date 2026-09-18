# 0000. Record architecture decisions

Status: Accepted
Date: 2026-09-17
Deciders: Chelsea Kelly-Reif

## Context

`DOCUMENTATION-STANDARD.md` §3 asks for an ADR log at `docs/adr/`, one file
per decision, numbered, and never edited once accepted. This repository
already keeps its product decisions in a single file, `docs/DECISIONS.md`.
As of 2026-09-17 that file holds entries 0001 to 0007, 0010 and 0011.
Two different entries both carry the number 0007: the StoreKit purchase
mechanism, dated 2026-09-15, and zero-row weeks, dated 2026-09-14. The
numbers 0008 and 0009 were never used. The entries are not in numeric
order, because 0011 sits directly under 0002, which it supersedes for the
website.

With two logs, numbers collide. The first draft of this ADR planned to
start `docs/adr/` at 0011. That number was taken in `docs/DECISIONS.md` the
same day.

## Decision

New decisions are recorded here only, one Markdown file per decision, in
MADR form (Context, Decision, Consequences, Status), named
`NNNN-title.md`.

- `docs/DECISIONS.md` is closed to new entries. A note at its top points
  here. Its existing entries are not rewritten or moved, and they remain
  the record of those decisions.
- Numbering continues after the highest number used in either log, so the
  first ADR in this directory after this one is 0012. A number used in
  `docs/DECISIONS.md` is never reused here.
- The duplicated 0007 is cited by title and date, because the number alone
  is ambiguous.
- An accepted ADR is never edited to change its meaning. A later decision
  adds a new ADR, and the older one gets only a `Superseded by NNNN` status
  line.

## Consequences

Each decision is its own reviewable diff with a stable number, and a
decision cannot collide with another by landing in a different file.
Readers of the older decisions still need `docs/DECISIONS.md`. The two 0007
entries stay ambiguous by number. That is recorded here and is not fixed by
renumbering, because renumbering would break every existing reference to
them.
