"""The website's "Opt out of analytics" footer control.

The choice is a localStorage flag on this device, read by the GA4 tag before
anything loads. These tests run the rendered tag under node against a stub
browser with localStorage, the footer's elements and a click. The first
checks are that the flag stops GA from loading, that a click writes the flag,
and that the next page load honours it.

Each negative control asserts that its sabotage changed the input before it
asserts that the check caught it.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
TEST_ID = "G-TEST12345"
KEY = "trout-truck:analytics-opt-out"
OPT_OUT_GUARD = "if (optedOut) return;"

OFF = "Analytics is off on this device."
BACK_ON = "Analytics is back on from the next page you open."
SIGNAL = "Analytics is off: your browser sends Global Privacy Control or Do Not Track."
NOT_SAVED = (
    "Your browser would not save this choice, so it lasts only until you leave "
    "this page."
)

FOOTER = re.compile(
    r'<p id="analytics-choice" hidden><button type="button" id="analytics-opt-out"'
    r' class="link-button" hidden>Opt out of analytics</button>'
    r' <span id="analytics-status" role="status"></span></p>'
)


def _build(root: Path, ga4_measurement_id: str | None) -> dict[str, str]:
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
        ga4_measurement_id=ga4_measurement_id,
    )
    pages = {
        str(f.relative_to(out)): f.read_text(encoding="utf-8")
        for f in sorted(out.rglob("*.html"))
    }
    assert len(pages) > 10, sorted(pages)
    return pages


@pytest.fixture(scope="module")
def id_pages(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    return _build(tmp_path_factory.mktemp("optout-with-id"), TEST_ID)


@pytest.fixture(scope="module")
def no_id_pages(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    return _build(tmp_path_factory.mktemp("optout-no-id"), None)


@pytest.fixture(scope="module")
def tag_js(id_pages: dict[str, str]) -> str:
    scripts = re.findall(
        r"<script\b[^>]*>(.*?)</script\b[^>]*>", id_pages["index.html"], re.S | re.I
    )
    assert len(scripts) == 1
    js: str = scripts[0]
    return js


# ---- the markup


def test_every_page_with_the_tag_has_the_footer_control_hidden_until_js(id_pages):
    for name, html in id_pages.items():
        footer = html[html.index('<footer class="site-footer">') :]
        assert len(FOOTER.findall(footer)) == 1, name


def test_no_control_without_the_tag(no_id_pages):
    """No analytics, nothing to opt out of: no button and no empty status."""
    for name, html in no_id_pages.items():
        assert "analytics-choice" not in html, name
        assert "Opt out of analytics" not in html, name


def test_privacy_page_describes_the_opt_out(id_pages):
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", id_pages["privacy/index.html"]))
    for phrase in (
        "Opting out on this device.",
        "“Opt out of analytics” button at the bottom of every page",
        "does not load it at all",
        "local storage for this site, not in a cookie",
        "“Opt back in”",
        "or you opt out",
    ):
        assert phrase in text.replace("&ldquo;", "“").replace("&rdquo;", "”"), phrase


# ---- the behaviour, executed

_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[2], "utf8");
const c = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const blocked = () => { throw new Error("storage blocked"); };
const data = Object.assign({}, c.storage || {});
const localStorage = c.storageBlocked
  ? { getItem: blocked, setItem: blocked, removeItem: blocked }
  : {
      getItem: (k) => (Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null),
      setItem: (k, v) => { data[k] = String(v); },
      removeItem: (k) => { delete data[k]; },
    };
function element(hidden, text) {
  const listeners = [];
  return {
    hidden, textContent: text,
    addEventListener: (type, f) => { if (type === "click") listeners.push(f); },
    click: () => listeners.forEach((f) => f()),
  };
}
const els = {
  "analytics-choice": element(true, ""),
  "analytics-opt-out": element(true, "Opt out of analytics"),
  "analytics-status": element(false, ""),
};
const ready = [];
const appended = [];
const document = {
  createElement: (tag) => ({ tagName: tag }),
  head: { appendChild: (el) => { appended.push(el); } },
  getElementById: (id) => els[id] || null,
  addEventListener: (type, f) => { if (type === "DOMContentLoaded") ready.push(f); },
};
const navigator = Object.assign({}, c.navigator);
const window = Object.assign({ localStorage }, c.window);
vm.runInContext(code, vm.createContext({ navigator, window, document, Date, encodeURIComponent }));
ready.forEach((f) => f());
const snap = () => ({
  choiceHidden: els["analytics-choice"].hidden,
  buttonHidden: els["analytics-opt-out"].hidden,
  button: els["analytics-opt-out"].textContent,
  status: els["analytics-status"].textContent,
  storage: c.storageBlocked ? null : Object.assign({}, data),
  gaDisabled: window["ga-disable-" + c.id] === undefined ? null : window["ga-disable-" + c.id],
});
const states = [snap()];
for (let i = 0; i < (c.clicks || 0); i++) {
  els["analytics-opt-out"].click();
  states.push(snap());
}
const loaded = appended.length > 0 || window.dataLayer !== undefined;
process.stdout.write(JSON.stringify({ loaded, appended: appended.length, states }));
"""


def _run(
    tmp_path: Path,
    js: str,
    *,
    storage: dict[str, str] | None = None,
    storage_blocked: bool = False,
    navigator: dict[str, object] | None = None,
    clicks: int = 0,
) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI to execute the opt-out")
        pytest.skip("node is not installed")
    (tmp_path / "harness.js").write_text(_HARNESS, encoding="utf-8")
    (tmp_path / "tag.js").write_text(js, encoding="utf-8")
    case = {
        "id": TEST_ID,
        "storage": storage or {},
        "storageBlocked": storage_blocked,
        "navigator": navigator or {},
        "window": {},
        "clicks": clicks,
    }
    (tmp_path / "case.json").write_text(json.dumps(case), encoding="utf-8")
    result = subprocess.run(
        [node, *(str(tmp_path / f) for f in ("harness.js", "tag.js", "case.json"))],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    parsed: dict[str, Any] = json.loads(result.stdout)
    return parsed


def test_the_flag_stops_ga_from_loading(tmp_path, tag_js):
    ran = _run(tmp_path, tag_js, storage={KEY: "1"})
    assert ran["loaded"] is False
    assert ran["appended"] == 0
    assert ran["states"][0] == {
        "choiceHidden": False,
        "buttonHidden": False,
        "button": "Opt back in",
        "status": OFF,
        "storage": {KEY: "1"},
        "gaDisabled": None,
    }


def test_negative_control_without_the_flag_check_ga_loads_despite_the_flag(
    tmp_path, tag_js
):
    sabotaged = tag_js.replace(OPT_OUT_GUARD, "")
    assert sabotaged != tag_js  # the sabotage landed
    ran = _run(tmp_path, sabotaged, storage={KEY: "1"})
    assert ran["loaded"] is True
    assert ran["appended"] == 1


@pytest.mark.parametrize("storage", [{}, {KEY: "0"}, {"analytics-opt-out": "1"}])
def test_without_this_sites_flag_ga_loads_and_offers_the_opt_out(
    tmp_path, tag_js, storage
):
    """Only this site's key, set to "1", opts out. Other github.io project
    sites share this origin's localStorage, so a bare key is not ours."""
    ran = _run(tmp_path, tag_js, storage=storage)
    assert ran["loaded"] is True
    assert ran["appended"] == 1
    first = ran["states"][0]
    assert (first["button"], first["status"], first["buttonHidden"]) == (
        "Opt out of analytics",
        "",
        False,
    )


def test_opting_out_is_remembered_and_honoured_on_the_next_page(tmp_path, tag_js):
    first_page = _run(tmp_path, tag_js, clicks=2)
    assert first_page["loaded"] is True
    _, out, back_in = first_page["states"]
    assert (out["button"], out["status"], out["gaDisabled"]) == (
        "Opt back in",
        OFF,
        True,
    )
    assert out["storage"] == {KEY: "1"}
    assert (back_in["button"], back_in["status"], back_in["gaDisabled"]) == (
        "Opt out of analytics",
        BACK_ON,
        False,
    )
    assert back_in["storage"] == {}

    # the flag a single click leaves behind, read by the next page load
    opted_out = _run(tmp_path, tag_js, clicks=1)["states"][-1]["storage"]
    assert opted_out == {KEY: "1"}
    next_page = _run(tmp_path, tag_js, storage=opted_out)
    assert next_page["loaded"] is False


def test_blocked_storage_loads_as_before_and_says_the_choice_is_not_saved(
    tmp_path, tag_js
):
    ran = _run(tmp_path, tag_js, storage_blocked=True, clicks=1)
    assert ran["loaded"] is True
    clicked = ran["states"][1]
    assert (clicked["button"], clicked["status"], clicked["gaDisabled"]) == (
        "Opt back in",
        NOT_SAVED,
        True,
    )


@pytest.mark.parametrize(
    "navigator", [{"globalPrivacyControl": True}, {"doNotTrack": "1"}]
)
def test_under_gpc_or_dnt_the_footer_says_so_and_offers_no_button(
    tmp_path, tag_js, navigator
):
    ran = _run(tmp_path, tag_js, navigator=navigator)
    assert ran["loaded"] is False
    first = ran["states"][0]
    assert (first["choiceHidden"], first["buttonHidden"], first["status"]) == (
        False,
        True,
        SIGNAL,
    )
