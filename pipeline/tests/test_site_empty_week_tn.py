"""Tennessee water titles under the shared length rule, and the home page of
an empty week.

Built from the pinned fixtures only (never the daily-rewritten data files).
Pages are read with html.parser. Each negative control doctors its input,
asserts the doctoring landed, and then asserts the check caught it.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site, site_states

FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "states"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
STALE = FIXTURES / "schedule-stale-2025-cache.html"
SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
BANNED = {"only", "first", "best", "top", "unique", "stocked", "planted"}


class Page(HTMLParser):
    """Title, meta description, h1, visible text, and the rows of each
    ``<section aria-labelledby=ID>`` as (water slug, week text) pairs."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.h1 = ""
        self.text: list[str] = []
        self.section_ids: list[str] = []
        self.rows: dict[str, list[tuple[str, str]]] = {}
        self._skip: str | None = None
        self._tag_stack: list[str] = []
        self._section: str | None = None
        self._row: list[Any] | None = None
        self._cell = -1
        self.feed(html)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        self._tag_stack.append(tag)
        if tag in ("script", "style"):
            self._skip = tag
        if tag == "meta" and a.get("name") == "description":
            self.description = a.get("content") or ""
        if tag == "section" and a.get("aria-labelledby"):
            self._section = a["aria-labelledby"]
            self.section_ids.append(self._section)
            self.rows.setdefault(self._section, [])
        if tag == "tr" and self._section:
            self._row = ["", ""]
            self._cell = -1
        if tag == "td" and self._row is not None:
            self._cell += 1
        if tag == "a" and self._row is not None and self._cell == 0:
            href = a.get("href") or ""
            self._row[0] = href.rstrip("/").rsplit("/", 1)[-1]

    def handle_endtag(self, tag: str) -> None:
        if tag == self._skip:
            self._skip = None
        if tag == "tr" and self._row is not None and self._section and self._cell >= 0:
            self.rows[self._section].append((self._row[0], self._row[1].strip()))
            self._row = None
        if tag == "section":
            self._section = None
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        cur = self._tag_stack[-1] if self._tag_stack else ""
        if cur == "title":
            self.title += data
        if cur == "h1":
            self.h1 += data
        if self._row is not None and self._cell == 3:
            self._row[1] += data
        self.text.append(data)

    @property
    def visible(self) -> str:
        return " ".join("".join(self.text).split())


def _page(out: Path, rel: str) -> Page:
    return Page((out / rel / "index.html").read_text(encoding="utf-8"))


def _run(root: Path, *, states: bool = False, fixture: Path = FRESH) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    return cli.run(
        fixture_path=str(fixture),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA,
        site_out=root / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states" if states else None,
        states_fetch=("TN", "MA", "MI") if states else (),
        states_fixtures=STATE_FIXTURES if states else None,
    )


@pytest.fixture(scope="module")
def fresh(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    root = tmp_path_factory.mktemp("empty-week")
    snap = _run(root)
    return root / "site", snap


@pytest.fixture(scope="module")
def with_states(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("tn-titles")
    _run(root, states=True)
    return root / "site"


# ---- Tennessee titles

SN = site.SITE_NAME


def test_fit_title_takes_the_first_candidate_within_the_limit():
    short = "Pond trout stocking schedule (Perry County, Tennessee)"
    assert site_states.fit_title([short, "x"], SN, 100) == f"{short} | {SN}"
    assert site_states.fit_title([short, "Pond (TN)"], SN, 60) == f"Pond (TN) | {SN}"
    # Nothing fits: the shortest keeps the water's name; never dropped.
    assert site_states.fit_title(["a" * 80, "b" * 70], SN, 60) == f"{'b' * 70} | {SN}"


def test_tennessee_title_examples(with_states: Path):
    page = _page(with_states, "tn/water/tellico-river-monroe-county")
    assert page.title == (
        "Tellico River trout stocking schedule (Monroe County, TN) | Trout Truck"
    )
    # The h1 and the page keep the state's name.
    assert "(Monroe County, Tennessee)" in page.h1
    assert "Monroe County, Tennessee" in page.visible


def _tn_waters(root: Path) -> list[dict[str, Any]]:
    v2 = json.loads((root / "snapshot" / "v2.json").read_text("utf-8"))
    return [w for w in v2["waters"] if w["state"] == "TN"]


def test_every_tennessee_title_follows_the_shared_rule(with_states: Path):
    seen = {"name": 0, "code": 0}
    for w in _tn_waters(with_states):
        page = _page(with_states, w["site_path"].strip("/"))
        t = page.title
        assert t.endswith(f" | {SN}")
        assert t.startswith(f"{w['name']} ") and " stocking " in t
        if ", Tennessee) |" in t:
            assert len(t) <= site.WATER_TITLE_MAX, t
            seen["name"] += 1
        else:
            assert ", TN) |" in t, t
            longer = t.replace(", TN) |", ", Tennessee) |")
            assert len(longer) > site.WATER_TITLE_MAX, t
            seen["code"] += 1
        assert "Tennessee" in page.h1
    assert seen["code"], seen


def test_tennessee_title_rule_catches_a_tn_title_that_would_have_fit(with_states: Path):
    """Negative control on the check's own premise: a title whose full-name
    form fits must be allowed to keep the name, so a swap to TN there would
    be flagged. Build the candidate list for a short water name."""
    w = {"name": "Mill Pond", "counties": ["Polk"], "towns": []}
    state = {"name": "Tennessee", "code": "TN"}
    head = "Mill Pond trout stocking schedule"
    full = f"{head} ({site_states.place_phrase(w, state['name'])})"
    code = f"{head} ({site_states.short_place_phrase(w, state)})"
    assert full != code  # the sabotage (swapping the name for the code) landed
    assert len(f"{full} | {SN}") > site.WATER_TITLE_MAX  # too long: code is used
    shorter = {"name": "Ab", "counties": ["Polk"], "towns": []}
    head2 = "Ab stocking"
    full2 = f"{head2} ({site_states.place_phrase(shorter, 'Tennessee')})"
    assert len(f"{full2} | {SN}") <= 90
    assert (
        site_states.fit_title(
            [full2, f"{head2} ({site_states.short_place_phrase(shorter, state)})"],
            SN,
            90,
        )
        == f"{full2} | {SN}"
    )


def test_titles_and_descriptions_are_unique_site_wide(
    with_states: Path, fresh: tuple[Path, dict[str, Any]]
):
    for root in (with_states, fresh[0]):
        titles: dict[str, str] = {}
        descs: dict[str, str] = {}
        for f in sorted(root.rglob("index.html")):
            p = Page(f.read_text("utf-8"))
            rel = f.relative_to(root).as_posix()
            if p.title:
                assert p.title not in titles, (rel, titles.get(p.title))
                titles[p.title] = rel
            if p.description:
                assert p.description not in descs, (rel, descs.get(p.description))
                descs[p.description] = rel


# ---- the home page of an empty week


def _expected(
    snap: dict[str, Any],
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """(slug, week text) pairs: listed plants after the current week, and in
    the latest earlier week with any."""
    cur = snap["source_week"]["start"]
    later: set[tuple[str, str, str]] = set()
    earlier: set[tuple[str, str, str]] = set()
    for w in snap["waters"]:
        for p in w["plants"]:
            if p["status"] != "listed" or p["week"]["start"] == cur:
                continue
            rec = (w["slug"], p["week"]["label"], p["week"]["start"])
            (later if p["week"]["start"] > cur else earlier).add(rec)
    latest = max((s for _, _, s in earlier), default=None)
    return (
        {(s, lbl) for s, lbl, _ in later},
        {(s, lbl) for s, lbl, st in earlier if st == latest},
    )


def test_fixture_is_an_empty_week_with_a_next_and_a_recent_week(fresh):
    _, snap = fresh
    assert not snap["this_week"]
    later, earlier = _expected(snap)
    assert later and earlier


def test_empty_week_home_leads_with_next_and_recent_rows_from_the_data(fresh):
    out, snap = fresh
    page = _page(out, "")
    later, earlier = _expected(snap)
    label = snap["source_week"]["label"]
    assert set(page.rows["next-scheduled"]) == later
    assert set(page.rows["recently-scheduled"]) == earlier
    assert label not in {w for _, w in later | earlier}  # each row has its own week
    assert page.h1 == (
        f"California trout planting schedule: nothing listed for the {label}"
    )
    # They lead: the empty-week sections come before every browse list.
    assert page.section_ids[:2] == ["next-scheduled", "recently-scheduled"]
    assert "scheduled these waters" not in page.visible
    assert "not that there are no fish" in page.visible
    assert page.description == (
        f"CDFW's schedule lists no California fish plants for the {label}. "
        "The waters it scheduled next and most recently, with each water's "
        "trout stocking history."
    )
    assert "0 plants" not in page.visible and "no fish." not in page.description


def _banned_in(text: str) -> set[str]:
    return {w.strip(".,;:()\"'").lower() for w in text.split()} & BANNED


def test_empty_week_copy_has_no_banned_words_and_no_days(fresh):
    out, _ = fresh
    page = _page(out, "")
    # Negative control: the check flags a banned word once one is added.
    doctored = page.visible + " the best water, planted on Monday"
    assert doctored != page.visible
    assert _banned_in(doctored) == {"best", "planted"}
    assert not _banned_in(page.visible)
    for row in [r for rows in page.rows.values() for r in rows]:
        assert row[1].startswith("week of ")  # a week, never a day


def test_a_listed_week_home_has_no_empty_week_sections(tmp_path: Path):
    snap = _run(tmp_path / "w")
    doctored = copy.deepcopy(snap)
    wk = doctored["source_week"]
    donor = doctored["waters"][0]
    donor["plants"].append(
        {
            "species": "Rainbow Trout",
            "status": "listed",
            "week": wk,
            **{
                k: v
                for k, v in donor["plants"][0].items()
                if k not in ("species", "status", "week")
            },
        }
    )
    doctored["this_week"] = [{"water_id": donor["id"], "species": "Rainbow Trout"}]
    assert doctored["this_week"]  # the doctoring landed
    site.build_site(doctored, tmp_path / "s", base_url=BASE)
    page = _page(tmp_path / "s", "")
    assert "next-scheduled" not in page.section_ids
    assert "recently-scheduled" not in page.section_ids
    assert "scheduled these waters" in page.visible
    assert "Every California water" in page.description


def test_removed_weeks_are_neither_next_nor_recent(fresh, tmp_path: Path):
    _, snap = fresh
    marked = copy.deepcopy(snap)
    for w in marked["waters"]:
        for p in w["plants"]:
            p["status"] = "removed"
    assert not _expected(marked)[0] and not _expected(marked)[1]
    site.build_site(marked, tmp_path / "s", base_url=BASE)
    page = _page(tmp_path / "s", "")
    assert page.rows["next-scheduled"] == []
    assert "recently-scheduled" not in page.section_ids
    assert "lists no plants for a later week yet" in page.visible
    assert "not that there are no fish" in page.visible


def test_nothing_later_says_so_instead_of_showing_a_row(fresh, tmp_path: Path):
    _, snap = fresh
    cur = snap["source_week"]["start"]
    trimmed = copy.deepcopy(snap)
    for w in trimmed["waters"]:
        for p in w["plants"]:
            if p["week"]["start"] > cur:
                p["status"] = "removed"
    assert not _expected(trimmed)[0]  # the sabotage landed
    assert _expected(snap)[0]  # ...and the original had rows
    site.build_site(trimmed, tmp_path / "s", base_url=BASE)
    page = _page(tmp_path / "s", "")
    assert page.rows["next-scheduled"] == []
    assert "lists no plants for a later week yet" in page.visible


def test_a_stale_fetch_is_never_an_empty_week(tmp_path: Path):
    """The stale cached page is refused before any page is built, so the
    empty-week home can never describe a failed fetch."""
    with pytest.raises(Exception, match="refusing to use this page"):
        _run(tmp_path / "s", fixture=STALE)
    assert not (tmp_path / "s" / "site" / "index.html").exists()
