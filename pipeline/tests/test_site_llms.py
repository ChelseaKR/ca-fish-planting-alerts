"""/llms.txt: the llmstxt.org grammar, links that resolve to files the build
wrote, stability across two builds of the same data, and a negative control
for each check. Parsed with a small grammar parser, not substring checks."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

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


# ---- the hubs, feeds and read times an assistant needs (2026-11-08) --------


def test_every_county_page_written_is_listed_with_its_feed(two_sites):
    site, _ = two_sites
    doc = parse_llms((site / "llms.txt").read_text(encoding="utf-8"))
    listed = dict(doc["sections"]["California counties"])
    written = {
        f"{BASE_URL}/county/{p.parent.name}/"
        for p in (site / "county").glob("*/index.html")
    }
    assert written  # the build wrote county pages, or this proves nothing
    assert set(listed.values()) == written
    # Each line's Atom feed is a file the build wrote, and it is the feed of
    # that county, not another's.
    for line in (site / "llms.txt").read_text(encoding="utf-8").split("\n"):
        m = re.match(
            rf"^- \[(.+)\]\({re.escape(BASE_URL)}/county/([^/]+)/\): \d+ waters? on the record; "
            rf"Atom feed {re.escape(BASE_URL)}/(feeds/county/([^ ]+)\.atom)$",
            line,
        )
        if m:
            assert m.group(2) == m.group(4), line
            assert (site / m.group(3)).is_file(), line
    # The negative control: a county the build did not write is caught.
    assert f"{BASE_URL}/county/nowhere/" not in written


def test_calendar_feed_pattern_names_a_feed_the_build_wrote(two_sites):
    site, _ = two_sites
    text = (site / "llms.txt").read_text(encoding="utf-8")
    doc = parse_llms(text)
    assert "Calendar feeds (iCalendar)" in doc["sections"]
    pattern = f"{BASE_URL}/water/<name>/feed.ics"
    assert pattern in text
    slugs = [p.parent.name for p in (site / "water").glob("*/feed.ics")]
    assert slugs  # the build wrote calendar feeds
    real = pattern.replace("<name>", slugs[0])
    assert (site / real[len(BASE_URL) + 1 :]).is_file()
    # Negative control: the same pattern with a different file name points
    # at nothing, so the check is not vacuous.
    wrong = pattern.replace("<name>", slugs[0]).replace("feed.ics", "calendar.ics")
    assert not (site / wrong[len(BASE_URL) + 1 :]).is_file()
    assert "webcal://" in text and '"scheduled"' in text
    assert (
        "stocked" not in text.split("## Calendar feeds (iCalendar)")[1].split("##")[0]
    )


def test_the_build_states_when_californias_schedule_was_read(two_sites):
    site, _ = two_sites
    doc = parse_llms((site / "llms.txt").read_text(encoding="utf-8"))
    # FETCHED is the fixture's read time; the pages print it the same way.
    assert "California's schedule was read 2026-09-17 23:00 UTC" in doc["loose"]
    assert "not the time the page was fetched" in doc["loose"]
    assert llms.READING_NOTES in doc["loose"]
    # The reading notes never promise fish.
    assert "not a statement about whether fish are present" in llms.READING_NOTES
    assert "stocked" not in llms.READING_NOTES


def test_without_a_fetched_label_no_read_time_sentence_is_invented():
    text = llms.render(
        site_name="Trout Truck",
        base_url=BASE_URL,
        attribution_text="Data: X.",
        states=[],
        region_feeds=[],
        week_label="week of 2026-09-13",
    )
    assert "was read" not in text
    assert "## States" not in text
    assert "## California counties" not in text
    assert "## Calendar feeds" not in text


def test_states_section_lists_each_other_state_hub_with_its_read_time(
    multi_state_site,
):
    site, v2 = multi_state_site
    text = (site / "llms.txt").read_text(encoding="utf-8")
    doc = parse_llms(text)
    others = [s for s in v2["states"] if s["code"] != "CA"]
    assert len(others) >= 2  # or the section proves little
    listed = dict(doc["sections"]["States"])
    assert listed == {s["name"]: f"{BASE_URL}/{s['code'].lower()}/" for s in others}
    for s in others:
        line = next(ln for ln in text.split("\n") if ln.startswith(f"- [{s['name']}]"))
        assert (site / s["code"].lower() / "index.html").is_file()
        assert f"/{s['code'].lower()}/water/<name>/" in line
        n = sum(1 for w in v2["waters"] if w["state"] == s["code"])
        assert f"{n} water page" in line
        # The read time is the snapshot's, in the pages' format.
        stamp = s["checks"]["last_success_at"]
        label = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
        if s["source"].get("read_method") == "manual":
            assert "downloaded" in line
        else:
            assert f"last read {label}" in line
        if s["checks"]["last_attempt_ok"]:
            assert "failed" not in line
    # California has no hub page; Home is its hub.
    assert "California" not in listed


def _hub(**over: Any) -> dict[str, Any]:
    base = {
        "name": "Tennessee",
        "url": f"{BASE_URL}/tn/",
        "agency_name": "Tennessee Wildlife Resources Agency",
        "agency_short": "TWRA",
        "semantics": "schedule",
        "water_count": 3,
        "manual": False,
        "manual_sentence": "",
        "automatic_failing": False,
        "attempt_failed": False,
        "fetched_date": "2026-10-15",
        "fetched_label": "2026-10-15 13:31 UTC",
        "attempt_label": "2026-11-08 01:18 UTC",
    }
    base.update(over)
    return base


def _render_hubs(*hubs: dict[str, Any]) -> str:
    return llms.render(
        site_name="Trout Truck",
        base_url=BASE_URL,
        attribution_text="Data: X.",
        states=[],
        region_feeds=[],
        week_label="week of 2026-11-01",
        state_hubs=list(hubs),
    )


def test_a_failed_latest_check_is_said_on_the_hub_line():
    ok = _render_hubs(_hub())
    failed = _render_hubs(_hub(attempt_failed=True))
    assert "TWRA's data was last read 2026-10-15 13:31 UTC." in ok
    assert "failed" not in ok.split("## States")[1]
    assert (
        "The check on 2026-11-08 01:18 UTC failed, so the pages show the data "
        "from the last good read." in failed
    )
    # Negative control: the two renders differ only by that sentence.
    assert (
        failed.replace(
            " The check on 2026-11-08 01:18 UTC failed, so the pages show the data "
            "from the last good read.",
            "",
        )
        == ok
    )


def test_a_manual_load_uses_the_pages_own_sentence_and_never_says_failed():
    sentence = (
        "This data is from TWRA's published schedule file, downloaded 2026-11-07."
    )
    text = _render_hubs(
        _hub(manual=True, manual_sentence=sentence, attempt_failed=False)
    )
    assert sentence in text
    assert "last read" not in text.split("## States")[1]
    assert "failed" not in text.split("## States")[1]


def test_each_source_kind_is_named_in_its_own_words_and_never_stocked_for_a_schedule():
    text = _render_hubs(
        _hub(semantics="schedule"),
        _hub(
            name="Michigan",
            url=f"{BASE_URL}/mi/",
            agency_short="DNR",
            semantics="report",
        ),
        _hub(
            name="New York", url=f"{BASE_URL}/ny/", agency_short="DEC", semantics="plan"
        ),
    )
    section = text.split("## States")[1]
    tn, mi, ny = (ln for ln in section.split("\n") if ln.startswith("- ["))
    assert "stocking schedule (planned dates the agency can change)" in tn
    assert "stocked" not in tn and "confirmed" not in tn
    assert "stocking report (stockings already made)" in mi
    assert "seasonal stocking plan, in the agency's own words" in ny
    assert "1 water page " not in tn and "3 water pages" in tn
    with pytest.raises(KeyError):
        _render_hubs(_hub(semantics="forecast"))
