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
"""

from __future__ import annotations

import datetime as dt
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

from cfpa import cli, launch_check, site

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


def _build(root: Path, *, app_store_live: bool = False) -> Path:
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
        states_fetch=("TN", "MA", "MI"),
        states_fixtures=STATE_FIXTURES,
        app_store_live=app_store_live,
    )
    return root / "site"


@pytest.fixture(scope="module")
def off(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("no-app-off"))


@pytest.fixture(scope="module")
def on(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("no-app-on"), app_store_live=True)


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
