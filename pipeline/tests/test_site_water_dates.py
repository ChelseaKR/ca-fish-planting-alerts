"""Machine-readable dates on water pages (DECISIONS 0059).

Every California and state water page carries a WebPage ``dateModified``
and a ``<time datetime>`` on its "last checked"/"last read" line. Both are
the snapshot's last good read for that source: never the build time, never
a guess. A paused state keeps its old date. llms.txt names each state hub
in the build and its water URL pattern.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from cfpa import llms

from .test_site_llms import parse_llms
from .test_site_state_water_convert import FIXTURES, _pages, _run, _tn_from_failed_check
from .test_snapshot_v2 import _run as _run_with_states


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _run(tmp_path_factory.mktemp("water-dates"), FIXTURES / "states")


@pytest.fixture(scope="module")
def multi_state_site(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("water-dates-llms")
    _run_with_states(root, states=("TN", "MA", "MI", "NY"))
    v2 = json.loads((root / "site" / "snapshot" / "v2.json").read_text("utf-8"))
    return root / "site", v2


LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
TIME = re.compile(r'<time datetime="([^"]+)">([^<]+)</time>')


def _date_modified(html: str) -> str | None:
    graph = json.loads(LD.search(html).group(1))["@graph"]
    pages = [n for n in graph if n.get("@type") == "WebPage"]
    assert len(pages) == 1
    return pages[0].get("dateModified")


def _ca_pages(out: Path) -> list[str]:
    return [
        (d / "index.html").read_text(encoding="utf-8")
        for d in sorted((out / "water").iterdir())
    ]


def test_california_water_pages_carry_cdfws_last_good_read(built: Path):
    v1 = json.loads((built / "snapshot" / "v1.json").read_text("utf-8"))
    fetched = v1["source"]["fetched_at"]
    pages = _ca_pages(built)
    assert pages
    for html in pages:
        assert _date_modified(html) == fetched
        times = TIME.findall(html)
        assert (fetched, "2026-09-13 12:00 UTC") in times


def test_state_water_pages_carry_each_states_last_good_read(built: Path):
    v2 = json.loads((built / "snapshot" / "v2.json").read_text("utf-8"))
    last = {s["code"]: s["checks"]["last_success_at"] for s in v2["states"]}
    for code in ("TN", "MA", "MI", "NY"):
        pages = _pages(built, code.lower())
        assert pages
        for html in pages:
            assert _date_modified(html) == last[code], code
            assert any(dt_ == last[code] for dt_, _ in TIME.findall(html)), code


def test_negative_control_a_paused_states_date_is_its_last_good_read(tmp_path: Path):
    """Built 2026-10-23 from a history whose last good read is 2026-10-15:
    the page says paused and its dates are 2026-10-15, not the build day
    and not today. The doctored page (build time swapped in) is caught."""
    out = _tn_from_failed_check(
        tmp_path, dt.datetime(2026, 10, 23, 14, 0, tzinfo=dt.UTC)
    )
    today = dt.date.today().isoformat()
    pages = _pages(out, "tn")
    assert pages
    for html in pages:
        assert "Updates paused since 2026-10-15" in html
        modified = _date_modified(html)
        assert modified and modified.startswith("2026-10-15")
        assert not modified.startswith(today)
        assert not modified.startswith("2026-10-23")
        stamps = [d for d, _ in TIME.findall(html)]
        assert stamps and all(d.startswith("2026-10-15") for d in stamps)
    doctored = pages[0].replace(modified, "2026-10-23T14:00:00Z")
    assert doctored != pages[0]  # the doctoring landed
    assert not _date_modified(doctored).startswith("2026-10-15")


def test_no_date_means_no_key_rather_than_a_guess():
    from cfpa import site

    node = site._ld_page(
        "WebPage", page_url="u", name="n", base_url="b", about={}, date_modified=""
    )
    assert "dateModified" not in node


def test_llms_lists_each_state_hub_and_its_water_pattern(multi_state_site):
    out, v2 = multi_state_site
    doc = parse_llms((out / "llms.txt").read_text(encoding="utf-8"))
    hubs = doc["sections"]["State pages"]
    codes = [s["code"] for s in v2["states"] if s["code"] != "CA"]
    assert [u.rsplit("/", 2)[-2] for _, u in hubs] == [c.lower() for c in codes]
    for _, url in hubs:
        seg = url.rstrip("/").rsplit("/", 1)[-1]
        assert (out / seg / "index.html").is_file()
        assert (out / seg / "water").is_dir()


def test_llms_names_no_state_the_build_does_not_have():
    def state(code: str) -> dict:
        return {
            "code": code,
            "name": code,
            "agency": {"name": f"{code} agency"},
            "source_url": "https://e.com/",
            "semantics": "schedule",
            "terms_url": "https://e.com/terms",
            "files": [],
        }

    text = llms.render(
        site_name="Trout Truck",
        base_url="https://e.invalid",
        attribution_text="Data: X.",
        states=[state("CA"), state("TN")],
        region_feeds=[],
        week_label="week",
    )
    assert "https://e.invalid/tn/" in text and "/tn/water/<name>/" in text
    assert "https://e.invalid/ma/" not in text
    only_ca = llms.render(
        site_name="Trout Truck",
        base_url="https://e.invalid",
        attribution_text="Data: X.",
        states=[state("CA")],
        region_feeds=[],
        week_label="week",
    )
    assert "## State pages" not in only_ca
