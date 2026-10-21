"""GA4 click events for gear links and calendar feed (.ics) links.

The events go through the one existing GA4 tag (DECISIONS 0011), below the
Global Privacy Control, Do Not Track and footer opt-out returns, and they
check ga-disable at click time. These tests render the real site, take the
real anchors from a rendered water page, and run the real tag under node
against a stub browser, once per opt-out. App Store clicks have their own
tests in test_site_app_store.py.

Each negative control asserts that its sabotage changed the input before it
asserts that the check caught it.
"""

from __future__ import annotations

import datetime as dt
import html as htmllib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from cfpa import cli

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
TEST_ID = "G-TEST12345"
KEY = "trout-truck:analytics-opt-out"
GATE = 'if (!a || w["ga-disable-" + id]) return;'

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[2], "utf8");
const c = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const listeners = {};
const attrs = c.attrs || {};
const anchor = {
  href: c.href,
  hostname: new URL(c.href, "https://example.invalid/water/x/").hostname,
  getAttribute: (k) => (k in attrs ? attrs[k] : null),
};
const data = Object.assign({}, c.storage || {});
const localStorage = {
  getItem: (k) => (Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null),
  setItem: (k, v) => { data[k] = String(v); },
  removeItem: (k) => { delete data[k]; },
};
const document = {
  addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
  getElementById: () => null,
  createElement: () => ({}),
  head: { appendChild: () => {} },
};
const window = Object.assign({ localStorage }, c.window);
const navigator = Object.assign({}, c.navigator);
vm.runInContext(code, vm.createContext({
  window, navigator, document, Date, encodeURIComponent, URL,
}));
if (c.disableAfterLoad) window[c.disableAfterLoad] = true;
const hit = c.noAnchor ? null : anchor;
const target = { closest: (sel) => (hit && sel.indexOf("data-ga-event") >= 0 ? hit : null) };
(listeners.click || []).forEach((f) => f({ target }));
const events = (window.dataLayer || [])
  .map((a) => Array.from(a))
  .filter((a) => a[0] === "event");
process.stdout.write(JSON.stringify({ clickListeners: (listeners.click || []).length, events }));
"""


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI to execute the GA4 link clicks")
        pytest.skip("node is not installed; the link clicks are string-checked")
    return node


def _build(root: Path, ga4_measurement_id: str | None, **extra: object) -> Path:
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
        **extra,
    )
    return out


def _scripts(page: str) -> list[str]:
    return re.findall(
        r'<script\b(?![^>]*\btype="application/ld\+json")[^>]*>(.*?)</script\b[^>]*>',
        page,
        re.S | re.I,
    )


@pytest.fixture(scope="module")
def site_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("link-clicks"), TEST_ID)


@pytest.fixture(scope="module")
def water_page(site_dir: Path) -> str:
    pages = sorted((site_dir / "water").glob("*/index.html"))
    assert pages
    return pages[0].read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tag_js(site_dir: Path) -> str:
    scripts = _scripts((site_dir / "index.html").read_text(encoding="utf-8"))
    assert len(scripts) == 1
    return scripts[0]


def _anchors(page: str, event: str) -> list[dict[str, object]]:
    found = []
    for m in re.finditer(r"<a\b([^>]*\bdata-ga-event=\"" + event + r"\"[^>]*)>", page):
        attrs = {
            k: htmllib.unescape(v)
            for k, v in re.findall(r'([\w-]+)="([^"]*)"', m.group(1))
        }
        found.append(attrs)
    return found


def _click(
    tmp_path: Path, js: str, anchor: dict[str, object] | None, case: dict[str, object]
) -> dict[str, object]:
    node = _node()
    payload = dict(case)
    if anchor is None:
        payload.update(noAnchor=True, href="https://example.invalid/")
    else:
        payload.update(attrs=anchor, href=anchor["href"])
    (tmp_path / "h.js").write_text(HARNESS, encoding="utf-8")
    (tmp_path / "tag.js").write_text(js, encoding="utf-8")
    (tmp_path / "case.json").write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [
            node,
            str(tmp_path / "h.js"),
            str(tmp_path / "tag.js"),
            str(tmp_path / "case.json"),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    parsed: dict[str, object] = json.loads(result.stdout)
    return parsed


# ---- the markup


def test_water_page_marks_four_gear_links_and_one_calendar_link(water_page):
    gear = _anchors(water_page, "gear_click")
    ics = _anchors(water_page, "calendar_subscribe_click")
    assert len(gear) == 4
    assert len(ics) == 1
    for a in gear:
        assert urlsplit(str(a["href"])).hostname == "www.amazon.com"
        assert a["data-ga-placement"] == "water"
        assert a["data-ga-type"] == "amazon_search"
    assert ics[0]["href"] == "feed.ics"
    assert ics[0]["data-ga-placement"] == "water"
    assert ics[0]["data-ga-type"] == "ics"


def test_every_amazon_link_on_the_site_is_a_marked_gear_link(site_dir):
    seen = 0
    for f in site_dir.rglob("*.html"):
        page = f.read_text(encoding="utf-8")
        for m in re.finditer(r"<a\b[^>]*href=\"https://www\.amazon\.com[^>]*>", page):
            seen += 1
            assert 'data-ga-event="gear_click"' in m.group(0), f
    assert seen >= 4


def test_marked_links_add_no_script_and_the_tag_stays_the_only_one(
    site_dir, water_page
):
    assert len(_scripts(water_page)) == 1
    assert re.findall(r"<script\b[^>]*\bsrc=", water_page) == []
    assert "googletagmanager" in water_page  # still loaded by the one tag
    for host in re.findall(r"https?://([a-z0-9.-]+)", _scripts(water_page)[0]):
        assert host in {"www.googletagmanager.com"}, host


def test_no_ga_id_means_no_click_code_at_all(tmp_path):
    out = _build(tmp_path, None)
    for f in out.rglob("*.html"):
        page = f.read_text(encoding="utf-8")
        assert "gear_click" not in page.replace('data-ga-event="gear_click"', "")
        assert "calendar_subscribe_click" not in page.replace(
            'data-ga-event="calendar_subscribe_click"', ""
        )
        assert "<script" not in re.sub(
            r"<script[^>]*ld\+json.*?</script>", "", page, flags=re.S
        )


# ---- the behavior, executed


def test_a_gear_click_sends_placement_type_and_host_only(tmp_path, tag_js, water_page):
    anchor = _anchors(water_page, "gear_click")[0]
    ran = _click(tmp_path, tag_js, anchor, {"navigator": {"doNotTrack": "0"}})
    assert ran["events"] == [
        [
            "event",
            "gear_click",
            {
                "placement": "water",
                "link_type": "amazon_search",
                "link_host": "www.amazon.com",
            },
        ]
    ]
    blob = json.dumps(ran["events"])
    assert "tag=" not in blob
    assert "?k=" not in blob
    assert "https://" not in blob


def test_a_calendar_click_sends_placement_type_and_host_only(
    tmp_path, tag_js, water_page
):
    anchor = _anchors(water_page, "calendar_subscribe_click")[0]
    ran = _click(tmp_path, tag_js, anchor, {"navigator": {}})
    assert ran["events"] == [
        [
            "event",
            "calendar_subscribe_click",
            {"placement": "water", "link_type": "ics", "link_host": "example.invalid"},
        ]
    ]


def test_a_click_off_a_marked_link_sends_nothing(tmp_path, tag_js):
    assert _click(tmp_path, tag_js, None, {"navigator": {}})["events"] == []


def test_an_unlisted_event_name_is_never_sent(tmp_path, tag_js):
    anchor = {
        "href": "https://example.invalid/x",
        "data-ga-event": "purchase",
        "data-ga-placement": "water",
        "data-ga-type": "x",
    }
    assert _click(tmp_path, tag_js, anchor, {"navigator": {}})["events"] == []


OPT_OUTS = {
    "gpc": {"navigator": {"globalPrivacyControl": True}},
    "dnt-1": {"navigator": {"doNotTrack": "1"}},
    "dnt-yes": {"navigator": {"doNotTrack": "yes"}},
    "window-dnt": {"navigator": {}, "window": {"doNotTrack": "1"}},
    "footer-opt-out-stored": {"navigator": {}, "storage": {KEY: "1"}},
    "ga-disable-after-load": {
        "navigator": {},
        "disableAfterLoad": "ga-disable-" + TEST_ID,
    },
}


@pytest.mark.parametrize("event", ["gear_click", "calendar_subscribe_click"])
@pytest.mark.parametrize("name", sorted(OPT_OUTS))
def test_no_event_under_any_opt_out(tmp_path, tag_js, water_page, event, name):
    anchor = _anchors(water_page, event)[0]
    ran = _click(tmp_path, tag_js, anchor, OPT_OUTS[name])
    assert ran["events"] == []
    if name != "ga-disable-after-load":
        assert ran["clickListeners"] == 0  # the tag returned before registering


def test_negative_control_catches_a_removed_ga_disable_check(
    tmp_path, tag_js, water_page
):
    anchor = _anchors(water_page, "gear_click")[0]
    sabotaged = tag_js.replace(GATE, "if (!a) return;", 1)
    assert sabotaged != tag_js  # the sabotage landed
    ran = _click(tmp_path, sabotaged, anchor, OPT_OUTS["ga-disable-after-load"])
    assert ran["events"] != []


def test_negative_control_catches_a_removed_gpc_dnt_and_stored_opt_out_guard(
    tmp_path, tag_js, water_page
):
    anchor = _anchors(water_page, "calendar_subscribe_click")[0]
    for guard, name in (
        ("if (n.globalPrivacyControl === true) return;", "gpc"),
        ('if (dnt === "1" || dnt === "yes") return;', "dnt-1"),
        ("if (optedOut) return;", "footer-opt-out-stored"),
    ):
        sabotaged = tag_js.replace(guard, "", 1)
        assert sabotaged != tag_js  # the sabotage landed
        ran = _click(tmp_path, sabotaged, anchor, OPT_OUTS[name])
        assert ran["events"] != [], name


def test_negative_control_catches_a_full_url_in_the_event(tmp_path, tag_js, water_page):
    anchor = _anchors(water_page, "gear_click")[0]
    sabotaged = tag_js.replace('link_host: a.hostname || ""', "link_host: a.href", 1)
    assert sabotaged != tag_js  # the sabotage landed
    ran = _click(tmp_path, sabotaged, anchor, {"navigator": {}})
    assert "tag=" in json.dumps(ran["events"])  # what the clean tag must not do


# ---- the privacy page


def _text(page: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", page)))


def test_privacy_page_states_what_the_events_record(site_dir):
    page = (site_dir / "privacy" / "index.html").read_text(encoding="utf-8")
    assert page.count('id="link-clicks"') == 1
    text = _text(page)
    for phrase in (
        "Link click events.",
        "which kind of page it was on",
        "the kind of link",
        "the link\u2019s host name",
        "It does not record the full link",
        "the affiliate tag and the search terms are not part of these events",
        "nothing is recorded if your browser sends Global Privacy Control or Do Not Track, or if you opted out",
    ):
        assert phrase in text, phrase


def test_privacy_page_without_analytics_has_no_click_event_paragraph(tmp_path):
    out = _build(tmp_path, None)
    assert "link-clicks" not in (out / "privacy" / "index.html").read_text(
        encoding="utf-8"
    )
