"""/llms.txt: the llmstxt.org grammar, links that resolve to files the build
wrote, stability across two builds of the same data, and a negative control
for each check. Parsed with a small grammar parser, not substring checks."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from cfpa import llms

from .test_site_feeds import BASE_URL, MIDWEEK, _build
from .test_snapshot_v2 import _run as _run_with_states

FETCHED = dt.datetime(2026, 9, 17, 23, 0, tzinfo=dt.UTC)
TODAY = dt.date(2026, 9, 17)


@pytest.fixture(scope="module")
def two_sites(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    a = _build(tmp_path_factory.mktemp("llms-a"), MIDWEEK, FETCHED, TODAY)
    b = _build(tmp_path_factory.mktemp("llms-b"), MIDWEEK, FETCHED, TODAY)
    return a, b


def parse_llms(text: str) -> dict:
    lines = text.split("\n")
    assert lines[0].startswith("# ") and not lines[0].startswith("## ")
    assert lines[2].startswith("> ")
    sections: dict[str, list[tuple[str, str]]] = {}
    current: str | None = None
    loose: list[str] = []
    for line in lines[3:]:
        if line.startswith("## "):
            current = line[3:]
            sections[current] = []
        elif line.startswith("# "):
            raise AssertionError("second H1")
        elif current is None:
            loose.append(line)
        elif line.strip():
            m = re.match(r"^- \[([^\]]+)\]\((https://[^)\s]+)\)(?:: .+)?$", line)
            if m:
                sections[current].append((m.group(1), m.group(2)))
            else:
                assert line.startswith("- "), (
                    line
                )  # a note line in a list, not stray text
    return {"title": lines[0][2:], "sections": sections, "loose": "\n".join(loose)}


def test_llms_txt_is_valid_and_every_local_link_is_a_written_file(two_sites):
    site, _ = two_sites
    text = (site / "llms.txt").read_text(encoding="utf-8")
    doc = parse_llms(text)
    assert doc["title"] == "Trout Truck"
    assert llms.SPEC_URL in doc["loose"]
    assert {"Pages", "Feeds (Atom 1.0)", "Sources and open data"} <= set(
        doc["sections"]
    )
    checked = 0
    for items in doc["sections"].values():
        for _name, url in items:
            if not url.startswith(BASE_URL + "/"):
                continue  # the agency's own page
            rel = url[len(BASE_URL) + 1 :]
            target = site / rel
            if target.is_dir() or rel == "" or rel.endswith("/"):
                target = site / rel / "index.html"
            assert target.is_file(), url
            checked += 1
    assert checked > 8


def test_feed_list_matches_the_feeds_written(two_sites):
    site, _ = two_sites
    doc = parse_llms((site / "llms.txt").read_text(encoding="utf-8"))
    listed = {u for _, u in doc["sections"]["Feeds (Atom 1.0)"] if u.endswith(".atom")}
    written = {
        f"{BASE_URL}/{p.relative_to(site).as_posix()}"
        for p in (site / "feeds").rglob("*.atom")
    }
    region_and_week = {u for u in written if "/county/" not in u}
    assert listed == region_and_week


def test_sources_come_from_the_snapshot_and_are_never_called_stocked(two_sites):
    site, _ = two_sites
    text = (site / "llms.txt").read_text(encoding="utf-8")
    assert "California Department of Fish and Wildlife" in text
    assert "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch" in text
    assert "scheduled" in text
    # Built without a v2 snapshot, the only source is California's schedule:
    # no other state and no report or plan wording is invented.
    assert "California" in text and "report source" not in text
    assert "plan source" not in text
    # No affiliate or tracking URL in the file.
    urls = re.findall(r"https?://[^\s)>\"]+", text)
    assert not [u for u in urls if re.search(r"amazon|tag=|utm_|\?", u)]


def test_two_builds_of_the_same_data_are_byte_identical(two_sites):
    a, b = two_sites
    assert (a / "llms.txt").read_bytes() == (b / "llms.txt").read_bytes()


def test_negative_control_parser_rejects_bad_files():
    with pytest.raises(AssertionError):
        parse_llms("Trout Truck\n\n> x\n")
    with pytest.raises(AssertionError):
        parse_llms("# T\n\n> x\n\n# Again\n")
    with pytest.raises(AssertionError):
        parse_llms("# T\n\n> x\n\n## S\n\nstray text\n")
    ok = parse_llms("# T\n\n> x\n\n## S\n\n- [a](https://e.com/): note\n")
    assert ok["sections"]["S"] == [("a", "https://e.com/")]


def test_negative_control_a_listed_missing_file_is_caught(two_sites):
    site, _ = two_sites
    text = (site / "llms.txt").read_text(encoding="utf-8")
    sabotaged = text.replace(
        f"{BASE_URL}/feeds/this-week.atom", f"{BASE_URL}/feeds/does-not-exist.atom"
    )
    assert sabotaged != text  # the sabotage applied
    urls = [u for items in parse_llms(sabotaged)["sections"].values() for _, u in items]
    missing = [
        u
        for u in urls
        if u.startswith(BASE_URL + "/")
        and u.endswith(".atom")
        and not (site / u[len(BASE_URL) + 1 :]).is_file()
    ]
    assert missing == [f"{BASE_URL}/feeds/does-not-exist.atom"]


def test_without_a_v2_snapshot_no_sources_section_is_invented():
    text = llms.render(
        site_name="Trout Truck",
        base_url=BASE_URL,
        attribution_text="Data: X.",
        states=[],
        region_feeds=[],
        week_label="week of 2026-09-13",
    )
    assert "Sources and open data" not in parse_llms(text)["sections"]


def test_states_link_only_when_there_is_more_than_one_state():
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

    kwargs = {
        "site_name": "Trout Truck",
        "base_url": BASE_URL,
        "attribution_text": "Data: X.",
        "region_feeds": [],
        "week_label": "week",
    }
    one = llms.render(states=[state("CA")], **kwargs)
    two = llms.render(states=[state("CA"), state("TN")], **kwargs)
    assert f"{BASE_URL}/states/" not in one
    assert f"{BASE_URL}/states/" in two


def _kinds_sentence(text: str, kind: str) -> str | None:
    m = re.search(rf"For a {kind} source \(([^)]*)\)", text)
    return m.group(1) if m else None


def _names(sentence: str | None) -> set[str]:
    return set(re.split(r", and |, | and ", sentence)) if sentence else set()


def _assert_kinds(text: str, expected: dict[str, set[str]]) -> None:
    for kind in ("schedule", "report", "plan"):
        assert _names(_kinds_sentence(text, kind)) == expected[kind], kind


@pytest.fixture(scope="module")
def multi_state_site(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("llms-states")
    _run_with_states(root, states=("TN", "MA", "MI", "NY"))
    v2 = json.loads((root / "site" / "snapshot" / "v2.json").read_text("utf-8"))
    return root / "site", v2


def test_the_text_follows_the_snapshots_states_and_their_semantics(multi_state_site):
    site, v2 = multi_state_site
    text = (site / "llms.txt").read_text(encoding="utf-8")
    expected: dict[str, set[str]] = {}
    for st in v2["states"]:
        expected.setdefault(st["semantics"], set()).add(st["name"])
    # The snapshot really has all three kinds, or this test proves nothing.
    assert set(expected) == {"schedule", "report", "plan"}
    assert expected["plan"] == {"New York"}
    _assert_kinds(text, expected)
    # New York is DEC's plan, in the plan sentence only.
    assert "New York" not in (_kinds_sentence(text, "schedule") or "")
    assert "New York" not in (_kinds_sentence(text, "report") or "")
    assert 'the site says "planned", never "scheduled"' in text
    # Every state in the snapshot has its source line, with its own semantics.
    doc = parse_llms(text)
    assert len(doc["sections"]["Sources and open data"]) >= len(v2["states"])
    for st in v2["states"]:
        line = next(
            ln
            for ln in text.split("\n")
            if ln.startswith("- [") and st["source"]["url"] in ln
        )
        assert f"source for {st['name']} ({st['semantics']})" in line
    # The summary names the kinds that exist and no more.
    summary = text.split("\n")[2]
    assert "schedules, reports, and plans" in summary


def test_negative_control_a_text_with_a_wrong_kind_is_caught(multi_state_site):
    site, v2 = multi_state_site
    text = (site / "llms.txt").read_text(encoding="utf-8")
    expected: dict[str, set[str]] = {}
    for st in v2["states"]:
        expected.setdefault(st["semantics"], set()).add(st["name"])
    _assert_kinds(text, expected)  # the real text passes
    sabotaged = text.replace("plan source (New York)", "report source (New York)")
    assert sabotaged != text  # the sabotage applied
    with pytest.raises(AssertionError):
        _assert_kinds(sabotaged, expected)


def test_the_cadence_sentence_does_not_assume_two_sources():
    def state(code: str, name: str, semantics: str) -> dict:
        return {
            "code": code,
            "name": name,
            "agency": {"name": f"{code} agency"},
            "source_url": f"https://e.com/{code}",
            "semantics": semantics,
            "terms_url": "https://e.com/terms",
            "files": [],
        }

    kwargs = {
        "site_name": "Trout Truck",
        "base_url": BASE_URL,
        "attribution_text": "Data: X.",
        "region_feeds": [],
        "week_label": "week of 2026-09-13",
    }
    only_ny_and_ca = llms.render(
        states=[state("CA", "California", "schedule"), state("NY", "New York", "plan")],
        **kwargs,
    )
    assert _names(_kinds_sentence(only_ny_and_ca, "plan")) == {"New York"}
    assert _kinds_sentence(only_ny_and_ca, "report") is None
    assert "schedules and plans" in only_ny_and_ca.split("\n")[2]
    assert "Tennessee" not in only_ny_and_ca
    three = llms.render(
        states=[
            state("CA", "California", "schedule"),
            state("TN", "Tennessee", "schedule"),
            state("MI", "Michigan", "report"),
        ],
        **kwargs,
    )
    assert _names(_kinds_sentence(three, "schedule")) == {"California", "Tennessee"}
    assert "plan source" not in three
    with pytest.raises(ValueError):
        llms.render(states=[state("XX", "Nowhere", "forecast")], **kwargs)
