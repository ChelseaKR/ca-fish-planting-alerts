# 0076. publish-health fails its run, at the freshness job's limits

Status: Accepted
Date: 2026-11-19
Deciders: Chelsea Kelly-Reif

## Context

The 2026-11-19 delivery audit (`_agent-tools/growth/delivery-audit-2026-11-19/REPORT.md`,
outside this repo, problem 1, approved by Chelsea the same day) found the
live snapshot holding Tennessee data from 2026-11-14 and Massachusetts data
from 2026-11-07 while both `publish` and `publish-health` were green. The
only signal was a daily comment on #168. DECISIONS 0065 had already said
that a comment nobody reads is not a signal, and moved the publish run's
signal to a red `freshness` job, but left `publish-health.yml` as it was.

`publish-health` also used a limit of its own: a state failing for 3 days.
Since DECISIONS 0061 Tennessee is a hand-loaded TWRA file, renewed weekly,
while the runner's automated read stays refused. A 3-day limit put
Tennessee in the issue four days of every seven, and a red run on that rule
would have been red most days with nothing wrong. Massachusetts is
"waiting" under DECISIONS 0071: Hub's copy is stale, and MassWildlife has
not edited its layer since 2026-10-13, so nothing newer exists upstream.

Read on 2026-11-19 with the project's own user agent:

- **Tennessee.** From a home connection, `www.tn.gov/robots.txt` answers
  200 with `Allow: /`, and the data URL the reader uses answers 200 with
  TWRA's JSON (Last-Modified 2026-11-18). From the GitHub-hosted runner the
  same robots.txt request is reset (`[Errno 104] Connection reset by
  peer`), and earlier runs got 403 (#97). The block depends on where the
  request comes from, not on the user agent or the URL, and has lasted
  since 2026-10-15, so it is not transient. The only other TWRA data found
  is a locations layer on ArcGIS Hub ("Trout Stocking Locations in
  Tennessee", 730 points, edited 2026-11-16), which has no stocking dates.
  The reader is unchanged: it refuses a host whose robots.txt it cannot
  read, and does not work around the block.
- **Massachusetts.** Hub still answers `cacheStatus` "stale". The layer
  (`StockedFish_View`, item `e27aa5ec…`) was last edited 2026-10-13
  17:06 UTC and has 155 records. MassWildlife's own dashboard, linked from
  mass.gov's trout stocking report page, still reads that same item. The
  URL and columns are unchanged. The data is stale at the source, so
  nothing on our side needs fixing.

## Decision

- **Unhealthy is a red run.** A last step, `fail the run while unhealthy`,
  exits 1 after the issue step has opened or updated the issue. The issue
  still closes itself on the first healthy check. This covers every
  finding: a stale publish, California's week, the site not answering, and
  a stuck state.
- **The issue stays quiet.** The red run is the daily signal, so the issue
  no longer gets the same comment every day (#168 had nine). The report
  ends with a hidden line, `<!-- publish-health-state: KEYS -->`, holding
  the sorted keys of the failing findings. The workflow comments and
  rewrites the body only when those keys differ from the ones in the open
  issue's body. A waiting state is not in the keys. This is Lake Notice's
  rule from the same audit.
- **The open issue is found by listing, not search.** The step now runs
  `gh issue list --state open --limit 500` and matches the exact title.
  Lake Notice's search index once missed an open issue and made a
  duplicate (#11, then #48).
- **Ages are measured from the build.** A state's last good read, and
  California's week, are dated against the snapshot's `generated_at`, not
  the time of the check. A publish that did not deploy is one finding,
  `publish-stale`, instead of one per state as well.
- **One limit per state, shared with the freshness job.** A state is stuck
  when the last good read in the live snapshot (`checks.last_success_at`,
  which for a hand import is the download time), measured from the build,
  is older than the freshness allowance: `cfpa.freshness.DEFAULT_MAX_READ_AGE_DAYS` (7 days) or the
  state module's `max_read_age_days`. Equal is not stuck.
  `STATE_FAIL_DAYS` (3) is gone.
- **Waiting is judged by the same rule.** `cfpa.freshness.stale_copy_verdict`
  judges both the history file and the snapshot. The snapshot carries
  `checks.stale_copy` only when the latest attempt failed on Hub's flag. A
  waiting state is printed, and listed under "Not counted" when the issue
  is open for another reason. It does not fail the run on its own. An edit
  date that cannot be read, or a recent edit, makes the state stuck.

## Consequences

- On the 2026-11-19 snapshot this check is healthy: Tennessee's file is 5
  days old, and Massachusetts is waiting. Its next run closes #168. It goes
  red on the first check whose snapshot was built more than 7 days after
  Tennessee's file was downloaded (for the 2026-11-14 file, the build of
  2026-11-22 01:17 UTC), or on the first check after MassWildlife edits
  its layer while Hub's copy is still stale.
- `publish-health` and the publish run's `freshness` job now agree on every
  state. `publish-health` still reads what is live, so it also catches a
  deploy that did not land, which the `freshness` job cannot see.
- A red run reaches Chelsea only if GitHub notifies her about failed
  scheduled runs. The audit did not check that setting.
- The first unhealthy run after this lands comments once, because #168's
  body has no marker yet. Unchanged runs after that only go red.
- A test checks the fields the script reads against `schema/snapshot.v2.json`,
  so a contract change that renames one fails in `make verify`.
- To go back to issue-only, remove the last step. To red Massachusetts while
  it waits, drop the waiting branch in `_check_state`. Either is a one-line
  change and changes no data.
