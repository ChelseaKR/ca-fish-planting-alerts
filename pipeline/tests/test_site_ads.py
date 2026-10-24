"""Display ads behind a flag that is off (cfpa/ads.py, docs/adr/0040).

Off, no page names AdSense and there is no ads.txt. On, exactly the pages in
``ads.AD_PAGES`` carry one unit, nowhere near the Amazon disclosure, and the
privacy, about and footer copy describe the ads. The slot's script is also
executed under node against a stub browser: GPC, Do Not Track and the
visitor's opt-out load nothing, and an unfilled, failed or silent unit is
removed rather than left as an empty box.

Every negative control asserts that its sabotage changed the input before it
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

import pytest

from cfpa import ads, cli

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
GA4_ID = "G-TEST12345"
PUB_ID = "ca-pub-0000000000000001"
SLOT_ID = "1234567890"
EFFECTIVE = "2026-11-01"
ADSENSE_HOST = "googlesyndication.com"


def _build(root: Path) -> dict[str, str]:
    out = root / "site"
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        ga4_measurement_id=GA4_ID,
    )
    pages = {
        str(p.relative_to(out)): p.read_text(encoding="utf-8")
        for p in out.rglob("*")
        if p.is_file() and p.suffix in {".html", ".txt", ".css"}
    }
    return pages


def _turn_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ads, "ADS_ENABLED", True)
    monkeypatch.setattr(ads, "ADSENSE_PUBLISHER_ID", PUB_ID)
    monkeypatch.setattr(ads, "ADSENSE_SLOT_ID", SLOT_ID)
    monkeypatch.setattr(ads, "ADS_EFFECTIVE_DATE", EFFECTIVE)


@pytest.fixture(scope="module")
def off_pages(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    return _build(tmp_path_factory.mktemp("ads-off"))


@pytest.fixture(scope="module")
def on_pages(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    with pytest.MonkeyPatch.context() as mp:
        _turn_on(mp)
        return _build(tmp_path_factory.mktemp("ads-on"))


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).lower()


def _kind(name: str) -> str:
    """Which template a written page came from, by its path."""
    parts = name.split("/")
    if name == "index.html":
        return "home"
    return parts[0] if len(parts) > 1 else name


# ---- off by default


def test_committed_switch_is_off() -> None:
    assert ads.ADS_ENABLED is False
    assert ads.ads_config() is ads.ADS_OFF


def test_off_build_has_no_ads_anywhere(off_pages: dict[str, str]) -> None:
    assert "ads.txt" not in off_pages
    for name, body in off_pages.items():
        assert "google-adsense-account" not in body, name
        assert ADSENSE_HOST not in body, name
        assert "adsbygoogle" not in body, name
        assert 'id="ads"' not in body, name
    assert "there are no ads on this site" in _text(off_pages["about/index.html"])


# ---- the settings are checked


@pytest.mark.parametrize(
    ("pub", "slot", "date"),
    [
        ("", SLOT_ID, EFFECTIVE),
        ("pub-0000000000000001", SLOT_ID, EFFECTIVE),
        ("ca-pub-123", SLOT_ID, EFFECTIVE),
        (PUB_ID, "", EFFECTIVE),
        (PUB_ID, "slot-1", EFFECTIVE),
        (PUB_ID, SLOT_ID, ""),
        (PUB_ID, SLOT_ID, "November 1"),
    ],
)
def test_on_without_good_ids_fails_instead_of_shipping_an_empty_slot(
    pub: str, slot: str, date: str
) -> None:
    with pytest.raises(ValueError):
        ads.ads_config(True, pub, slot, date)


def test_good_ids_pass_and_off_ignores_them() -> None:
    config = ads.ads_config(True, f" {PUB_ID} ", SLOT_ID, EFFECTIVE)
    assert config.enabled and config.publisher_id == PUB_ID
    assert config.ads_txt_publisher == "pub-0000000000000001"
    assert ads.ads_config(False, "", "nonsense", "") is ads.ADS_OFF
    connect = ads.ads_config(False, PUB_ID, "", "")
    assert connect.enabled is False and connect.publisher_id == PUB_ID
    with pytest.raises(ValueError):
        ads.ads_config(False, "pub-123", "", "")


def test_publisher_id_alone_connects_the_site_and_shows_no_ads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ads, "ADSENSE_PUBLISHER_ID", PUB_ID)
    pages = _build(tmp_path)
    assert pages["ads.txt"].startswith("google.com, pub-0000000000000001, DIRECT")
    meta = f'<meta name="google-adsense-account" content="{PUB_ID}">'
    assert meta in pages["index.html"]
    for name, body in pages.items():
        assert "adsbygoogle" not in body, name
        assert ADSENSE_HOST not in body, name
        assert 'id="ads"' not in body, name
    assert ".ad-slot" not in pages["assets/style.css"]


def test_ads_need_the_analytics_copy(tmp_path: Path, monkeypatch) -> None:
    _turn_on(monkeypatch)
    with pytest.raises(ValueError, match="GA4"):
        cli.run(
            fixture_path=str(FRESH),
            history_path=tmp_path / "history.json",
            aliases_path=tmp_path / "aliases.json",
            schema_path=SCHEMA_PATH,
            site_out=tmp_path / "site",
            base_url=BASE_URL,
            fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
            run_today=dt.date(2026, 9, 13),
            ga4_measurement_id=None,
        )


# ---- on: where the unit goes


def test_on_build_writes_ads_txt(on_pages: dict[str, str]) -> None:
    assert on_pages["ads.txt"] == (
        "google.com, pub-0000000000000001, DIRECT, f08c47fec0942fa0\n"
    )


def test_unit_is_on_listing_pages_and_never_on_the_excluded_ones(
    on_pages: dict[str, str],
) -> None:
    with_unit = {n for n, b in on_pages.items() if 'class="adsbygoogle"' in b}
    kinds = {_kind(n) for n in with_unit}
    assert {"water", "county", "region"} <= kinds, kinds
    never = {"home", "gear", "about", "privacy", "support", "guide", "data", "404.html"}
    assert kinds.isdisjoint(never), kinds & never
    for name in with_unit:
        assert on_pages[name].count('class="adsbygoogle"') == 1, name
        assert on_pages[name].count(f'data-ad-client="{PUB_ID}"') == 1, name


def test_unit_sits_after_the_content_and_far_from_the_amazon_disclosure(
    on_pages: dict[str, str],
) -> None:
    waters = [n for n in on_pages if n.startswith("water/") and n.endswith(".html")]
    assert waters
    for name in waters:
        body = on_pages[name]
        disclosure = body.index('id="gear-disclosure"')
        slot = body.index('id="ad-slot"')
        main_end = body.index("</main>")
        assert disclosure < slot < main_end, name
        # Something other than the gear section sits between them: at least
        # one more heading, so the ad never reads as part of the gear list.
        assert "<h2" in body[disclosure:slot] or "</section>" in body[disclosure:slot]
        assert "Advertisement" in body[slot:main_end]
        assert "amazon" not in body[slot:main_end].lower(), name


def test_on_build_copy_describes_the_ads(on_pages: dict[str, str]) -> None:
    privacy = _text(on_pages["privacy/index.html"])
    for phrase in (
        f"since {EFFECTIVE}, some pages on this website show one ad from google adsense",
        "non-personalized ads only",
        "restricted data processing",
        "do not sell or share",
        "global privacy control and do not track are honored",
        "turn off ads",
        "the eea, the uk and switzerland",
        "where there are never ads",
    ):
        assert phrase in privacy, phrase
    assert "there are no ads on this site" not in privacy
    about = _text(on_pages["about/index.html"])
    assert "there are no ads on this site" not in about
    assert "non-personalized google ad" in about
    water = next(n for n in on_pages if n.startswith("water/"))
    assert "privacy/#ads" in on_pages[water]
    # The footer link is on every page, including those without a unit.
    assert "Ad choices: turn off ads on this device" in on_pages["index.html"]


def test_on_build_appends_the_slot_css(on_pages: dict[str, str]) -> None:
    css = on_pages["assets/style.css"]
    assert ".ad-slot.ad-pending{" in css
    assert 'ins.adsbygoogle[data-ad-status="unfilled"]' in css


# ---- the slot's script, executed

_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[2], "utf8");
const c = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const appended = [];
let observer = null;
let timer = null;
const attrs = {};
const unit = { getAttribute: (k) => (k in attrs ? attrs[k] : null) };
const label = { hidden: true };
const classes = new Set(["ad-slot", "ad-pending"]);
const box = {
  parentNode: null,
  hidden: false,
  attrs: { "aria-hidden": "true" },
  classList: { remove: (k) => classes.delete(k) },
  removeAttribute: (k) => { delete box.attrs[k]; },
  querySelector: (sel) => (sel === ".ad-label" ? label : unit),
};
const parent = { removeChild: (el) => { el.parentNode = null; } };
box.parentNode = parent;
const store = c.optedOut ? { "trout-truck:ads-opt-out": "1" } : {};
const window = Object.assign({}, c.window, {
  localStorage: { getItem: (k) => (k in store ? store[k] : null) },
  setTimeout: (fn) => { timer = fn; },
  MutationObserver: function (fn) { this.observe = () => { observer = fn; }; },
});
const navigator = Object.assign({}, c.navigator);
const document = {
  getElementById: (id) => (id === "ad-slot" ? box : null),
  createElement: (tag) => ({ tagName: tag }),
  head: { appendChild: (el) => { appended.push(el); } },
};
vm.runInContext(code, vm.createContext({ navigator, window, document }));
if (c.status !== undefined && observer) { attrs["data-ad-status"] = c.status; observer(); }
if (c.scriptError) { for (const el of appended) if (el.onerror) el.onerror(); }
if (c.timeout && timer) timer();
process.stdout.write(JSON.stringify({
  appended: appended.map((el) => ({ tagName: el.tagName, async: el.async, src: el.src })),
  npa: window.adsbygoogle ? window.adsbygoogle.requestNonPersonalizedAds : null,
  pushed: window.adsbygoogle ? window.adsbygoogle.length : 0,
  removed: box.parentNode === null,
  shown: !classes.has("ad-pending") && !("aria-hidden" in box.attrs) && !label.hidden,
}));
"""


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI to execute the ad slot's script")
        pytest.skip("node is not installed; the slot script is only string-checked")
    return node


def _slot_js(on_pages: dict[str, str]) -> str:
    name = next(n for n, b in on_pages.items() if 'id="ad-slot"' in b)
    body = on_pages[name]
    after = body[body.index('id="ad-slot"') :]
    m = re.search(r"<script>(.*?)</script>", after, re.S)
    assert m is not None
    return m.group(1)


def _run(tmp_path: Path, js: str, **case: object) -> dict[str, object]:
    node = _node()
    harness = tmp_path / "harness.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    script = tmp_path / "slot.js"
    script.write_text(js, encoding="utf-8")
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(case), encoding="utf-8")
    result = subprocess.run(
        [node, str(harness), str(script), str(case_path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    parsed: dict[str, object] = json.loads(result.stdout)
    return parsed


def test_slot_loads_non_personalized_ads_and_shows_only_when_filled(
    tmp_path: Path, on_pages: dict[str, str]
) -> None:
    js = _slot_js(on_pages)
    ran = _run(tmp_path, js, navigator={"doNotTrack": "0"})
    assert ran["appended"] == [
        {
            "tagName": "script",
            "async": True,
            "src": f"https://pagead2.{ADSENSE_HOST}/pagead/js/adsbygoogle.js?client={PUB_ID}",
        }
    ]
    assert ran["npa"] == 1 and ran["pushed"] == 1
    assert ran["shown"] is False and ran["removed"] is False  # still waiting
    filled = _run(tmp_path, js, status="filled")
    assert filled["shown"] is True and filled["removed"] is False


@pytest.mark.parametrize(
    "case",
    [
        {"status": "unfilled"},
        {"status": "unfill-optimized"},
        {"scriptError": True},
        {"timeout": True},
    ],
)
def test_slot_never_leaves_an_empty_box(
    tmp_path: Path, on_pages: dict[str, str], case: dict[str, object]
) -> None:
    ran = _run(tmp_path, _slot_js(on_pages), **case)
    assert ran["removed"] is True and ran["shown"] is False


@pytest.mark.parametrize(
    "case",
    [
        {"navigator": {"globalPrivacyControl": True}},
        {"navigator": {"doNotTrack": "1"}},
        {"window": {"doNotTrack": "yes"}},
        {"optedOut": True},
    ],
)
def test_privacy_signals_load_nothing(
    tmp_path: Path, on_pages: dict[str, str], case: dict[str, object]
) -> None:
    ran = _run(tmp_path, _slot_js(on_pages), **case)
    assert ran["appended"] == [] and ran["pushed"] == 0
    assert ran["removed"] is True


def test_negative_control_a_slot_without_the_guard_loads_under_gpc(
    tmp_path: Path, on_pages: dict[str, str]
) -> None:
    js = _slot_js(on_pages)
    sabotaged = js.replace("n.globalPrivacyControl === true || ", "")
    assert sabotaged != js  # the sabotage landed
    ran = _run(tmp_path, sabotaged, navigator={"globalPrivacyControl": True})
    assert ran["appended"] != []
