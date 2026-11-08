"""The publish workflow's web push steps (DECISIONS 0069).

Two steps around the deploy: the selection runs before the domain push
replaces the live snapshot (it is what this build is compared with), and the
send runs after the domain is verified to serve this build (so a message's
link already shows the change) and before the Pages upload, which stays the
build job's last step. Both are guarded by the two variables and can fail
without failing the run.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish.yml"
GUARD = "if: vars.SITE_BASE_URL != '' && vars.PUSH_API_URL != ''"

RUN_PIPELINE = "run the pipeline (live fetch -> history -> snapshot -> site)"
PICK = "pick the schedule changes to tell web push subscribers (custom domain only)"
PUSH_DOMAIN = "push the domain site to its Pages repository (custom domain only)"
WAIT_DOMAIN = "wait for the domain to serve this run's snapshot (custom domain only)"
SEND = "send the schedule changes to web push subscribers (custom domain only)"
UPLOAD = "upload site as a Pages artifact"


def _steps(text: str) -> dict[str, str]:
    build = text[text.index("\n  build:\n") : text.index("\n  deploy:\n")]
    blocks = re.split(r"\n(?=      - (?:name|uses):)", build)
    steps: dict[str, str] = {}
    for block in blocks[1:]:
        m = re.match(r"      - name: (.+)", block)
        if m:
            steps[m.group(1).strip()] = block
    return steps


@pytest.fixture(scope="module")
def steps() -> dict[str, str]:
    return _steps(WORKFLOW.read_text(encoding="utf-8"))


def test_the_two_steps_exist_and_are_guarded_and_advisory(steps):
    for name in (PICK, SEND):
        assert name in steps, name
        assert GUARD in steps[name], name
        assert "continue-on-error: true" in steps[name], name


def test_the_selection_runs_before_the_live_site_is_replaced_and_the_send_after_it_is_verified(
    steps,
):
    order = list(steps)
    idx = {
        n: order.index(n)
        for n in (RUN_PIPELINE, PICK, PUSH_DOMAIN, WAIT_DOMAIN, SEND, UPLOAD)
    }
    assert (
        idx[RUN_PIPELINE]
        < idx[PICK]
        < idx[PUSH_DOMAIN]
        < idx[WAIT_DOMAIN]
        < idx[SEND]
        < idx[UPLOAD]
    )
    assert order[-1] == UPLOAD


def test_the_selection_compares_the_live_snapshot_with_this_build(steps):
    body = steps[PICK]
    assert "python -m cfpa.push diff" in body
    assert '--before-url "${SITE_BASE_URL%/}/snapshot/v2.json"' in body
    assert "--after ../site/snapshot/v2.json" in body
    assert '--out "$RUNNER_TEMP/push-events.json"' in body
    assert "secrets." not in body


def test_the_send_uses_the_selected_events_and_the_secret_token_through_env(steps):
    body = steps[SEND]
    assert "python -m cfpa.push send" in body
    assert "PUSH_SENDER_TOKEN: ${{ secrets.PUSH_SENDER_TOKEN }}" in body
    assert "PUSH_API_URL: ${{ vars.PUSH_API_URL }}" in body
    assert '--api-url "$PUSH_API_URL"' in body
    # The token never appears on a command line: cfpa.push reads it from env.
    assert "PUSH_SENDER_TOKEN" not in body.split("run: |")[1]
    # A missing events file (the selection step failed) is a warning, not a call.
    assert 'if [ ! -f "$events" ]' in body


def test_the_pipeline_step_passes_the_two_variables_through_env(steps):
    body = steps[RUN_PIPELINE]
    assert "PUSH_API_URL: ${{ vars.PUSH_API_URL }}" in body
    assert "PUSH_VAPID_PUBLIC_KEY: ${{ vars.PUSH_VAPID_PUBLIC_KEY }}" in body
    assert '--push-api-url "$PUSH_API_URL"' in body
    assert '--push-vapid-public-key "$PUSH_VAPID_PUBLIC_KEY"' in body


def test_the_terraform_refuses_any_account_but_the_one_named():
    versions = (REPO_ROOT / "infra" / "web-push" / "versions.tf").read_text("utf-8")
    assert "allowed_account_ids = [var.aws_account_id]" in versions
    # Nothing in the repository applies it: the owner does (README).
    for wf in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
        assert "terraform" not in wf.read_text("utf-8").lower(), wf.name
