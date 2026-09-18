## What and why

<!-- What changes, which issue it closes, and why. -->

Closes #

## Quality characteristic

<!-- ISO 25010 characteristic(s) this touches: functional suitability,
reliability, security, interaction capability, maintainability,
performance efficiency, compatibility, flexibility, safety, data quality. -->

## Definition of Done (`DEFINITION_OF_DONE.md`)

- [ ] Every required check is green on the final head, with nothing muted or skipped.
- [ ] `make verify` passes locally. If the site changed, `tools/site-checks/run.sh` passes too.
- [ ] Docs and CHANGELOG agree with the change.
- [ ] A change to `schema/` or to what lands in `pipeline/data/` states its rollback plan below.
- [ ] A new external surface (source, third-party script, endpoint) updates the data card or `docs/RESPONSIBLE-TECH-AUDITS.md`.
- [ ] A new interactive element on the site or in the app has had a keyboard and screen-reader check.
- [ ] An expensive-to-reverse decision has an ADR in `docs/adr/`.

## Rollback

<!-- How to undo this if it goes wrong, or "revert the merge commit". -->
