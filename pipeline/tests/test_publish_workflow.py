"""The publish workflow's custom-domain steps (DECISIONS 0019, option B).

The workflow is YAML the pipeline never runs, so these tests read the file
and check its shape: what happens with the variable unset, and in what
order things happen with it set. The order is the safety property: the
github.io site is replaced by redirect pages only after the domain serves
this run's own snapshot, so a domain that is not serving leaves github.io,
and every installed app, exactly as they were.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish.yml"
GUARD = "if: vars.SITE_BASE_URL != ''"

RUN_PIPELINE = "run the pipeline (live fetch -> history -> snapshot -> site)"
COMMIT_HISTORY = "commit updated history and alias table, if any"
PUSH_DOMAIN = "push the domain site to its Pages repository (custom domain only)"
WAIT_DOMAIN = "wait for the domain to serve this run's snapshot (custom domain only)"
UPLOAD = "upload site as a Pages artifact"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _steps(text: str) -> dict[str, str]:
    """The build job's steps by name, each with its full YAML block."""
    build = text[text.index("\n  build:\n") : text.index("\n  deploy:\n")]
    blocks = re.split(r"\n(?=      - (?:name|uses):)", build)
    steps: dict[str, str] = {}
    for block in blocks[1:]:
        m = re.match(r"      - name: (.+)", block)
        if m:
            steps[m.group(1).strip()] = block
    return steps


def _run_body(block: str) -> str:
    return block[block.index("run: |") :]


def _order(steps: dict[str, str]) -> list[str]:
    return list(steps)


@pytest.fixture(scope="module")
def steps() -> dict[str, str]:
    return _steps(_text())


def test_the_custom_domain_steps_exist_in_the_build_job(steps):
    for name in (RUN_PIPELINE, COMMIT_HISTORY, PUSH_DOMAIN, WAIT_DOMAIN, UPLOAD):
        assert name in steps, name


def test_the_order_is_build_commit_push_wait_then_deploy(steps):
    order = _order(steps)
    idx = {
        n: order.index(n)
        for n in (RUN_PIPELINE, COMMIT_HISTORY, PUSH_DOMAIN, WAIT_DOMAIN, UPLOAD)
    }
    assert (
        idx[RUN_PIPELINE]
        < idx[COMMIT_HISTORY]
        < idx[PUSH_DOMAIN]
        < idx[WAIT_DOMAIN]
        < idx[UPLOAD]
    )
    # Nothing is uploaded to Pages before the wait has passed.
    assert order[-1] == UPLOAD


def test_both_domain_steps_run_only_with_the_variable_set(steps):
    for name in (PUSH_DOMAIN, WAIT_DOMAIN):
        block = steps[name]
        assert GUARD in block, name
        # The guard comes before the step's env and run, not inside a comment.
        guard_line = next(ln for ln in block.splitlines() if ln.strip() == GUARD)
        assert guard_line.startswith("        if:"), name


def test_unset_means_the_steps_that_existed_before_are_not_guarded(steps):
    for name in (RUN_PIPELINE, COMMIT_HISTORY, UPLOAD):
        assert GUARD not in steps[name], name


def test_the_pipeline_writes_the_legacy_site_only_with_the_variable_set(steps):
    body = _run_body(steps[RUN_PIPELINE])
    assert '--legacy-site-out "${SITE_BASE_URL:+../site-legacy}"' in body


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, ""), ("", ""), ("https://trouttruck.com", "../site-legacy")],
)
def test_the_shell_expansion_the_pipeline_step_relies_on(value, expected):
    env = {"PATH": "/usr/bin:/bin"}
    if value is not None:
        env["SITE_BASE_URL"] = value
    out = subprocess.run(
        ["/bin/bash", "-c", 'set -u; printf "%s" "${SITE_BASE_URL:+../site-legacy}"'],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout == expected


def test_the_artifact_is_the_legacy_site_only_with_the_variable_set(steps):
    assert (
        "path: ${{ vars.SITE_BASE_URL != '' && 'site-legacy' || 'site' }}"
        in steps[UPLOAD]
    )


def test_the_push_checks_the_build_before_pushing_and_never_writes_the_key(steps):
    body = _run_body(steps[PUSH_DOMAIN])
    push = body.index('git -C "$work" push --force')
    for check in (
        "test -f site/CNAME",
        "test -f site/snapshot/v1.json",
        "test -f site-legacy/snapshot/v1.json",
        'gitleaks" dir site',
        "StrictHostKeyChecking=yes",
        "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl",
        "| ssh-add -q -",
        "trap 'ssh-agent -k > /dev/null' EXIT",
        ': > "$work/.nojekyll"',
    ):
        assert check in body, check
        assert body.index(check) < push, check
    # The key reaches ssh-agent on stdin; no line writes the secret to a file.
    assert not re.search(r"DEPLOY_KEY[^\n]*>", body)
    # IR-15: no wildcard add (scripts/check_hygiene.py enforces it too).
    assert "git add --pathspec-from-file=- --pathspec-file-nul" in body
    assert "git add -A" not in body and "git add ." not in body


def test_the_push_refuses_a_missing_repository_or_key(steps):
    body = _run_body(steps[PUSH_DOMAIN])
    assert '[[ ! "${DOMAIN_SITE_REPO}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]' in body
    assert '[ -z "${DOMAIN_SITE_DEPLOY_KEY}" ]' in body
    assert body.index('DOMAIN_SITE_REPO}" =~') < body.index("test -f site/CNAME")


def test_the_wait_compares_this_run_s_snapshot_over_https_and_fails_otherwise(steps):
    body = _run_body(steps[WAIT_DOMAIN])
    assert 'want="$(sha256sum site/snapshot/v1.json' in body
    assert "--proto '=https'" in body
    assert 'url="${SITE_BASE_URL%/}/snapshot/v1.json"' in body
    assert '"${url}?run=${GITHUB_RUN_ID}-${i}"' in body
    assert 'if [ "$got" = "$want" ]' in body
    assert "exit 0" in body and body.rstrip().endswith("exit 1")
    assert "seq 1 40" in body and "sleep 15" in body


def test_the_job_timeout_covers_the_wait():
    text = _text()
    build = text[text.index("\n  build:\n") : text.index("\n  deploy:\n")]
    m = re.search(r"timeout-minutes: (\d+)", build)
    assert m and int(m.group(1)) >= 30


def test_no_expression_is_interpolated_into_a_run_body(steps):
    # Values reach the shell through env, never through ${{ }} in run:.
    for name, block in steps.items():
        if "run: |" in block:
            assert "${{" not in _run_body(block), name
