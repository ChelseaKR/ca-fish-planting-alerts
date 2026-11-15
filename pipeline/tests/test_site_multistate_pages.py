"""Pages that California and the other states share, on a multistate build.

- No page skips a heading level. A Tennessee water page's calendar box
  follows the h1 directly, so its heading is an h2 there; a California water
  page's box sits under the status h2 and keeps its h3. axe's WCAG tags do
  not include heading-order, so tools/site-checks does not catch a skip.
- The 404 page, which GitHub Pages serves at any missing address, names the
  other states' address shape and links their hubs. A California-only build
  keeps its California wording.
- The about page says that only California's dates are always a week.
"""

from __future__ import annotations

import datetime as dt
import itertools
import re
from pathlib import Path

import pytest

from cfpa import cli

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
_HEADING = re.compile(r"<h([1-6])\b")
_TAGS = re.compile(r"<[^>]+>")


def _build(root: Path, states: tuple[str, ...]) -> Path:
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
        states_fixtures=FIXTURES / "states",
    )
    return root / "site"


@pytest.fixture(scope="module")
def multi(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("multi"), ("TN", "MA", "MI", "NY"))


@pytest.fixture(scope="module")
def ca_only(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("ca-only"), ())


def _visible(html: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub(" ", html))


def _skips(html: str) -> list[str]:
    levels = [int(n) for n in _HEADING.findall(html)]
    return [f"h{a} -> h{b}" for a, b in itertools.pairwise(levels) if b > a + 1]


def test_no_page_skips_a_heading_level(multi: Path):
    pages = sorted(multi.rglob("*.html"))
    assert any(p.parts[-4] == "tn" for p in pages if len(p.parts) >= 4)
    bad = {
        str(p.relative_to(multi)): s
        for p in pages
        if (s := _skips(p.read_text(encoding="utf-8")))
    }
    assert not bad, (
        f"{len(bad)} page(s) skip a heading level, e.g. {next(iter(bad.items()))}"
    )


def test_the_calendar_heading_is_h2_on_a_state_page_and_h3_in_california(multi: Path):
    tn = next((multi / "tn" / "water").glob("*/index.html")).read_text("utf-8")
    assert re.search(r'<h2 id="calendar-heading">Get .*?</h2>', tn)
    ca = next(
        p.read_text("utf-8")
        for p in sorted((multi / "water").glob("*/index.html"))
        if 'id="calendar-heading"' in p.read_text("utf-8")
    )
    assert re.search(r'<h3 id="calendar-heading">Get .*?</h3>', ca)
    # The control: the old fixed h3 is the skip this file guards against.
    assert _skips(
        tn.replace('<h2 id="calendar-heading"', '<h3 id="calendar-heading"', 1)
    )


def test_404_names_every_other_states_hub(multi: Path):
    html = (multi / "404.html").read_text(encoding="utf-8")
    text = _visible(html)
    assert "<code>&lt;state&gt;/water/&lt;name&gt;/</code>" in html
    assert "California: this week's planting schedule" in text
    for seg, name in (
        ("tn", "Tennessee"),
        ("ma", "Massachusetts"),
        ("mi", "Michigan"),
        ("ny", "New York"),
    ):
        # Root-relative, as every link on a page served at any depth.
        assert f'href="/ca-fish-planting-alerts/{seg}/"' in html
        assert f"{name} trout stocking schedule" in text
        assert (multi / seg / "index.html").is_file()
    assert "a water that CDFW has never scheduled" not in text


def test_404_in_a_california_only_build_is_as_before(ca_only: Path):
    text = _visible((ca_only / "404.html").read_text(encoding="utf-8"))
    assert "a water that CDFW has never scheduled has no page here" in text
    assert "&lt;state&gt;" not in text and "Also on" not in text


def test_about_says_only_californias_dates_are_always_a_week(
    multi: Path, ca_only: Path
):
    text = _visible((multi / "about" / "index.html").read_text(encoding="utf-8"))
    assert "Every California date on this site is a week" in text
    assert "Other states' dates are shown at each agency's own precision" in text
    assert 'href="../tn/"' in (multi / "about" / "index.html").read_text("utf-8")
    before = _visible((ca_only / "about" / "index.html").read_text(encoding="utf-8"))
    assert "Every date on this site is a week" in before
    assert "Other states' dates" not in before
