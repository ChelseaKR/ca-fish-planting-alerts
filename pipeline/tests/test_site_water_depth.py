"""Water-page depth: the record facts, the related-water links, and the links
to the other states' hubs from the home page and the county index.

Pages are read with html.parser, never with a pattern over markup."""

from __future__ import annotations

import copy
import datetime as dt
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "states"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
FORBIDDEN = {"stocked", "planted", "only", "first", "colour", "centre", "organise"}


class _Sections(HTMLParser):
    """Collects, per section id of interest, the text and the water links."""

    def __init__(self) -> None:
        super().__init__()
        self.depth_stack: list[str | None] = []
        self.sections: dict[str, dict[str, Any]] = {}
        self._open: list[str] = []
        self.all_hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "section":
            label = a.get("aria-labelledby") or ""
            cls = a.get("class") or ""
            key = label or cls
            self._open.append(key)
            self.sections.setdefault(key, {"text": [], "hrefs": []})
        if tag == "a" and a.get("href"):
            self.all_hrefs.append(a["href"] or "")
            for key in self._open:
                self.sections[key]["hrefs"].append(a["href"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "section" and self._open:
            self._open.pop()

    def handle_data(self, data: str) -> None:
        for key in self._open:
            self.sections[key]["text"].append(data)


def _parse(path: Path) -> _Sections:
    p = _Sections()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def _plants(weeks: list[str], status: str = "listed") -> list[dict[str, Any]]:
    return [
        {
            "week": {"start": d, "end": d, "label": f"week of {d}"},
            "species": "Trout",
            "status": status,
        }
        for d in weeks
    ]


def _w(weeks: list[str], removed: list[str] | None = None) -> dict[str, Any]:
    return {
        "region": "R1",
        "plants": _plants(weeks) + _plants(removed or [], "removed"),
    }


# ---- _water_record


def test_record_gaps_and_median_from_listed_weeks() -> None:
    r = site._water_record(_w(["2026-01-04", "2026-01-11", "2026-02-01"]))
    assert (r["first_week"], r["latest_week"]) == ("2026-01-04", "2026-02-01")
    assert (r["span_weeks"], r["gap_count"]) == (4, 2)
    assert (r["min_gap"], r["max_gap"], r["median_gap"]) == (
        "1 week",
        "3 weeks",
        "2 weeks",
    )


def test_record_even_gap_count_takes_the_midpoint() -> None:
    r = site._water_record(_w(["2026-01-04", "2026-01-11", "2026-01-25", "2026-02-15"]))
    assert r["median_gap"] == "2 weeks"  # gaps 1, 2, 3
    r = site._water_record(
        _w(["2026-01-04", "2026-01-11", "2026-01-25", "2026-02-15", "2026-03-22"])
    )
    assert r["median_gap"] == "2.5 weeks"  # gaps 1, 2, 3, 5


def test_removed_weeks_do_not_count_and_a_negative_control_proves_it() -> None:
    base = _w(["2026-01-04", "2026-01-11"])
    with_removed = _w(["2026-01-04", "2026-01-11"], removed=["2026-06-07"])
    assert site._water_record(with_removed) == site._water_record(base)
    # Control: if removed weeks were counted, the latest week would move.
    counted = _w(["2026-01-04", "2026-01-11", "2026-06-07"])
    assert site._water_record(counted)["latest_week"] == "2026-06-07"
    assert site._water_record(base)["latest_week"] == "2026-01-11"


def test_one_week_has_no_gap_and_no_weeks_has_nothing() -> None:
    one = site._water_record(_w(["2026-01-04"]))
    assert one["gap_count"] == 0 and one["median_gap"] == ""
    none = site._water_record(_w([]))
    assert none["count"] == 0 and none["first_week"] == ""


# ---- built pages


def _bigger(snap: dict[str, Any], per_region: int = 12) -> dict[str, Any]:
    """The fixture snapshot with copies of its waters so every region that has
    a water has at least ``per_region`` of them, as the real snapshot does."""
    out = copy.deepcopy(snap)
    by_region: dict[str, list[dict[str, Any]]] = {}
    for w in out["waters"]:
        by_region.setdefault(w["region"], []).append(w)
    n = 0
    for region, ws in by_region.items():
        i = 0
        while len(by_region[region]) < per_region:
            src = copy.deepcopy(ws[i % len(ws)])
            n += 1
            i += 1
            src["id"] = f"{src['id']}-copy{n}"
            src["slug"] = f"{src['slug']}-copy{n}"
            src["name"] = f"{src['name']} Copy {n}"
            by_region[region].append(src)
            out["waters"].append(src)
    return out


@pytest.fixture(scope="module")
def v1(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp = tmp_path_factory.mktemp("depth-src")
    cli.run(
        fixture_path=str(FRESH),
        history_path=tmp / "history.json",
        aliases_path=tmp / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=tmp / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    return json.loads((tmp / "site" / "snapshot" / "v1.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def big_site(tmp_path_factory: pytest.TempPathFactory, v1: dict[str, Any]) -> Path:
    out = tmp_path_factory.mktemp("depth-big") / "site"
    site.build_site(_bigger(v1), out, base_url=BASE)
    return out


def _slugs_in(sec: dict[str, Any] | None) -> list[str]:
    out = []
    for h in (sec or {"hrefs": []})["hrefs"]:
        parts = h.rstrip("/").split("/")
        if len(parts) >= 2 and parts[-2] == "water":
            out.append(parts[-1])
    return out


def _related_slugs(page: Path, own: str) -> list[str]:
    """Water slugs linked from the same-county and same-region sections, in
    page order."""
    p = _parse(page)
    slugs: list[str] = []
    for key, sec in p.sections.items():
        if key.startswith("others-") or key == "region-related-heading":
            for h in sec["hrefs"]:
                parts = h.rstrip("/").split("/")
                if len(parts) >= 2 and parts[-2] == "water" and parts[-1] != own:
                    slugs.append(parts[-1])
    return slugs


def test_every_water_page_links_at_least_five_related_waters(big_site: Path) -> None:
    pages = sorted((big_site / "water").glob("*/index.html"))
    assert len(pages) > 50
    for page in pages:
        slugs = _related_slugs(page, page.parent.name)
        assert len(set(slugs)) >= 5, page.parent.name
        # A water in two counties is listed under each (existing behavior);
        # the region list must never repeat a county link.
        p = _parse(page)
        region = _slugs_in(p.sections.get("region-related-heading"))
        county = {
            s
            for k, sec in p.sections.items()
            if k.startswith("others-")
            for s in _slugs_in(sec)
        }
        assert not set(region) & county, page.parent.name


def test_county_waters_come_before_region_waters(big_site: Path) -> None:
    page = big_site / "water" / "shaver-lake" / "index.html"
    p = _parse(page)
    keys = list(p.sections)
    county_keys = [k for k in keys if k.startswith("others-")]
    assert county_keys, keys
    assert keys.index("region-related-heading") > max(
        keys.index(k) for k in county_keys
    )


def test_without_the_region_links_a_thin_county_falls_below_five(
    big_site: Path,
    v1: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative control: with the region fill switched off the same check
    fails for some page, so the check above is able to fail."""
    monkeypatch.setattr(site, "RELATED_WATERS_TARGET", 0)
    assert site.RELATED_WATERS_TARGET == 0  # the sabotage applied
    out = tmp_path / "site"
    site.build_site(_bigger(v1), out, base_url=BASE)
    short = [
        d.name
        for d in (out / "water").iterdir()
        if len(set(_related_slugs(d / "index.html", d.name))) < 5
    ]
    assert short, "no page fell below five links; the control proves nothing"
    sections = _parse(out / "water" / short[0] / "index.html").sections
    assert "region-related-heading" not in sections


def test_record_section_matches_the_snapshot_for_every_water(
    big_site: Path, v1: dict[str, Any]
) -> None:
    checked = 0
    for w in v1["waters"]:
        listed = sorted(
            {p["week"]["start"] for p in w["plants"] if p["status"] == "listed"}
        )
        sec = _parse(big_site / "water" / w["slug"] / "index.html").sections.get(
            "water-record-heading"
        )
        if not listed:
            assert sec is None
            continue
        text = " ".join("".join(sec["text"]).split())
        assert f"The week of {listed[0]}." in text
        if len(listed) > 1:
            assert f"to the week of {listed[-1]}" in text
        else:
            assert "One listed week so far" in text
        checked += 1
    assert checked > 10


def test_record_and_related_copy_follows_the_owner_rules(big_site: Path) -> None:
    for page in sorted((big_site / "water").glob("*/index.html"))[:40]:
        p = _parse(page)
        for key in ("water-record-heading", "region-related-heading"):
            if key in p.sections:
                words = {
                    t.strip(".,:;()'\"").lower()
                    for t in " ".join(p.sections[key]["text"]).split()
                }
                assert not (words & FORBIDDEN), (page.name, key, words & FORBIDDEN)


def test_record_section_does_not_repeat_the_status_block(big_site: Path) -> None:
    p = _parse(big_site / "water" / "shaver-lake" / "index.html")
    status = " ".join(p.sections["water-status-heading"]["text"])
    record = " ".join(p.sections["water-record-heading"]["text"])
    for label in ("Last on the schedule", "Weeks on the schedule"):
        assert label in status and label not in record


# ---- links to the other states


def _states_site(tmp_path: Path, states: tuple[str, ...] | None) -> Path:
    cli.run(
        fixture_path=str(FRESH),
        history_path=tmp_path / "history.json",
        aliases_path=tmp_path / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=tmp_path / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=None if states is None else tmp_path / "states",
        states_fetch=states or (),
        states_fixtures=STATE_FIXTURES if states else None,
    )
    return tmp_path / "site"


def _body_links(page: Path, url: str) -> set[str]:
    return {urljoin(url, h) for h in _parse(page).all_hrefs}


def test_home_and_county_index_link_the_tennessee_hub(tmp_path: Path) -> None:
    out = _states_site(tmp_path, ("TN",))
    hub = f"{BASE}/tn/"
    assert (out / "tn" / "index.html").is_file()
    assert hub in _body_links(out / "index.html", f"{BASE}/")
    assert hub in _body_links(out / "county" / "index.html", f"{BASE}/county/")
    home = (out / "index.html").read_text(encoding="utf-8")
    assert "Tennessee trout stocking schedule</a>" in home


def test_a_california_only_build_has_no_state_link_in_the_body(tmp_path: Path) -> None:
    out = _states_site(tmp_path, None)
    assert not (out / "tn").exists()
    assert f"{BASE}/tn/" not in _body_links(out / "index.html", f"{BASE}/")
    assert f"{BASE}/tn/" not in _body_links(
        out / "county" / "index.html", f"{BASE}/county/"
    )
