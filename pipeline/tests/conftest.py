"""Test-wide setup.

The launch switch (site.APP_STORE_LIVE_DEFAULT) is changed by one line on
launch day. The suite pins it off here so that line is the only edit the
launch pull request needs: tests that check the site "with the switch unset"
mean the pre-launch site, and tests that exercise the switch set it
themselves with monkeypatch, which runs after this fixture.
"""

from __future__ import annotations

import pytest

from cfpa import cli, site


@pytest.fixture(autouse=True)
def _pin_launch_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(site, "APP_STORE_LIVE_DEFAULT", False)


@pytest.fixture(autouse=True)
def _keep_the_committed_source_log_out_of_tests(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A test that calls ``cli.main`` without ``--source-log`` must not write
    the committed pipeline/data/source_log.json (it would feed a later test
    a streak of identical hashes)."""
    scratch = tmp_path_factory.mktemp("source-log") / "source_log.json"
    monkeypatch.setattr(cli, "DEFAULT_SOURCE_LOG_PATH", scratch)
