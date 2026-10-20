"""The launch switch moves every App Store surface together.

``launch_check.surface_problems`` reads a built site and reports every
surface (Smart App Banner, badge, install links, MobileApplication JSON-LD,
GA4 click event, badge file, "not yet" copy) that disagrees with the state it
expects. These tests build the site both ways, through every route that can
turn the switch on, and fail if the surfaces are ever half on.

Every negative control asserts that its sabotage changed the input before it
asserts that the check caught it.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from cfpa import cli, launch_check, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
GA = "G-TEST12345"


def _build(root: Path, **extra) -> Path:
    out = root / "site"
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url="https://example.invalid/ca-fish-planting-alerts",
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        ga4_measurement_id=GA,
        **extra,
    )
    return out


def _main(root: Path, *extra: str) -> Path:
    argv = [
        "--fixture", str(FRESH),
        "--fixture-fetched-at", "2026-09-13T12:00:00Z",
        "--run-today", "2026-09-13",
        "--history", str(root / "history.json"),
        "--aliases", str(root / "aliases.json"),
        "--site-out", str(root / "site"),
        "--base-url", "https://example.invalid/ca-fish-planting-alerts",
        *extra,
    ]  # fmt: skip
    assert cli.main(argv) == 0
    return root / "site"


def test_the_committed_default_is_a_bool_and_documented():
    assert isinstance(site.APP_STORE_LIVE_DEFAULT, bool)


@pytest.mark.parametrize("live", [False, True])
def test_every_surface_agrees_with_the_flag(tmp_path, live):
    out = _build(tmp_path, app_store_live=live)
    assert launch_check.surface_problems(out, live=live) == []


def test_build_default_is_all_off(tmp_path):
    out = _build(tmp_path)
    assert launch_check.surface_problems(out, live=False) == []


@pytest.mark.parametrize(
    ("variable", "default", "live"),
    [
        (None, False, False),
        ("", False, False),
        ("false", False, False),
        ("true", False, True),
        (None, True, True),
        ("", True, True),
        ("true", True, True),
        ("false", True, False),  # the kill switch beats the committed default
    ],
)
def test_the_committed_default_and_the_variable_through_the_entry_point(
    tmp_path, monkeypatch, variable, default, live
):
    monkeypatch.setattr(site, "APP_STORE_LIVE_DEFAULT", default)
    monkeypatch.setattr(site, "GA4_MEASUREMENT_ID", GA)
    extra = () if variable is None else ("--app-store-live", variable)
    out = _main(tmp_path, *extra)
    assert launch_check.surface_problems(out, live=live) == []


def test_an_explicit_url_with_the_switch_off_shows_nothing(tmp_path):
    out = _build(
        tmp_path,
        app_store_live=False,
        app_store_url="https://apps.apple.com/us/app/id0000000000",
    )
    assert launch_check.surface_problems(out, live=False) == []


def test_an_explicit_url_with_the_switch_on_is_used_everywhere(tmp_path):
    other = "https://apps.apple.com/us/app/trout-truck/id6818637427"
    out = _build(tmp_path, app_store_live=True, app_store_url=other)
    assert launch_check.surface_problems(out, live=True, url=other) == []


# ---- negative controls: the check can fail


def _edit(path: Path, old: str, new: str) -> None:
    original = path.read_text(encoding="utf-8")
    path.write_text(original.replace(old, new), encoding="utf-8")
    assert path.read_text(encoding="utf-8") != original  # the sabotage landed


def test_negative_control_banner_left_on_when_off(tmp_path):
    out = _build(tmp_path, app_store_live=False)
    _edit(
        out / "index.html",
        "</head>",
        '<meta name="apple-itunes-app" content="app-id=6818637427"></head>',
    )
    assert any("banner" in p for p in launch_check.surface_problems(out, live=False))


def test_negative_control_banner_missing_when_on(tmp_path):
    out = _build(tmp_path, app_store_live=True)
    _edit(out / "support" / "index.html", 'name="apple-itunes-app"', 'name="x"')
    assert any(
        p.startswith("support/index.html: banner")
        for p in launch_check.surface_problems(out, live=True)
    )


def test_negative_control_schema_missing_when_on(tmp_path):
    out = _build(tmp_path, app_store_live=True)
    _edit(out / "index.html", '"MobileApplication"', '"Thing"')
    assert any(
        "MobileApplication" in p for p in launch_check.surface_problems(out, live=True)
    )


def test_negative_control_schema_left_when_off(tmp_path):
    live = _build(tmp_path / "live", app_store_live=True)
    off = _build(tmp_path / "off", app_store_live=False)
    block = (live / "index.html").read_text(encoding="utf-8")
    assert "MobileApplication" in block
    _edit(off / "index.html", "</head>", "<!-- MobileApplication --></head>")
    assert any("while off" in p for p in launch_check.surface_problems(off, live=False))


def test_negative_control_link_left_when_off(tmp_path):
    out = _build(tmp_path, app_store_live=False)
    _edit(
        out / "about" / "index.html",
        "</main>",
        '<a href="https://apps.apple.com/us/app/id6818637427">x</a></main>',
    )
    assert any("while off" in p for p in launch_check.surface_problems(out, live=False))


def test_negative_control_install_link_missing_on_a_water_page(tmp_path):
    out = _build(tmp_path, app_store_live=True)
    water = sorted((out / "water").glob("*/index.html"))[0]
    text = water.read_text(encoding="utf-8")
    assert "data-app-store-kind" in text
    water.write_text(
        text.replace("apps.apple.com", "example.invalid"), encoding="utf-8"
    )
    assert any(
        "install link missing" in p
        for p in launch_check.surface_problems(out, live=True)
    )


def test_negative_control_click_event_missing_when_on(tmp_path):
    out = _build(tmp_path, app_store_live=True)
    for f in out.rglob("*.html"):
        text = f.read_text(encoding="utf-8")
        f.write_text(
            text.replace("app_store_click", "something_else"), encoding="utf-8"
        )
    assert any(
        "app_store_click" in p for p in launch_check.surface_problems(out, live=True)
    )


def test_negative_control_badge_file_missing_when_on(tmp_path):
    out = _build(tmp_path, app_store_live=True)
    (out / "assets" / site.APP_STORE_BADGE_FILE).unlink()
    assert any("badge file" in p for p in launch_check.surface_problems(out, live=True))


def test_negative_control_wrong_state_is_caught_both_ways(tmp_path):
    on = _build(tmp_path / "on", app_store_live=True)
    off = _build(tmp_path / "off", app_store_live=False)
    assert launch_check.surface_problems(on, live=False) != []
    assert launch_check.surface_problems(off, live=True) != []


def test_flipping_the_one_constant_turns_everything_on(tmp_path, monkeypatch):
    """The launch pull request changes APP_STORE_LIVE_DEFAULT and nothing
    else: with the variable unset, the real entry point then builds all on."""
    monkeypatch.setattr(site, "GA4_MEASUREMENT_ID", GA)
    before = _main(tmp_path / "before")
    assert launch_check.surface_problems(before, live=False) == []
    monkeypatch.setattr(site, "APP_STORE_LIVE_DEFAULT", True)
    after = _main(tmp_path / "after")
    assert launch_check.surface_problems(after, live=True) == []
    assert launch_check.surface_problems(after, live=False) != []  # not vacuous


def test_the_workflow_still_passes_the_variable_through():
    wf = (
        Path(__file__).resolve().parents[2] / ".github/workflows/publish.yml"
    ).read_text(encoding="utf-8")
    assert '--app-store-live "$APP_STORE_LIVE"' in wf


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("https://apps.apple.com/us/app/id123", True),
        ("http://apps.apple.com/us/app/id123", True),
        ("https://example.com/?next=apps.apple.com", False),
        ("https://apps.apple.com.example.com/us/app/id123", False),
        ("https://example.com/apps.apple.com", False),
        ("", False),
        (None, False),
    ],
)
def test_an_install_link_is_recognized_by_its_host_not_a_substring(href, expected):
    assert launch_check._is_app_store_link(href) is expected
