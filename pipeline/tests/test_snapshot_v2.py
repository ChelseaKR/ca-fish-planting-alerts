"""snapshot/v2.json and the state pages (DECISIONS 0025).

The promise to installed 1.0 builds is that v1 does not change: these tests
build the same run with and without the other states and compare v1 byte
for byte, and compare every California page of a California-only build."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import jsonschema
import pytest

from cfpa import cli, legacy, site, snapshot_v2
from cfpa.states import SOURCES
from cfpa.states import run as srun

FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "states"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO = Path(__file__).resolve().parents[2]
V1_SCHEMA = REPO / "schema" / "snapshot.v1.json"
V2_SCHEMA = REPO / "schema" / "snapshot.v2.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
NOW = dt.datetime(2026, 10, 12, 19, 18, 13, tzinfo=dt.UTC)


def _run(root: Path, *, states: tuple[str, ...] | None, **extra) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    return cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=V1_SCHEMA,
        site_out=root / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=None if states is None else root / "states",
        states_fetch=states or (),
        states_fixtures=STATE_FIXTURES if states else None,
        **extra,
    )


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("v2")
    _run(root, states=("TN", "MA", "MI"))
    return root


def _v2(root: Path) -> dict:
    return json.loads((root / "site" / "snapshot" / "v2.json").read_text("utf-8"))


def _tree(site: Path) -> dict[str, str]:
    return {
        p.relative_to(site).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(site.rglob("*"))
        if p.is_file()
    }


# ---- v1 compatibility


def test_v1_is_byte_for_byte_the_same_with_or_without_the_states(tmp_path: Path):
    _run(tmp_path / "plain", states=None)
    _run(tmp_path / "states", states=("TN", "MA", "MI"))
    plain = json.loads((tmp_path / "plain/site/snapshot/v1.json").read_text())
    with_states = json.loads((tmp_path / "states/site/snapshot/v1.json").read_text())
    # generated_at is the wall clock of each run; everything else is equal.
    plain.pop("generated_at")
    with_states.pop("generated_at")
    assert plain == with_states
    a = (tmp_path / "plain/site/snapshot/v1.json").read_text()
    b = (tmp_path / "states/site/snapshot/v1.json").read_text()
    strip = re.compile(r'"generated_at": "[^"]+"')
    assert strip.sub("", a) == strip.sub("", b)
    jsonschema.validate(json.loads(b), json.loads(V1_SCHEMA.read_text()))


def test_a_california_only_v2_leaves_every_california_page_unchanged(tmp_path: Path):
    """The same snapshot rendered with no v2 and with a v2 that has
    California alone writes the same files, byte for byte."""
    v1 = _run(tmp_path / "run", states=None)
    ca_only = snapshot_v2.build_snapshot_v2(v1, [], generated_at=NOW)
    site.build_site(v1, tmp_path / "without", base_url=BASE)
    site.build_site(v1, tmp_path / "with", base_url=BASE, snapshot_v2=ca_only)
    a, b = _tree(tmp_path / "without"), _tree(tmp_path / "with")
    assert a == b
    assert "states/index.html" not in a
    assert "Other states" not in (tmp_path / "with" / "index.html").read_text()


def test_the_california_pages_link_the_states_only_when_there_are_some(built: Path):
    home = (built / "site" / "index.html").read_text()
    assert 'href="./states/">Other states</a>' in home
    # Every California URL is where it was.
    assert (built / "site" / "water").is_dir()
    assert (built / "site" / "county").is_dir()


# ---- v2 itself


def test_v2_validates_and_carries_california_with_v1s_ids(built: Path):
    v2 = _v2(built)
    jsonschema.validate(v2, json.loads(V2_SCHEMA.read_text()))
    snapshot_v2.check_invariants(v2)
    v1 = json.loads((built / "site/snapshot/v1.json").read_text())
    ca_ids = [w["id"] for w in v2["waters"] if w["state"] == "CA"]
    assert ca_ids == [w["id"] for w in v1["waters"]]
    ca = v2["states"][0]
    assert ca["code"] == "CA"
    assert ca["current_week"] == v1["source_week"]
    assert ca["attribution"] == v1["attribution"]
    for w1, w2 in zip(
        v1["waters"], (w for w in v2["waters"] if w["state"] == "CA"), strict=True
    ):
        assert w2["site_path"] == f"/water/{w1['slug']}/"
        assert [p["period"]["label"] for p in w2["plants"]] == [
            p["week"]["label"] for p in w1["plants"]
        ]
        assert (w2["last_period"] or {}).get("label") == (
            w1["last_listed_week"] or {}
        ).get("label")
    assert [e for e in v2["this_week"] if e["water_id"].startswith("cdfw-")] == v1[
        "this_week"
    ]


def test_v2_states_say_what_their_records_mean(built: Path):
    states = {s["code"]: s for s in _v2(built)["states"]}
    assert list(states) == ["CA", "MA", "MI", "TN"]
    assert states["TN"]["semantics"] == "schedule"
    assert states["TN"]["removal_inference"] is True
    assert states["MA"]["semantics"] == states["MI"]["semantics"] == "report"
    assert states["MI"]["recency_note"]
    assert "indemnify" in states["MI"]["license"]["sources"][0]["terms_quote"]
    assert (
        "identify the state agency"
        in states["TN"]["license"]["sources"][0]["terms_quote"]
    )
    assert states["TN"]["attribution"]["text"].startswith(
        "Data: Tennessee Wildlife Resources Agency (TWRA)"
    )


def test_michigan_publishes_only_from_its_publish_date(built: Path):
    mi = [w for w in _v2(built)["waters"] if w["state"] == "MI"]
    starts = [p["period"]["start"] for w in mi for p in w["plants"]]
    assert starts and min(starts) >= "2021-01-01"
    assert "mi-3456" not in {w["id"] for w in mi}  # only a 2020 record


def test_month_precision_is_never_this_week(built: Path):
    v2 = _v2(built)
    month_waters = {
        w["id"]
        for w in v2["waters"]
        for p in w["plants"]
        if p["period"]["precision"] == "month"
        and all(q["period"]["precision"] == "month" for q in w["plants"])
    }
    assert not month_waters & {e["water_id"] for e in v2["this_week"]}


def test_month_only_tennessee_waters_are_listed_with_their_letters(built: Path):
    tn = [w for w in _v2(built)["waters"] if w["state"] == "TN"]
    assert len(tn) == 136
    letters_only = [w for w in tn if not w["plants"]]
    assert letters_only
    assert all(w["months_note"] for w in letters_only)


def test_invariants_catch_a_removal_in_a_report_state(built: Path):
    v2 = copy.deepcopy(_v2(built))
    mi = next(w for w in v2["waters"] if w["state"] == "MI")
    mi["plants"][0]["status"] = "removed"
    assert mi["plants"][0]["status"] == "removed"
    with pytest.raises(snapshot_v2.SnapshotV2Error, match="report state"):
        snapshot_v2.check_invariants(v2)


def test_invariants_catch_a_week_that_does_not_start_on_sunday(built: Path):
    v2 = copy.deepcopy(_v2(built))
    tn = next(
        w
        for w in v2["waters"]
        if w["state"] == "TN"
        and any(p["period"]["precision"] == "week" for p in w["plants"])
    )
    p = next(p for p in tn["plants"] if p["period"]["precision"] == "week")
    p["period"]["start"] = "2026-10-13"
    p["period"]["end"] = "2026-10-19"
    p["period"]["label"] = "week of 2026-10-13"
    with pytest.raises(snapshot_v2.SnapshotV2Error):
        snapshot_v2.check_invariants(v2)


def test_schema_refuses_a_day_label_on_a_week(built: Path):
    v2 = copy.deepcopy(_v2(built))
    tn = next(w for w in v2["waters"] if w["state"] == "TN" and w["plants"])
    tn["plants"][0]["period"]["precision"] = "week"
    tn["plants"][0]["period"]["label"] = "2026-10-11"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(v2, json.loads(V2_SCHEMA.read_text()))


def test_a_state_with_no_data_is_left_out_not_shown_empty(tmp_path: Path):
    v1 = _run(tmp_path, states=None)
    v2 = snapshot_v2.build_snapshot_v2(
        v1,
        [
            (
                s,
                srun.StateRun(
                    s, srun.StateHistory.empty(c), tmp_path, "skipped", ""
                ).history,
            )
            for c, s in SOURCES.items()
        ],
        generated_at=NOW,
    )
    assert [s["code"] for s in v2["states"]] == ["CA"]


# ---- the state pages


def _page(built: Path, rel: str) -> str:
    return (built / "site" / rel).read_text(encoding="utf-8")


def test_each_state_has_a_hub_water_pages_and_the_states_index(built: Path):
    site = built / "site"
    assert (site / "states" / "index.html").is_file()
    for code in ("tn", "ma", "mi"):
        assert (site / code / "index.html").is_file()
        assert any((site / code / "water").iterdir())
    for w in _v2(built)["waters"]:
        assert (site / w["site_path"].strip("/") / "index.html").is_file()


def test_state_pages_carry_their_agencys_attribution_and_disclaimer(built: Path):
    v2 = _v2(built)
    for state in v2["states"][1:]:
        code = state["code"].lower()
        hub = _page(built, f"{code}/index.html")
        assert state["attribution"]["text"] in hub
        water = next(w for w in v2["waters"] if w["state"] == state["code"])
        page = _page(built, water["site_path"].strip("/") + "/index.html")
        assert state["attribution"]["text"] in page
        assert "not affiliated with or endorsed by CDFW" not in page
        assert "endorsed by" in page


def test_a_week_is_never_shown_as_a_day_on_tennessee_pages(built: Path):
    page = _page(built, "tn/water/tellico-river-monroe-county/index.html")
    assert "week of 2026-10-11" in page
    assert "<td>2026-10-11</td>" not in page
    december = _page(built, "tn/water/mckenzie-city-park-caroll-county/index.html")
    assert "December 2026 (day not set yet)" in december


def test_report_states_say_stocked_and_michigan_says_how_late_it_is(built: Path):
    mi = _page(built, "mi/index.html")
    assert "stocking report" in mi
    assert "weeks after the stocking" in mi
    ma_page = _page(built, "ma/water/swift-river-belchertown/index.html")
    assert "<td>Stocked</td>" in ma_page
    tn = _page(built, "tn/water/tellico-river-monroe-county/index.html")
    assert "<td>Stocked</td>" not in tn
    assert "<td>Scheduled</td>" in tn


def test_state_titles_put_stocking_first_and_structured_data_parses(built: Path):
    page = _page(built, "tn/water/tellico-river-monroe-county/index.html")
    title = re.search(r"<title>(.*?)</title>", page).group(1)
    # "(Monroe County, Tennessee)" would make the part before the brand 63
    # characters, over the 60 a results page shows, so the title uses "TN";
    # the h1 keeps the state's name.
    assert title == (
        "Tellico River trout stocking schedule (Monroe County, TN) | Trout Truck"
    )
    assert (
        "<h1>Tellico River trout stocking schedule (Monroe County, Tennessee)</h1>"
        in page
    )
    ld = json.loads(
        re.search(
            r'<script type="application/ld\+json">(.*?)</script>', page, re.S
        ).group(1)
    )
    types = {n["@type"] for n in ld["@graph"]}
    assert {"WebPage", "BreadcrumbList", "BodyOfWater"} <= types
    assert "Event" not in json.dumps(ld)


def test_the_sitemap_lists_every_state_page(built: Path):
    sitemap = _page(built, "sitemap.xml")
    assert f"<loc>{BASE}/states/</loc>" in sitemap
    for w in _v2(built)["waters"]:
        assert f"<loc>{BASE}{w['site_path']}</loc>" in sitemap


def test_the_legacy_site_keeps_v2_byte_for_byte(tmp_path: Path):
    root = tmp_path / "dom"
    root.mkdir()
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=V1_SCHEMA,
        site_out=root / "site",
        base_url="https://trouttruck.example",
        legacy_site_out=root / "legacy",
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=("TN",),
        states_fixtures=STATE_FIXTURES,
    )
    rel = Path("snapshot") / "v2.json"
    assert (root / "legacy" / rel).read_bytes() == (root / "site" / rel).read_bytes()
    assert rel == legacy.SNAPSHOT_V2_PATH


def test_an_offline_cli_run_never_fetches_a_state(tmp_path: Path, monkeypatch):
    seen: dict = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return {}

    monkeypatch.setattr(cli, "run", fake_run)
    assert cli.main(["--fixture", str(FRESH), "--states-dir", str(tmp_path)]) == 0
    assert seen["states_fetch"] == ()
    assert cli.main(["--fixture", str(FRESH), "--no-states"]) == 0
    assert seen["states_dir"] is None
    assert cli.main(["--states", "tn, mi"]) == 0
    assert seen["states_fetch"] == ("TN", "MI")


def test_no_sentence_on_a_state_page_runs_into_the_next(built: Path):
    """Jinja's trim_blocks eats the newline after a block tag, which once
    printed "week of 2026-10-25.Most recently" on every Tennessee page."""
    joined = re.compile(r"[a-z0-9)]\.[A-Z][a-z]")
    pages = [
        p
        for code in ("tn", "ma", "mi", "states")
        for p in (built / "site" / code).rglob("index.html")
    ]
    assert len(pages) > 100
    for p in pages:
        body = re.sub(r"<script.*?</script>", " ", p.read_text("utf-8"), flags=re.S)
        text = re.sub(r"<[^>]+>", " ", body)
        assert not joined.search(text), (p, joined.search(text))


def test_california_locations_go_into_v2_and_never_into_v1(built: Path):
    from cfpa import locations as locations_mod

    placed = locations_mod.load_locations(cli.DEFAULT_LOCATIONS_PATH)
    v1 = json.loads((built / "site/snapshot/v1.json").read_text())
    v2 = _v2(built)
    assert all(w["location"] is None for w in v1["waters"])
    by_id = {w["id"]: w for w in v2["waters"]}
    hits = [w for w in v1["waters"] if w["cdfw_stock_id"] in placed]
    assert hits, "the fixture needs at least one water the geocoder placed"
    for w in hits:
        assert by_id[w["id"]]["location"] == placed[w["cdfw_stock_id"]]
    misses = [w for w in v1["waters"] if w["cdfw_stock_id"] not in placed]
    assert all(by_id[w["id"]]["location"] is None for w in misses)
    assert all(w["location"] is None for w in v2["waters"] if w["state"] != "CA")


def test_a_broken_locations_file_refuses_the_run(tmp_path: Path):
    bad = tmp_path / "locations.json"
    bad.write_text('{"schema": "something-else", "waters": []}', encoding="utf-8")
    assert '"something-else"' in bad.read_text()
    with pytest.raises(snapshot_v2.SnapshotV2Error, match="water locations"):
        _run(tmp_path / "run", states=None, locations_path=bad)


def test_every_state_water_title_follows_the_shared_length_rule(built: Path):
    """Every non-California water page: the water's name, species and
    "stocking" first; the state's name when it fits in the 60 characters a
    results page shows, else its postal code; the brand last. And each page
    carries its own agency's attribution, never CDFW's."""
    v2 = _v2(built)
    states = {s["code"]: s for s in v2["states"]}
    checked = {"name": 0, "code": 0}
    for w in v2["waters"]:
        if w["state"] == "CA":
            continue
        state = states[w["state"]]
        page = _page(built, w["site_path"].strip("/") + "/index.html")
        title = re.search(r"<title>(.*?)</title>", page).group(1)
        title = title.replace("&amp;", "&").replace("&#39;", "'")
        visible, brand = title.rsplit(" | ", 1)
        assert brand == "Trout Truck"
        assert visible.startswith(f"{w['name']} ") and " stocking " in visible
        if visible.endswith(f"{state['name']})"):
            assert len(visible) <= site.TITLE_VISIBLE_CHARS, title
            checked["name"] += 1
        else:
            assert visible.endswith(f", {state['code']})") or visible.endswith(
                f"({state['code']})"
            ), title
            longer = visible[: visible.rindex(state["code"])] + state["name"] + ")"
            assert len(longer) > site.TITLE_VISIBLE_CHARS, title
            checked["code"] += 1
        assert state["attribution"]["text"].replace("'", "&#39;") in page or (
            state["attribution"]["text"] in page
        ), w["site_path"]
        assert "not affiliated with or endorsed by CDFW" not in page
    assert checked["name"] and checked["code"]  # the fixtures exercise both
