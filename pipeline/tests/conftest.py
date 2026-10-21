"""Test-wide setup.

The launch switch (site.APP_STORE_LIVE_DEFAULT) is changed by one line on
launch day. The suite pins it off here so that line is the only edit the
launch pull request needs: tests that check the site "with the switch unset"
mean the pre-launch site, and tests that exercise the switch set it
themselves with monkeypatch, which runs after this fixture.
"""

from __future__ import annotations

import pytest

from cfpa import site


@pytest.fixture(autouse=True)
def _pin_launch_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(site, "APP_STORE_LIVE_DEFAULT", False)
