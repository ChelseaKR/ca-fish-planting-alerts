"""The website's Google Analytics 4 tag (DECISIONS 0011).

With no measurement ID the build emits nothing: no script, no Google host,
and privacy copy that says nothing is collected. With one, every page carries
the tag behind a Global Privacy Control / Do Not Track guard. The guard is
string-checked, and also executed under node against a stub browser, so a
guard that is present but does not stop anything fails too.

Every negative control asserts that its sabotage changed the input before it
asserts that the check caught it; a sabotage that silently no-ops would
otherwise read as a pass.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import plistlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
TEST_ID = "G-TEST12345"

GPC_GUARD = "if (n.globalPrivacyControl === true) return;"
DNT_GUARD = 'if (dnt === "1" || dnt === "yes") return;'

# The EU 27, the rest of the EEA, the UK and Switzerland.
EXPECTED_DENIED_REGIONS = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",
    "IS", "LI", "NO",
    "GB", "CH",
}  # fmt: skip

# Claims the no-analytics copy makes about the website that are false once
# the tag is on. Matched against page text with tags stripped and whitespace
# collapsed, case-insensitively.
FALSE_WITH_ANALYTICS = (
    "no javascript runs",
    "no cookies are set",
    "literally nothing is collected",
    "nothing you do here leaves your browser",
    "adds no collection",
    "does not add any collection",
    "neither the trout truck website nor",
    "no page makes a request to any server other than",
    "no request made by a page on this site contacts",
    "what it collects (nothing)",
    "site and ios app collect: nothing",
    "nothing is collected from anyone",
)


def _build(root: Path, ga4_measurement_id: str | None) -> Path:
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
        ga4_measurement_id=ga4_measurement_id,
    )
    return out


def _main_argv(root: Path) -> list[str]:
    """The production entry point (what publish.yml runs), kept off the
    repo's own data files."""
    return [
        "--fixture", str(FRESH),
        "--fixture-fetched-at", "2026-09-13T12:00:00Z",
        "--run-today", "2026-09-13",
        "--history", str(root / "history.json"),
        "--aliases", str(root / "aliases.json"),
        "--site-out", str(root / "site"),
        "--base-url", BASE_URL,
    ]  # fmt: skip


def _pages(out: Path) -> dict[str, str]:
    pages = {
        str(f.relative_to(out)): f.read_text(encoding="utf-8")
        for f in sorted(out.rglob("*.html"))
    }
    # index, about, privacy, support, 404 and the water pages: a build that
    # produced almost nothing must not pass every per-page check vacuously
    assert len(pages) > 10, sorted(pages)
    return pages


# Any <script> element, whatever its attributes, case or end-tag spelling.
# The exact-string `<script>...</script>` this replaced let a script with an
# attribute, or one closed as `</script >`, through: its JavaScript then
# counted as visible page text in the copy checks below, and was not seen by
# _scripts(). CodeQL flagged both uses as py/bad-tag-filter.
_SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script\b[^>]*>", re.IGNORECASE | re.DOTALL)


def _text(html: str) -> str:
    """What a reader or a search result shows: the visible text plus the
    meta description, lowercased, whitespace collapsed."""
    description = re.search(r'<meta name="description" content="([^"]*)">', html)
    text = _SCRIPT.sub(" ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    if description:
        text += " " + description.group(1)
    return re.sub(r"\s+", " ", text).lower()


def _ga_markers(html: str) -> list[str]:
    """Anything that would mean analytics reached the page."""
    lowered = html.lower()
    markers = ["<script", "googletagmanager", "google-analytics", "gtag", "datalayer"]
    found = [m for m in markers if m in lowered]
    found += [i for i in (TEST_ID, site.GA4_MEASUREMENT_ID) if i and i in html]
    return found


def _scripts(html: str) -> list[str]:
    return _SCRIPT.findall(html)


def _guard_problems(html: str, measurement_id: str) -> list[str]:
    """String-level checks of the one inline script on a page."""
    scripts = _scripts(html)
    if html.lower().count("<script") != 1 or len(scripts) != 1:
        return [f"expected exactly one inline <script>, found {len(scripts)}"]
    js = scripts[0]
    problems = []
    for needle in (
        GPC_GUARD,
        DNT_GUARD,
        f'gtag("config", "{measurement_id}"',
        "allow_google_signals: false",
        "allow_ad_personalization_signals: false",
        "https://www.googletagmanager.com/gtag/js?id=",
    ):
        if needle not in js:
            problems.append(f"missing {needle!r}")
    if problems:
        return problems
    # both guards return before anything is set up or fetched
    first_effect = min(js.index("dataLayer"), js.index("googletagmanager"))
    for guard in (GPC_GUARD, DNT_GUARD):
        if js.index(guard) > first_effect:
            problems.append(f"{guard!r} runs after the tag starts")
    return problems


@pytest.fixture(scope="module")
def no_id_pages(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    return _pages(_build(tmp_path_factory.mktemp("no-id"), None))


@pytest.fixture(scope="module")
def id_pages(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    return _pages(_build(tmp_path_factory.mktemp("with-id"), TEST_ID))


# ---- configuration


def test_committed_measurement_id_is_empty_or_well_formed():
    """A typo in site.GA4_MEASUREMENT_ID fails here, in the PR that makes
    it, not in the nightly publish run."""
    configured = site.GA4_MEASUREMENT_ID
    assert site.ga4_measurement_id_or_none(configured) == (configured or None)


@pytest.mark.parametrize("value", [None, ""])
def test_unset_measurement_id_means_none(value: str | None):
    assert site.ga4_measurement_id_or_none(value) is None


@pytest.mark.parametrize(
    "value", ["UA-12345-1", "g-abc123", " G-ABC123", "G-ABC123\n", "G-", "GTM-ABC123"]
)
def test_malformed_measurement_id_is_refused(value: str):
    with pytest.raises(ValueError, match="G-XXXXXXXXXX"):
        site.ga4_measurement_id_or_none(value)


def test_consent_regions_are_the_eea_uk_and_switzerland():
    regions = site.GA4_ANALYTICS_DENIED_REGIONS
    assert len(regions) == len(set(regions)) == 32
    assert set(regions) == EXPECTED_DENIED_REGIONS


# ---- no ID: nothing at all


def test_build_with_no_id_emits_no_analytics_on_any_page(no_id_pages):
    for name, html in no_id_pages.items():
        assert _ga_markers(html) == [], name
        assert "google analytics" not in _text(html), name


def test_no_analytics_detector_is_not_vacuous(no_id_pages, id_pages):
    """Negative control: the detector above flags a page that has the tag,
    and flags a no-ID page once a script is injected into it."""
    for name, html in id_pages.items():
        assert _ga_markers(html), name
    original = no_id_pages["index.html"]
    sabotaged = original.replace("</head>", "<script></script></head>", 1)
    assert sabotaged != original  # the sabotage landed
    assert _ga_markers(sabotaged) == ["<script"]


def test_no_id_copy_still_says_the_site_collects_nothing(no_id_pages):
    privacy = _text(no_id_pages["privacy/index.html"])
    assert "no analytics, no advertising, no tracking" in privacy
    assert "no cookies are set and no javascript runs" in privacy
    assert "literally nothing is collected" in _text(no_id_pages["about/index.html"])


# ---- with an ID: the tag on every page, behind the guard


def test_build_with_id_emits_the_guarded_tag_on_every_page(id_pages):
    for name, html in id_pages.items():
        assert _guard_problems(html, TEST_ID) == [], name
        assert "<head>" in html and html.index("<script") < html.index("</head>"), name


def test_guard_checker_catches_a_missing_or_late_guard(id_pages):
    """Negative controls for _guard_problems: drop each guard, then move the
    GPC guard below the dataLayer set-up."""
    original = id_pages["index.html"]
    for guard in (GPC_GUARD, DNT_GUARD):
        sabotaged = original.replace(guard, "")
        assert sabotaged != original  # the sabotage landed
        assert _guard_problems(sabotaged, TEST_ID), guard
    moved = original.replace(GPC_GUARD, "").replace(
        'gtag("js"', GPC_GUARD + '\n  gtag("js"', 1
    )
    assert moved != original and GPC_GUARD in moved  # the sabotage landed
    assert _guard_problems(moved, TEST_ID) == [
        f"{GPC_GUARD!r} runs after the tag starts"
    ]


def test_id_build_copy_describes_ga4_and_keeps_the_app_at_data_not_collected(id_pages):
    privacy = _text(id_pages["privacy/index.html"])
    for phrase in (
        "uses google analytics 4",
        "global privacy control",
        "do not track",
        "the eea, the uk and switzerland",
        "google signals and ad personalisation are turned off",
        "14 months",
        "the trout truck ios app collects no data at all",
        "app store privacy label: data not collected",
    ):
        assert phrase in privacy, phrase
    assert "google analytics" in _text(id_pages["about/index.html"])
    assert "uses google analytics" in _text(id_pages["support/index.html"])
    description = re.search(
        r'<meta name="description" content="([^"]+)">', id_pages["privacy/index.html"]
    )
    assert description is not None
    assert (
        "website uses Google Analytics; the app collects nothing"
        in description.group(1)
    )


def test_id_build_makes_no_claim_that_analytics_made_false(id_pages, no_id_pages):
    for name, html in id_pages.items():
        text = _text(html)
        hits = [claim for claim in FALSE_WITH_ANALYTICS if claim in text]
        assert hits == [], (name, hits)
    # Negative control: the same list does match the no-analytics copy, so
    # it is checking real sentences and not phrases that never render.
    no_id_hits = {
        claim
        for html in no_id_pages.values()
        for claim in FALSE_WITH_ANALYTICS
        if claim in _text(html)
    }
    assert no_id_hits == set(FALSE_WITH_ANALYTICS)


# ---- the guard, executed

_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[2], "utf8");
const c = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const appended = [];
const navigator = Object.assign({}, c.navigator);
const window = Object.assign({}, c.window);
const document = {
  createElement: (tag) => ({ tagName: tag }),
  head: { appendChild: (el) => { appended.push(el); } },
  addEventListener: () => {},  // footer opt-out: test_site_analytics_optout.py
};
const context = { navigator, window, document, Date, encodeURIComponent };
vm.runInContext(code, vm.createContext(context));
const dataLayer = window.dataLayer ? window.dataLayer.map((a) => Array.from(a)) : null;
process.stdout.write(JSON.stringify({ dataLayer, appended }));
"""


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI to execute the GA4 guard")
        pytest.skip("node is not installed; the guard is only string-checked")
    return node


def _run_tag(
    tmp_path: Path,
    js: str,
    *,
    navigator: dict[str, object] | None = None,
    window: dict[str, object] | None = None,
) -> dict[str, object]:
    node = _node()
    harness = tmp_path / "harness.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    script = tmp_path / "tag.js"
    script.write_text(js, encoding="utf-8")
    case = tmp_path / "case.json"
    case.write_text(
        json.dumps({"navigator": navigator or {}, "window": window or {}}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [node, str(harness), str(script), str(case)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    parsed: dict[str, object] = json.loads(result.stdout)
    return parsed


def _tag_js(id_pages: dict[str, str]) -> str:
    scripts = _scripts(id_pages["index.html"])
    assert len(scripts) == 1
    return scripts[0]


def test_tag_loads_ga4_with_consent_defaults_when_no_signal_is_sent(tmp_path, id_pages):
    ran = _run_tag(tmp_path, _tag_js(id_pages), navigator={"doNotTrack": "0"})
    assert ran["appended"] == [
        {
            "tagName": "script",
            "async": True,
            "src": f"https://www.googletagmanager.com/gtag/js?id={TEST_ID}",
        }
    ]
    data_layer = ran["dataLayer"]
    assert isinstance(data_layer, list)
    assert [entry[0] for entry in data_layer] == ["consent", "consent", "js", "config"]
    ads_denied = {
        "ad_storage": "denied",
        "ad_user_data": "denied",
        "ad_personalization": "denied",
    }
    everywhere, regional = data_layer[0], data_layer[1]
    assert everywhere == [
        "consent",
        "default",
        {**ads_denied, "analytics_storage": "granted"},
    ]
    assert regional[:2] == ["consent", "default"]
    assert {k: v for k, v in regional[2].items() if k != "region"} == {
        **ads_denied,
        "analytics_storage": "denied",
    }
    assert set(regional[2]["region"]) == EXPECTED_DENIED_REGIONS
    assert data_layer[3] == [
        "config",
        TEST_ID,
        {"allow_google_signals": False, "allow_ad_personalization_signals": False},
    ]


@pytest.mark.parametrize(
    ("navigator", "window"),
    [
        ({"globalPrivacyControl": True}, {}),
        ({"doNotTrack": "1"}, {}),
        ({"doNotTrack": "yes"}, {}),
        ({}, {"doNotTrack": "1"}),
        ({"msDoNotTrack": "1"}, {}),
        ({"globalPrivacyControl": True, "doNotTrack": "0"}, {}),
    ],
)
def test_tag_does_nothing_under_gpc_or_dnt(tmp_path, id_pages, navigator, window):
    ran = _run_tag(tmp_path, _tag_js(id_pages), navigator=navigator, window=window)
    assert ran == {"dataLayer": None, "appended": []}


@pytest.mark.parametrize(
    ("guard", "navigator"),
    [(GPC_GUARD, {"globalPrivacyControl": True}), (DNT_GUARD, {"doNotTrack": "1"})],
)
def test_executed_guard_check_catches_a_removed_guard(
    tmp_path, id_pages, guard, navigator
):
    """Negative control: with the guard deleted, the same signal no longer
    stops the tag, and the run above would have seen that."""
    original = _tag_js(id_pages)
    sabotaged = original.replace(guard, "")
    assert sabotaged != original  # the sabotage landed
    ran = _run_tag(tmp_path, sabotaged, navigator=navigator)
    assert ran["appended"] != []
    assert ran["dataLayer"] is not None


# ---- the production entry point reads the committed ID


def test_cli_main_emits_the_committed_id(tmp_path, monkeypatch):
    monkeypatch.setattr(site, "GA4_MEASUREMENT_ID", TEST_ID)
    assert cli.main(_main_argv(tmp_path)) == 0
    for name, html in _pages(tmp_path / "site").items():
        assert _guard_problems(html, TEST_ID) == [], name


def test_cli_main_emits_nothing_when_the_committed_id_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(site, "GA4_MEASUREMENT_ID", "")
    assert cli.main(_main_argv(tmp_path)) == 0
    for name, html in _pages(tmp_path / "site").items():
        assert _ga_markers(html) == [], name


def test_cli_main_refuses_a_malformed_id_before_writing_anything(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(site, "GA4_MEASUREMENT_ID", "UA-12345-1")
    assert site.GA4_MEASUREMENT_ID == "UA-12345-1"  # the sabotage landed
    assert cli.main(_main_argv(tmp_path)) == 1
    assert "run refused" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


# ---- website only: the app never gets analytics


def test_the_app_stays_data_not_collected():
    """DECISIONS 0011 is website-only. The iOS privacy manifest declares no
    collected data and no tracking, nothing under ios/ references Google
    Analytics, and the App Store copy still says the app collects nothing."""
    ios = REPO_ROOT / "ios"
    if not ios.is_dir():
        pytest.skip("ios/ is not on this branch")
    manifests = list(ios.rglob("PrivacyInfo.xcprivacy"))
    assert manifests
    for manifest in manifests:
        plist = plistlib.loads(manifest.read_bytes())
        assert plist["NSPrivacyCollectedDataTypes"] == [], manifest
        assert plist["NSPrivacyTracking"] is False, manifest
    needles = ("googletagmanager", "google-analytics", "gtag", "googleanalytics")
    for f in ios.rglob("*"):
        if ".build" in f.parts or "DerivedData" in f.parts:
            continue
        if f.is_file() and f.suffix in {".swift", ".plist", ".xcprivacy", ".pbxproj"}:
            lowered = f.read_text(encoding="utf-8", errors="ignore").lower()
            assert not [n for n in needles if n in lowered], f
    listing = (REPO_ROOT / "docs" / "APP-STORE-LISTING.md").read_text(encoding="utf-8")
    assert "Data Not Collected" in listing
    assert (
        "Do you or your third-party partners collect data from this app?** No."
        in listing
    )
