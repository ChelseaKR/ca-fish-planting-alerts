"""No page promises an iPhone app (IA phase 1, D1, 2026-11-21).

Apple's rejection of the app was upheld on 2026-11-17 (DECISIONS 0073), so
the sentence "An iOS app ... is on its way" on every California and
Tennessee water page, every county page and the home page, and the about and
support pages' "not in the App Store yet", were no longer true. They are
gone, with the launch switch off and on. The about page's #app section and
the support page's alert question answer with the calendar instead, word
for word in the approved copy. The switch itself stays (DECISIONS 0028).

Built from the pinned fixtures only, with Tennessee, Massachusetts and
Michigan on. Every file the build writes is read, not only the pages. Each
negative control asserts that its sabotage changed the input before it
asserts that the check caught it.

The leftovers (2026-11-21, second pass): with the switch off, no file names
an app at all. The about page lost "The iOS app has no analytics of any
kind" and its privacy heading's app clause; the privacy page covers the
website only, with one date; the support page's privacy question is about
the site; the terms page, /states/ and every state hub drop their app
lines; and the about, privacy and support descriptions name the website
only. These are read in two more builds: one as production builds today
(analytics on, web push and ads off) and one with analytics, web push and
ads all on, so every privacy branch is read. With the switch on, the app
wording is still there.
"""

from __future__ import annotations

import datetime as dt
import html as html_lib
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

from cfpa import ads, cli, launch_check, push, site

FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "states"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
PROMISES = ("on its way", "not in the App Store yet")
# The sentence each page carried before 2026-11-21, for the negative controls.
OLD_WATER_LINE = (
    "An iOS app with a notification when Lake X appears in a new week is on "
    'its way (<a href="../../about/#app">how it will work</a>).'
)
OLD_ABOUT_LINE = (
    "<p>The app is not in the App Store yet; this page will link to it once it is.</p>"
)
ABOUT_APP = (
    "No. Trout Truck is a website. To follow a water, subscribe to its "
    "calendar on the water's page: each new week or date the agency schedules "
    "shows up in your calendar."
)
SUPPORT_Q = "Can I get an alert when a water is scheduled?"
SUPPORT_A = (
    "Yes, by calendar. On a California or Tennessee water's page, press Apple "
    "Calendar or Google Calendar. Each new week or date the agency schedules "
    "then shows up in your calendar. There is no Trout Truck app."
)


GA4_ID = "G-TEST12345"
PUSH_API = "https://abc.lambda-url.us-east-1.on.aws"
PUSH_KEY = "B" + "A" * 86


def _build(
    root: Path,
    *,
    app_store_live: bool = False,
    ga4: bool = False,
    push_on: bool = False,
    states: tuple[str, ...] = ("TN", "MA", "MI"),
) -> Path:
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA,
        site_out=root / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=states,
        states_fixtures=STATE_FIXTURES,
        app_store_live=app_store_live,
        ga4_measurement_id=GA4_ID if ga4 else None,
        push=push.PushConfig(api_url=PUSH_API, vapid_public_key=PUSH_KEY)
        if push_on
        else None,
    )
    return root / "site"


@pytest.fixture(scope="module")
def off(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("no-app-off"))


@pytest.fixture(scope="module")
def on(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("no-app-on"), app_store_live=True)


@pytest.fixture(scope="module")
def prod(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """As production builds today: analytics on, web push, ads and the
    switch off."""
    return _build(tmp_path_factory.mktemp("no-app-prod"), ga4=True)


@pytest.fixture(scope="module")
def with_ads(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Analytics, web push and ads on, California only, for the privacy
    page's push and ads branches (both off in production today; ads,
    docs/adr/0040)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ads, "ADS_ENABLED", True)
        mp.setattr(ads, "ADSENSE_PUBLISHER_ID", "ca-pub-1234567890123456")
        mp.setattr(ads, "ADSENSE_SLOT_ID", "1234567890")
        mp.setattr(ads, "ADS_EFFECTIVE_DATE", "2026-11-01")
        return _build(
            tmp_path_factory.mktemp("no-app-ads"), ga4=True, push_on=True, states=()
        )


def _texts(out: Path) -> dict[str, str]:
    """Every text file the build wrote (pages, feeds, sitemaps, llms.txt,
    snapshots), by path, with its whitespace runs flattened so a phrase
    broken across template lines is still found."""
    texts: dict[str, str] = {}
    for f in sorted(out.rglob("*")):
        if not f.is_file():
            continue
        try:
            raw = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # an image or another binary file
        texts[str(f.relative_to(out))] = " ".join(raw.split())
    return texts


def _promises(out: Path) -> list[tuple[str, str]]:
    return [
        (name, phrase)
        for name, text in _texts(out).items()
        for phrase in PROMISES
        if phrase in text
    ]


class _Text(HTMLParser):
    """Visible text, script and style skipped."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.text.append(data)


def _visible(html: str) -> str:
    p = _Text()
    p.feed(html)
    return " ".join("".join(p.text).split())


def _page(out: Path, rel: str) -> str:
    return (out / rel / "index.html").read_text(encoding="utf-8")


# ---- no file promises the app, with the switch off and on


@pytest.mark.parametrize("state", ["off", "on"])
def test_no_generated_file_promises_an_app(state: str, request: pytest.FixtureRequest):
    out: Path = request.getfixturevalue(state)
    texts = _texts(out)
    # the pages the sentence used to be on were built, so the check is not empty
    water = [n for n in texts if n.startswith("water/") and n.endswith("index.html")]
    tn = [n for n in texts if n.startswith("tn/water/") and n.endswith("index.html")]
    county = [n for n in texts if n.startswith("county/") and n.count("/") == 2]
    assert water and tn and county
    assert {"index.html", "about/index.html", "support/index.html"} <= set(texts)
    assert _promises(out) == []


def test_the_calendar_box_stays_and_no_longer_links_the_app_section(off: Path):
    for name, text in _texts(off).items():
        if "/water/" not in f"/{name}" or not name.endswith("index.html"):
            continue
        if "calendar-subscribe" not in text:
            continue
        assert "Apple Calendar" in text and "Google Calendar" in text, name
        assert "about/#app" not in text, name
        assert "iOS app" not in text, name


def test_home_and_county_pages_no_longer_name_the_app(off: Path):
    for name, text in _texts(off).items():
        if name == "index.html" or (
            name.startswith("county/") and name.count("/") == 2
        ):
            assert "iOS app" not in text, name
            assert "about/#app" not in text, name


def test_about_answers_is_there_an_app_in_the_approved_words(off: Path):
    html = _page(off, "about")
    assert '<h2 id="app">Is there an app?</h2>' in html
    assert ABOUT_APP in _visible(html)
    assert "The iOS app" not in _visible(html)


def test_support_asks_one_alert_question_and_no_purchase_question(off: Path):
    html = _page(off, "support")
    text = _visible(html)
    assert f"{SUPPORT_Q} {SUPPORT_A}" in text
    assert "restor" not in text.lower()
    assert 'id="restore"' not in html
    assert site._support_faq("x")[-1] == (SUPPORT_Q, SUPPORT_A)


def test_the_live_switch_still_shows_the_app_words(on: Path):
    """The switch stays: turned on, the about and support pages keep the
    installed-app wording, and the launch check still agrees."""
    assert '<h2 id="app">The iOS app</h2>' in _page(on, "about")
    assert "Why didn't the app alert me?" in _visible(_page(on, "support"))
    assert launch_check.surface_problems(on, live=True) == []


def test_the_launch_check_no_longer_wants_the_not_yet_sentence(off: Path):
    assert all("not in the App Store yet" not in t for t in _texts(off).values())
    assert launch_check.surface_problems(off, live=False) == []


# ---- negative controls


def _copy(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst


def test_negative_control_the_old_water_line_is_caught(off: Path, tmp_path: Path):
    out = _copy(off, tmp_path / "site")
    [page] = sorted(out.glob("water/*/index.html"))[:1]
    html = page.read_text(encoding="utf-8")
    doctored = html.replace("</p>\n</div>", f"{OLD_WATER_LINE}\n</p>\n</div>", 1)
    assert doctored != html  # the sabotage landed
    page.write_text(doctored, encoding="utf-8")
    assert _promises(out) == [(str(page.relative_to(out)), "on its way")]


def test_negative_control_the_old_about_line_is_caught_by_both_checks(
    off: Path, tmp_path: Path
):
    out = _copy(off, tmp_path / "site")
    about = out / "about" / "index.html"
    html = about.read_text(encoding="utf-8")
    doctored = html.replace('<h2 id="data">', f'{OLD_ABOUT_LINE}\n\n<h2 id="data">', 1)
    assert doctored != html
    about.write_text(doctored, encoding="utf-8")
    assert ("about/index.html", "not in the App Store yet") in _promises(out)
    assert any(
        "not in the App Store yet" in p
        for p in launch_check.surface_problems(out, live=False)
    )


def test_negative_control_a_phrase_broken_across_lines_is_still_caught(
    off: Path, tmp_path: Path
):
    out = _copy(off, tmp_path / "site")
    home = out / "index.html"
    html = home.read_text(encoding="utf-8")
    doctored = html.replace("</main>", "<p>An app is on its\n  way.</p>\n</main>", 1)
    assert doctored != html
    home.write_text(doctored, encoding="utf-8")
    assert ("index.html", "on its way") in _promises(out)


# ---- the leftovers: no file names an app while the switch is off

# Words only app copy would use. Case-insensitive and word bounded, read over
# raw files (so meta descriptions, ids and JSON-LD count) with scripts
# dropped and whitespace flattened (so a phrase broken across template lines
# counts). The owner's rule for every privacy sentence: never "no tracking".
MENTIONS = {
    "iPhone": r"\biphone\b",
    "iOS app": r"\bios app\b",
    "Android": r"\bandroid\b",
    "Google Play": r"\bgoogle play\b",
    "App Store": r"\bapp store\b",
    "the app": r"\bthe apps?\b",
    "its app": r"\bits apps?\b",
    "in-app": r"\bin-app\b",
    "no tracking": r"\bno tracking\b",
}
_MENTION = re.compile("|".join(f"(?:{p})" for p in MENTIONS.values()), re.I)
# The phone named only to say how a calendar or web push works on it.
ALLOWED = (
    "Apple Calendar (iPhone, iPad, Mac)",
    "on iPhone, in the Calendar app's settings",
    "an iPhone or iPad",
)
_SCRIPT = re.compile(r"<script\b.*?</script\s*>", re.I | re.S)

# The approved words (FOR-APPROVAL-app-leftovers.md, recommended column).
ABOUT_PRIVACY_H2 = '<h2 id="privacy">Privacy: the website counts visits</h2>'
ABOUT_DESCRIPTION = (
    "What Trout Truck is, what its website measures (Google Analytics), and "
    "where its trout planting and stocking data and license terms come from."
)
SUPPORT_DESCRIPTION = (
    "How the trout planting schedule and stocking calendar feeds work, and how "
    "to follow a water by calendar."
)
SUPPORT_PRIVACY_H2 = '<h2 id="privacy">What does this site know about me?</h2>'
SUPPORT_PRIVACY_GA = (
    "It uses Google Analytics to count visits, unless your browser sends "
    "Global Privacy Control or Do Not Track, or you press “Opt out of "
    "analytics” at the bottom of any page. It has no account. See the "
    "privacy policy."
)
SUPPORT_PRIVACY_BARE = "It has no account and no analytics. See the privacy policy."
PRIVACY_SCOPE = "Last updated 2026-11-21. Covers this website."
PRIVACY_LEDE_GA_END = "There is no account."
PRIVACY_LEDE_BARE = (
    "The Trout Truck website does not collect personal data. It has no "
    "account, no analytics, no advertising and no third-party script."
)
PRIVACY_CHILDREN_GA = (
    "The website's analytics are the same for every visitor, children "
    "included, and never ask for a name, age or contact details."
)
PRIVACY_DESCRIPTION = {
    "off": "What the Trout Truck trout planting site collects: nothing. No "
    "account and no analytics.",
    "prod": "What the Trout Truck trout planting site collects: it uses Google "
    "Analytics to count visits. No account, no ads.",
    "with_ads": "What the Trout Truck trout planting site collects: it uses "
    "Google Analytics and shows non-personalized Google ads. No account.",
}
ADS_NEVER = (
    "the about, privacy, support and data pages, the guides and any email "
    "from this site."
)
STATES_LINE = "Browsing and every water's history are free on this site."
TERMS_DATE = "Last updated 2026-11-21."


def _mentions(out: Path) -> list[tuple[str, str]]:
    """(file, matched words) for every app word in a file the build wrote.
    Scripts are code, not copy, so .js files and script elements are not read."""
    found = []
    for name, text in _texts(out).items():
        if name.endswith(".js"):
            continue
        text = _SCRIPT.sub(" ", html_lib.unescape(text))
        for phrase in ALLOWED:
            text = text.replace(phrase, " ")
        found += [(name, m.group(0)) for m in _MENTION.finditer(text)]
    return found


def _description(out: Path, rel: str) -> str:
    m = re.search(r'<meta name="description" content="([^"]*)">', _page(out, rel))
    assert m is not None, rel
    return html_lib.unescape(m.group(1))


@pytest.mark.parametrize("state", ["off", "prod", "with_ads"])
def test_no_generated_file_names_an_app(state: str, request: pytest.FixtureRequest):
    out: Path = request.getfixturevalue(state)
    texts = _texts(out)
    # the pages the app wording was on were built, so the check is not empty
    pages = {"about", "privacy", "support", "terms", "states"}
    assert {f"{p}/index.html" for p in pages} <= set(texts) or state == "with_ads"
    assert {"about/index.html", "privacy/index.html", "llms.txt"} <= set(texts)
    assert _mentions(out) == []


def test_the_production_build_reads_the_branches_it_should(prod: Path, with_ads: Path):
    privacy = _page(prod, "privacy")
    assert "googletagmanager" in privacy and 'id="push"' not in privacy
    assert "tn/index.html" in _texts(prod)
    assert 'id="ads"' in _page(with_ads, "privacy")
    assert 'id="push"' in _page(with_ads, "privacy")


@pytest.mark.parametrize("state", ["off", "prod", "with_ads"])
def test_descriptions_name_the_website_only(state: str, request: pytest.FixtureRequest):
    out: Path = request.getfixturevalue(state)
    assert _description(out, "privacy") == PRIVACY_DESCRIPTION[state]
    assert _description(out, "support") == SUPPORT_DESCRIPTION


def test_about_in_the_approved_words(prod: Path, off: Path):
    html = _page(prod, "about")
    assert ABOUT_PRIVACY_H2 in html
    assert _description(prod, "about") == ABOUT_DESCRIPTION
    assert "What Trout Truck is, what it collects (nothing), and" in _description(
        off, "about"
    )


def test_support_privacy_question_is_about_the_site(prod: Path, off: Path):
    assert SUPPORT_PRIVACY_H2 in _page(prod, "support")
    assert SUPPORT_PRIVACY_GA in _visible(_page(prod, "support"))
    assert SUPPORT_PRIVACY_H2 in _page(off, "support")
    assert SUPPORT_PRIVACY_BARE in _visible(_page(off, "support"))


@pytest.mark.parametrize("state", ["off", "prod", "with_ads"])
def test_privacy_covers_the_website_only_with_one_date(
    state: str, request: pytest.FixtureRequest
):
    out: Path = request.getfixturevalue(state)
    html = _page(out, "privacy")
    text = _visible(html)
    assert PRIVACY_SCOPE in text
    assert 'id="app"' not in html
    if state == "off":
        assert PRIVACY_LEDE_BARE in text
        assert "Nothing is collected from anyone, including children." in text
    else:
        lede = re.search(r'<p class="lede">(.*?)</p>', html, re.S)
        assert lede is not None
        assert _visible(lede.group(1)).endswith(PRIVACY_LEDE_GA_END)
        assert PRIVACY_CHILDREN_GA in text
    if state == "with_ads":
        assert ADS_NEVER in text


def test_states_hubs_and_terms_drop_their_app_lines(off: Path):
    assert STATES_LINE in _visible(_page(off, "states"))
    for hub in ("tn", "ma", "mi"):
        assert "one-time purchase" not in _visible(_page(off, hub)), hub
    terms = _page(off, "terms")
    assert TERMS_DATE in _visible(terms)
    assert 'id="apps"' not in terms
    assert "Agency names, Amazon, Apple and Google are" in _visible(terms)


def test_the_live_switch_still_shows_the_app_sections(on: Path):
    """Turned on, the privacy, terms, /states/ and hub pages keep their app
    wording, as the about and support pages do."""
    assert '<h2 id="app">The apps</h2>' in _page(on, "privacy")
    assert "apps for iPhone and Android." in _visible(_page(on, "privacy"))
    assert '<h2 id="apps">The apps</h2>' in _page(on, "terms")
    assert "In the iOS app" in _visible(_page(on, "states"))
    assert "In the iOS app" in _visible(_page(on, "tn"))
    assert "iOS app alerts" in _description(on, "support")
    assert "What does the app know about me?" in _visible(_page(on, "support"))


# ---- negative controls for the leftovers


def _sabotage(out: Path, rel: str, old: str, new: str) -> None:
    f = out / rel
    html = f.read_text(encoding="utf-8")
    doctored = html.replace(old, new, 1)
    assert doctored != html  # the sabotage landed
    f.write_text(doctored, encoding="utf-8")


def test_negative_control_the_old_about_app_sentence_is_caught(
    prod: Path, tmp_path: Path
):
    out = _copy(prod, tmp_path / "site")
    _sabotage(
        out,
        "about/index.html",
        "privacy policy</a>.",
        "privacy policy</a>. The iOS app has no analytics of any kind.",
    )
    assert _mentions(out) == [("about/index.html", "iOS app")]


def test_negative_control_the_old_support_description_is_caught(
    prod: Path, tmp_path: Path
):
    out = _copy(prod, tmp_path / "site")
    _sabotage(
        out,
        "support/index.html",
        f'content="{SUPPORT_DESCRIPTION}"',
        'content="How the trout planting schedule, stocking calendar feeds and '
        'iOS app alerts work, and why an alert may not arrive."',
    )
    assert ("support/index.html", "iOS app") in _mentions(out)


def test_negative_control_the_old_privacy_scope_and_a_broken_hub_line_are_caught(
    prod: Path, tmp_path: Path
):
    out = _copy(prod, tmp_path / "site")
    _sabotage(
        out,
        "privacy/index.html",
        "Covers this website.",
        "Covers this website and the Trout Truck apps for iPhone and\n  Android.",
    )
    _sabotage(
        out,
        "tn/index.html",
        "</main>",
        "<p>In the iOS\n  app, browsing is free.</p></main>",
    )
    found = _mentions(out)
    assert ("privacy/index.html", "iPhone") in found
    assert ("privacy/index.html", "Android") in found
    assert ("tn/index.html", "iOS app") in found


def test_negative_control_an_allowed_phrase_does_not_hide_a_new_one(
    prod: Path, tmp_path: Path
):
    out = _copy(prod, tmp_path / "site")
    _sabotage(out, "index.html", "</main>", "<p>No tracking in the app.</p></main>")
    assert sorted(m for _, m in _mentions(out)) == ["No tracking", "the app"]
