# Security Policy

## Supported versions

| Surface | Supported |
|---|---|
| The website, as deployed from `main` (republished daily) | yes |
| The iOS app, latest App Store build | yes, once it is released (not yet submitted) |
| Older app builds | no. Update to the latest build |

No version has been tagged yet (#23). "Supported" means the deployed site and
the current app build.

## Reporting a vulnerability

Please report security problems privately. Do not open a public issue.

- **Anyone:** email the support address shown on the site's
  [support page](https://chelseakr.github.io/ca-fish-planting-alerts/support/)
  with "security" in the subject.
- **Collaborators on this repository:** you can also open an issue here,
  because the repository is private.

**The support page does not show an address yet.** It appears once the
`SUPPORT_EMAIL` repository variable is set (#22). Until then there is no
reporting channel for anyone outside this repository. GitHub's private
vulnerability reporting is not available on private repositories.

**Response:** acknowledgement within 72 hours, then a fix or a written
assessment. For a leaked credential, the steps in
`docs/standards/INCIDENT-RESPONSE-STANDARD.md` §4 apply: rotate, revoke,
check for use, and record the history decision.

## What is in scope

- The website and everything the pipeline generates (`site/`, the snapshot,
  the `.ics` feeds).
- The pipeline's fetch, parse and publish path, including the daily job that
  commits `pipeline/data/` to `main`.
- The iOS app, including its StoreKit purchase and background refresh.

The site has no accounts, no forms and no server of its own. The app has no
accounts and talks only to the published snapshot.

## How this repository checks itself

The scanners are specified by `docs/standards/SECURITY-AND-SUPPLY-CHAIN-STANDARD.md`
and run in CI:

- `make verify`: pip-audit and osv-scanner over the lockfile, semgrep, and
  gitleaks over the working tree and the full history.
- `codeql.yml`: Python and GitHub Actions. The gate reads the SARIF locally,
  because code scanning is not enabled on this private repository.
- `zizmor.yml`: workflow security.
- `secret-scan-scheduled.yml`: TruffleHog weekly over the full history, all
  result tiers.
