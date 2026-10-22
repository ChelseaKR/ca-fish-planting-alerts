"""Three claims the 2026-10-21 structured-data audit found the site could not
stand behind, and what each page says now.

1. When a license is chosen for the snapshot (one named constant,
   ``site.DATASET_LICENSE_URL``, which also drives the Dataset and /data/),
   /about/ says the same in visible text. Which license is the owner's call
   and is still open, so the default states none.
2. /about/ no longer says map locations come from USGS as if pages showed a
   map: it says the pages show none.
3. The support FAQ's two app answers are true before launch (the app is not
   on the App Store yet) and are the old words once the launch switch is on.
   The visible text and the FAQPage JSON-LD stay word for word identical in
   both states.

Pages are read with html.parser, never with a regex over tags. Each negative
control asserts that its sabotage changed the input before it asserts that
the check caught it.
"""

from __future__ import annotations

import datetime as dt
import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
CDFW_TERMS = "https://wildlife.ca.gov/Conditions-of-Use"
NOT_YET = "The iPhone app is not in the App Store yet"


class _Page(HTMLParser):
    """Visible text (script and style skipped), JSON-LD blocks, h2 text, and
    the links with their hrefs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._in_ld = False
        self._in_h2 = False
        self.text: list[str] = []
        self.ld: list[str] = []
        self.h2: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script":
            self._skip += 1
            self._in_ld = a.get("type") == "application/ld+json"
            if self._in_ld:
                self.ld.append("")
        elif tag == "style":
            self._skip += 1
        elif tag == "h2":
            self._in_h2 = True
            self.h2.append("")
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
            self._in_ld = False
        elif tag == "h2":
            self._in_h2 = False

    def handle_data(self, data):
        if self._in_ld:
            self.ld[-1] += data
        elif not self._skip:
            self.text.append(data)
            if self._in_h2:
                self.h2[-1] += data


def _read(html: str) -> _Page:
    p = _Page()
    p.feed(html)
    return p


def _flat(s: str) -> str:
    return " ".join(s.split())


def _visible(html: str) -> str:
    return _flat("".join(_read(html).text))


def _faq(html: str) -> list[dict]:
    [block] = _read(html).ld
    [node] = [n for n in json.loads(block)["@graph"] if n["@type"] == "FAQPage"]
    return node["mainEntity"]


def _build(root: Path, **extra) -> Path:
    _run(root, **extra)
    return root / "site"


def _rebuild(root: Path, **kwargs) -> Path:
    """Render the about page again from the same snapshot with other
    build_site settings (the license is a build_site argument, not a cli one)."""
    snap = _run(root)
    site.build_site(snap, root / "other", base_url=BASE_URL, **kwargs)
    return root / "other"


def _run(root: Path, **extra):
    return cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        **extra,
    )


@pytest.fixture(scope="module")
def before_launch(tmp_path_factory) -> Path:
    return _build(tmp_path_factory.mktemp("before"))


@pytest.fixture(scope="module")
def after_launch(tmp_path_factory) -> Path:
    return _build(tmp_path_factory.mktemp("after"), app_store_live=True)


def _page(out: Path, slug: str) -> str:
    return (out / slug / "index.html").read_text(encoding="utf-8")


# ---- 1. the Dataset license ---------------------------------------------------


def _dataset(html: str) -> dict:
    [block] = _read(html).ld
    [node] = [n for n in json.loads(block)["@graph"] if n["@type"] == "Dataset"]
    return node


CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"


def test_no_license_is_stated_until_the_owner_chooses_one(before_launch):
    """The owner's decision is open, so the default is none: nothing in the
    Dataset or the page text claims a license for the compiled snapshot."""
    assert site.DATASET_LICENSE_URL == ""
    html = _page(before_launch, "about")
    ds = _dataset(html)
    assert "license" not in ds
    assert ds["isBasedOn"]["license"] == CDFW_TERMS
    assert "License stated for the machine-readable snapshot" not in _visible(html)
    notice = (Path(__file__).resolve().parents[2] / "NOTICE").read_text("utf-8")
    assert CDFW_TERMS in notice  # NOTICE is where the snapshot's terms are recorded


def test_a_chosen_license_reaches_the_dataset_and_the_page_text(tmp_path):
    out = _rebuild(tmp_path, dataset_license_url=CC0)
    html = _page(out, "about")
    ds = _dataset(html)
    assert ds["license"] == CC0
    assert ds["isBasedOn"]["license"] == CDFW_TERMS
    assert CC0 in _read(html).links
    assert f"License stated for the machine-readable snapshot: {CC0}." in _visible(html)


def test_negative_control_license_check_catches_a_changed_value(tmp_path):
    out = _rebuild(tmp_path, dataset_license_url=CC0)
    html = _page(out, "about")
    sabotaged = html.replace(CC0, "https://example.invalid/none")
    assert sabotaged != html  # the sabotage landed
    assert _dataset(sabotaged)["license"] != CC0
    assert CC0 not in _visible(sabotaged)


# ---- 2. the water locations paragraph -----------------------------------------


def test_about_says_pages_show_no_map_and_does_not_promise_one(before_launch):
    text = _visible(_page(before_launch, "about"))
    assert (
        "The pages on this site do not show a map or coordinates for any water." in text
    )
    assert "Each California water page links to CDFW's own map instead." in text
    # the old sentences that read as if pages carried a map
    assert "Map locations come from public-domain federal data" not in text
    assert "never placed on a map" not in text
    assert "a lake's point is inside the lake" not in text
    # the federal sources are still credited, because the data files use them
    assert "U.S. Geological Survey" in text and "U.S. Census Bureau" in text


def test_the_claim_matches_the_pages_no_water_page_shows_a_map(before_launch):
    for f in before_launch.glob("water/*/index.html"):
        html = f.read_text(encoding="utf-8")
        assert "geo" not in json.dumps(_read(html).ld).lower().replace("geographic", "")
        assert "<iframe" not in html and "openstreetmap" not in html.lower()


def test_negative_control_catches_the_old_locations_claim(before_launch):
    html = _page(before_launch, "about")
    old = html.replace(
        "The pages on this site do not show a map or coordinates for any water.",
        "Map locations come from public-domain federal data.",
    )
    assert old != html  # the sabotage landed
    assert "do not show a map" not in _visible(old)


# ---- 3. the support FAQ before and after launch -------------------------------


def test_before_launch_every_faq_answer_is_true_today(before_launch):
    html = _page(before_launch, "support")
    text = _visible(html)
    heads = [_flat(h) for h in _read(html).h2]
    answers = {q["name"]: q["acceptedAnswer"]["text"] for q in _faq(html)}
    assert len(answers) == 5
    for name, answer in answers.items():
        assert name in heads
        assert answer in text  # word for word
    app_answers = [a for a in answers.values() if "app" in a.lower()]
    assert len(app_answers) >= 2
    alert = answers["How will the app's alerts work?"]
    restore = answers["How will restoring a purchase on a new phone work?"]
    assert alert.startswith(NOT_YET) and restore.startswith(NOT_YET)
    # the live-state questions assume an installed app
    assert "Why didn't the app alert me?" not in answers
    assert "How do I restore my purchase on a new phone?" not in answers
    assert "Why didn't the app alert me?" not in text


def test_after_launch_the_faq_is_the_original_words(after_launch):
    html = _page(after_launch, "support")
    text = _visible(html)
    answers = {q["name"]: q["acceptedAnswer"]["text"] for q in _faq(html)}
    assert set(
        site_names := [site._APP_ALERTS_FAQ_LIVE[0], site._APP_RESTORE_FAQ_LIVE[0]]
    ) <= set(answers)
    assert site_names == [
        "Why didn't the app alert me?",
        "How do I restore my purchase on a new phone?",
    ]
    for answer in answers.values():
        assert answer in text
    assert "not in the App Store yet" not in text


def test_visible_faq_and_json_ld_match_in_both_states(before_launch, after_launch):
    for out in (before_launch, after_launch):
        html = _page(out, "support")
        text = _visible(html)
        for q in _faq(html):
            assert q["acceptedAnswer"]["text"] in text


def test_the_flip_changes_only_the_flag_constants_not_the_faq_code():
    """The launch is the one line plus the changelog: the FAQ chooses its words
    from the same ``app_store_live`` the banner and badge read."""
    assert isinstance(site.APP_STORE_LIVE_DEFAULT, bool)
    assert site._support_faq("x", app_store_live=True)[3] == site._APP_ALERTS_FAQ_LIVE
    assert (
        site._support_faq("x", app_store_live=False)[3] == site._APP_ALERTS_FAQ_NOT_YET
    )


def test_negative_control_catches_an_answer_that_drifts_from_the_page(before_launch):
    html = _page(before_launch, "support")
    sabotaged = html.replace("sends no alerts today", "sends alerts today", 1)
    assert sabotaged != html  # the sabotage landed
    text = _visible(sabotaged)
    answers = [q["acceptedAnswer"]["text"] for q in _faq(sabotaged)]
    assert any(a not in text for a in answers)


def test_negative_control_catches_an_answer_that_claims_the_app_is_installed(
    before_launch,
):
    html = _page(before_launch, "support")
    sabotaged = html.replace(NOT_YET, "The app is installed", 1)
    assert sabotaged != html
    answers = [q["acceptedAnswer"]["text"] for q in _faq(sabotaged)]
    assert not all(a.startswith(NOT_YET) for a in answers if "alert" in a[:60])
