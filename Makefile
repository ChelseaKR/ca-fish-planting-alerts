# Repository-root gate (CI-CD-STANDARD §1 and §9, CODE-QUALITY-STANDARD §2).
#
# The Python project lives in pipeline/ and the Swift package in
# ios/PlantingCore/ (docs/adr/0012-nested-pipeline-and-ios-layout.md), so this
# Makefile exposes the pipeline's gates from the repository root. CI's
# `verify` job runs `make verify` and nothing else for stages 1-5, so a green
# `make verify` locally is the same claim as a green `verify` check.
#
# Needs: uv >= 0.11, gitleaks 8.30.1, osv-scanner 2.x on PATH. CI installs the
# pinned binaries itself (.github/workflows/ci.yml).
#
# No recipe here pipes one command into another: macOS ships GNU Make 3.81,
# which ignores .SHELLFLAGS, so a pipe could hide a failing command. Each line
# is one command, and make stops at the first non-zero exit.

PIPELINE := pipeline
UV_RUN := uv run --frozen
SEMGREP_VERSION := 1.166.0
# One scratch directory per `make` run; each target writes under its own
# subdirectory, so nothing lands inside the checkout.
TMP := $(shell mktemp -d 2>/dev/null || mktemp -d -t cfpa)

.PHONY: verify sync format lint typecheck test smoke build audit sast secrets hygiene

# Stage order per CI-CD-STANDARD §1: format, lint, type, test, security.
verify: sync format lint typecheck test smoke build audit sast secrets hygiene

# CQ-09: `uv lock --check` first. `--frozen` installs from uv.lock without
# reading pyproject.toml, so it cannot notice drift, and a bare `uv run`
# would relock silently before the check could see it.
sync:
	cd $(PIPELINE) && uv lock --check
	cd $(PIPELINE) && uv sync --frozen

format:
	cd $(PIPELINE) && $(UV_RUN) ruff format --check .
	cd $(PIPELINE) && $(UV_RUN) ruff format --check --config pyproject.toml ../scripts

lint:
	cd $(PIPELINE) && $(UV_RUN) ruff check .
	cd $(PIPELINE) && $(UV_RUN) ruff check --config pyproject.toml ../scripts

typecheck:
	cd $(PIPELINE) && $(UV_RUN) mypy --strict src
	cd $(PIPELINE) && $(UV_RUN) mypy --strict ../scripts

# Branch coverage floor lives in pipeline/pyproject.toml ([tool.coverage.report]).
test:
	cd $(PIPELINE) && $(UV_RUN) pytest --cov=src --cov-branch --cov-report=term

# The offline end-to-end run: fixture -> history -> schema-validated
# snapshot -> site, with no network and nothing written inside the repo.
smoke:
	cd $(PIPELINE) && $(UV_RUN) cfpa \
		--fixture tests/fixtures/schedule-fresh-2026-09-13.html \
		--fixture-fetched-at 2026-09-13T12:00:00Z \
		--run-today 2026-09-13 \
		--history $(TMP)/smoke/history.json \
		--aliases $(TMP)/smoke/aliases.json \
		--site-out $(TMP)/smoke/site
	test -f $(TMP)/smoke/site/index.html

# CQ-10: the wheel builds, and the site templates ship inside it.
build:
	cd $(PIPELINE) && uv build --wheel --out-dir $(TMP)/dist
	cd $(PIPELINE) && $(UV_RUN) python -c "import sys, zipfile, glob; n = zipfile.ZipFile(glob.glob(sys.argv[1] + '/*.whl')[0]).namelist(); sys.exit(0 if 'cfpa/templates/base.html.jinja' in n else 'wheel is missing cfpa/templates')" $(TMP)/dist

# SEC-11 / SEC-13: every locked package, dev group included, audited from the
# lockfile itself. --strict fails on a package pip-audit could not check,
# rather than skipping it.
audit:
	cd $(PIPELINE) && uv export --frozen --no-emit-project --format requirements-txt --quiet --output-file $(TMP)/audit/requirements.txt
	cd $(PIPELINE) && $(UV_RUN) pip-audit --strict --require-hashes --disable-pip -r $(TMP)/audit/requirements.txt
	osv-scanner scan --lockfile $(PIPELINE)/uv.lock

# SEC-07: pinned scanner, pinned ruleset, --error so a finding fails the run.
# --python pins the interpreter uvx builds the tool environment with. Left to
# itself uvx picked a Python for which it built semgrep from the sdist, and
# that build has no semgrep-core binary, so the scan could not start.
sast:
	uvx --python 3.12 --from semgrep==$(SEMGREP_VERSION) semgrep scan --config p/python --error --metrics=off --quiet $(PIPELINE)/src scripts

# SEC-18: the working tree and the full commit history, redacted, no mute.
secrets:
	gitleaks dir . --no-banner --redact --exit-code 1
	gitleaks git . --no-banner --redact --exit-code 1

# CQ-34, CQ-35, IR-15. The self-test runs first so a check that no longer
# matches anything cannot report a clean tree.
hygiene:
	cd $(PIPELINE) && $(UV_RUN) python ../scripts/check_hygiene.py --self-test
	cd $(PIPELINE) && $(UV_RUN) python ../scripts/check_hygiene.py
