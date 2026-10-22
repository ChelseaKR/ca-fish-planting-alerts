"""/data/ and the CSV and JSON files it lists.

Built from the pinned fixtures (the 2026-09-13 CDFW page and the Tennessee
fixture), never from the daily-rewritten data files. Pages are read with
html.parser, not regular expressions over tags or scripts.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, opendata, site

FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "states"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO = Path(__file__).resolve().parents[2]
V1_SCHEMA = REPO / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"


def _run(root: Path, *, states: tuple[str, ...]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=V1_SCHEMA,
        site_out=root / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states" if states else None,
        states_fetch=states,
        states_fixtures=STATE_FIXTURES if states else None,
    )


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("opendata")
    _run(root, states=("TN",))
    return root / "site"


@pytest.fixture(scope="module")
def ca_only(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("opendata-ca")
    _run(root, states=())
    return root / "site"


class _Page(HTMLParser):
    """Links, ld+json blocks, <dt> code names and the visible text."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.ld: list[str] = []
        self.dt_codes: list[str] = []
        self.text: list[str] = []
        self._in_ld = False
        self._in_dt = False
        self._in_code = False
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"] or "")
        if tag == "script":
            self._in_ld = a.get("type") == "application/ld+json"
            self._skip += 1
        if tag == "dt":
            self._in_dt = True
        if tag == "code":
            self._in_code = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_ld = False
            self._skip -= 1
        if tag == "dt":
            self._in_dt = False
        if tag == "code":
            self._in_code = False

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self.ld.append(data)
        elif self._skip == 0:
            self.text.append(data)
        if self._in_dt and self._in_code:
            self.dt_codes.append(data)


def _page(site_dir: Path, rel: str) -> _Page:
    p = _Page()
    p.feed((site_dir / rel / "index.html").read_text("utf-8"))
    return p


def _csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames is not None
        return list(reader.fieldnames), list(reader)


def _v2(site_dir: Path) -> dict[str, Any]:
    return json.loads((site_dir / "snapshot" / "v2.json").read_text("utf-8"))


# ---- files


def test_files_exist_for_every_state_and_kind(built: Path) -> None:
    for state in ("ca", "tn"):
        for kind in ("current", "history"):
            for ext in ("csv", "json"):
                assert (built / "data" / "v1" / f"{state}-{kind}.{ext}").is_file()


def test_csv_header_is_the_documented_columns_in_order(built: Path) -> None:
    for name in ("ca-current", "ca-history", "tn-current", "tn-history"):
        header, _ = _csv_rows(built / "data" / "v1" / f"{name}.csv")
        assert tuple(header) == opendata.COLUMN_NAMES


def test_history_row_count_is_every_plant_in_the_snapshot(built: Path) -> None:
    v2 = _v2(built)
    for code in ("CA", "TN"):
        expected = sum(len(w["plants"]) for w in v2["waters"] if w["state"] == code)
        assert expected > 0
        _, rows = _csv_rows(built / "data" / "v1" / f"{code.lower()}-history.csv")
        assert len(rows) == expected
        doc = json.loads(
            (built / "data" / "v1" / f"{code.lower()}-history.json").read_text("utf-8")
        )
        assert len(doc["records"]) == expected


def test_current_is_this_week_and_later_and_never_removed(built: Path) -> None:
    v2 = _v2(built)
    for state in v2["states"]:
        start = state["current_week"]["start"]
        _, rows = _csv_rows(
            built / "data" / "v1" / f"{state['code'].lower()}-current.csv"
        )
        assert rows
        for r in rows:
            assert r["status"] in ("listed", "reported")
            assert r["period_end"] >= start
        _, history = _csv_rows(
            built / "data" / "v1" / f"{state['code'].lower()}-history.csv"
        )
        excluded = [r for r in history if r not in rows]
        assert excluded, "fixture must have records the current file leaves out"
        for r in excluded:
            assert r["status"] == "removed" or r["period_end"] < start


def test_csv_and_json_carry_the_same_records(built: Path) -> None:
    for name in ("ca-current", "ca-history", "tn-current", "tn-history"):
        _, rows = _csv_rows(built / "data" / "v1" / f"{name}.csv")
        doc = json.loads((built / "data" / "v1" / f"{name}.json").read_text("utf-8"))
        assert len(rows) == len(doc["records"])
        for row, rec in zip(rows, doc["records"], strict=True):
            assert list(rec) == list(opendata.COLUMN_NAMES)
            assert row["water_id"] == rec["water_id"]
            assert row["counties"] == "; ".join(rec["counties"])
            assert row["count"] == ("" if rec["count"] is None else str(rec["count"]))


def test_california_is_week_precision_and_never_a_day(built: Path) -> None:
    _, rows = _csv_rows(built / "data" / "v1" / "ca-history.csv")
    assert {r["period_precision"] for r in rows} == {"week"}
    for r in rows:
        assert r["period_label"] == f"week of {r['period_start']}"
        assert dt.date.fromisoformat(r["period_start"]).weekday() == 6
        assert r["state"] == "CA"
        assert r["water_page"].startswith(f"{BASE}/water/")


def test_tennessee_is_in_its_own_files_only(built: Path) -> None:
    for kind in ("current", "history"):
        _, ca = _csv_rows(built / "data" / "v1" / f"ca-{kind}.csv")
        _, tn = _csv_rows(built / "data" / "v1" / f"tn-{kind}.csv")
        assert {r["state"] for r in ca} == {"CA"}
        assert {r["state"] for r in tn} == {"TN"}


def test_json_envelope_updated_comes_from_the_data(built: Path) -> None:
    v2 = _v2(built)
    for state in v2["states"]:
        doc = json.loads(
            (built / "data" / "v1" / f"{state['code'].lower()}-current.json").read_text(
                "utf-8"
            )
        )
        assert doc["schema_version"] == 1
        assert doc["updated"] == state["source"]["fetched_at"][:10]
        assert doc["source_fetched_at"] == state["source"]["fetched_at"]
        assert doc["attribution"] == state["attribution"]
        assert doc["terms_url"].startswith("https://")
    ca = json.loads((built / "data" / "v1" / "ca-current.json").read_text("utf-8"))
    assert ca["terms_url"] == "https://wildlife.ca.gov/Conditions-of-Use"
    assert ca["updated"] == "2026-09-13"


def test_rebuild_of_unchanged_data_is_byte_identical(
    built: Path, tmp_path: Path
) -> None:
    _run(tmp_path / "again", states=("TN",))
    again = tmp_path / "again" / "site"
    for rel in (
        "data/v1/ca-history.csv",
        "data/v1/ca-current.json",
        "data/v1/tn-history.json",
        "data/index.html",
    ):
        assert (built / rel).read_bytes() == (again / rel).read_bytes()


def test_a_california_only_build_has_no_tennessee_files(ca_only: Path) -> None:
    assert (ca_only / "data" / "v1" / "ca-history.csv").is_file()
    assert not (ca_only / "data" / "v1" / "tn-history.csv").exists()
    page = _page(ca_only, "data")
    assert not any("tn-" in h for h in page.hrefs)


# ---- page


def test_page_attributes_cdfw_and_points_at_its_terms(built: Path) -> None:
    page = _page(built, "data")
    text = " ".join("".join(page.text).split())
    assert "Source: CDFW; terms: see CDFW Conditions of Use." in text
    assert "https://wildlife.ca.gov/Conditions-of-Use" in page.hrefs
    assert "not affiliated with or endorsed by CDFW" in text
    assert "scheduled, not confirmed" in text


def test_page_states_no_license_until_the_owner_chooses_one(built: Path) -> None:
    text = " ".join("".join(_page(built, "data").text).split())
    assert "These files add no license of their own" in text
    ld = json.loads("".join(_page(built, "data").ld))
    assert all("license" not in n for n in ld["@graph"])


def test_a_chosen_license_reaches_the_page_and_the_markup(
    ca_only: Path, tmp_path: Path
) -> None:
    v1 = json.loads((ca_only / "snapshot" / "v1.json").read_text("utf-8"))
    v2 = _v2(ca_only)
    out = tmp_path / "licensed"
    site.build_site(
        v1,
        out,
        base_url=BASE,
        snapshot_v2=v2,
        dataset_license_url="https://example.invalid/license",
    )
    page = _page(out, "data")
    assert "https://example.invalid/license" in page.hrefs
    assert "add no license of their own" not in " ".join("".join(page.text).split())
    ld = json.loads("".join(page.ld))
    assert [n["license"] for n in ld["@graph"]] == ["https://example.invalid/license"]


def test_dictionary_lists_every_column_in_order(built: Path) -> None:
    page = _page(built, "data")
    assert tuple(page.dt_codes) == opendata.COLUMN_NAMES


def test_page_lists_every_file_as_a_working_link(built: Path) -> None:
    page = _page(built, "data")
    for state in ("ca", "tn"):
        for kind in ("current", "history"):
            for ext in ("csv", "json"):
                rel = f"../data/v1/{state}-{kind}.{ext}"
                assert rel in page.hrefs
                assert (built / "data" / "v1" / f"{state}-{kind}.{ext}").is_file()


def test_page_last_updated_matches_the_data(built: Path) -> None:
    text = " ".join("".join(_page(built, "data").text).split())
    assert "Last updated 2026-09-13" in text


def test_page_copy_avoids_the_banned_words(built: Path) -> None:
    text = " ".join("".join(_page(built, "data").text).split()).lower()
    for word in (" only ", "best", "unique", "stocked on", "planted on"):
        assert word not in text
    # No word "top" or "first" outside the documented column names.
    prose = text
    for name in opendata.COLUMN_NAMES:
        prose = prose.replace(name, "")
    assert " top " not in f" {prose} "
    assert " first " not in f" {prose} "


def test_footer_and_about_link_to_the_page(built: Path) -> None:
    for rel, href in (("", "./data/"), ("about", "../data/"), ("data", "../data/")):
        assert href in _page(built, rel).hrefs, rel
    assert "../data/" in _page(built, "county").hrefs


def test_sitemap_lists_the_page_with_the_data_date(built: Path) -> None:
    sitemap = (built / "sitemap.xml").read_text("utf-8")
    assert f"<url><loc>{BASE}/data/</loc><lastmod>2026-09-13</lastmod></url>" in sitemap


# ---- structured data


def test_dataset_markup_matches_the_visible_page(built: Path) -> None:
    page = _page(built, "data")
    ld = json.loads("".join(page.ld))
    nodes = ld["@graph"]
    assert [n["@type"] for n in nodes] == ["Dataset", "Dataset"]
    text = " ".join("".join(page.text).split())
    for node in nodes:
        assert 50 <= len(node["description"]) <= 5000
        assert node["creditText"] in text
        assert node["isBasedOn"]["license"].startswith("https://")
        assert node["isAccessibleForFree"] is True
        for dist in node["distribution"]:
            rel = dist["contentUrl"].removeprefix(BASE + "/")
            assert (built / rel).is_file()
            assert "../" + rel in page.hrefs
        for key in ("startDate", "endDate", "geo", "latitude", "longitude"):
            assert key not in node
    assert nodes[0]["@id"] == f"{BASE}/data/#ca"
    assert nodes[0]["dateModified"] == "2026-09-13"


def test_about_dataset_is_unchanged_and_still_distinct(built: Path) -> None:
    ld = json.loads("".join(_page(built, "about").ld))
    (node,) = ld["@graph"]
    assert node["@id"] == f"{BASE}/about/#data"
    assert [d["contentUrl"] for d in node["distribution"]] == [
        f"{BASE}/snapshot/v1.json"
    ]


# ---- negative controls


def test_control_current_filter_drops_a_record_marked_removed(built: Path) -> None:
    v2 = _v2(built)
    state = next(s for s in v2["states"] if s["code"] == "CA")
    before_current, _ = opendata.records_for_state(v2, state, base_url=BASE)
    victim = next(
        (w, p)
        for w in v2["waters"]
        if w["state"] == "CA"
        for p in w["plants"]
        if p["status"] == "listed"
        and p["period"]["end"] >= state["current_week"]["start"]
    )
    assert victim[1]["status"] == "listed"
    victim[1]["status"] = "removed"  # the sabotage
    assert victim[1]["status"] == "removed"
    after_current, _ = opendata.records_for_state(v2, state, base_url=BASE)
    assert len(after_current) == len(before_current) - 1


def test_control_a_renamed_column_fails_the_header_check(built: Path) -> None:
    text = (built / "data" / "v1" / "ca-history.csv").read_text("utf-8")
    sabotaged = text.replace("water_name", "name", 1)
    assert sabotaged != text
    header = next(csv.reader(io.StringIO(sabotaged)))
    assert tuple(header) != opendata.COLUMN_NAMES
