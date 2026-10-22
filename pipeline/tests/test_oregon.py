"""Oregon (ODFW), built and tested but OFF by default.

The tests prove three things: the adapter reads ODFW's pinned pages honestly
(refusing a changed, cut-off or inconsistent page), the flag keeps Oregon out
of a default run entirely (the registry, the pages, the sitemap, the
snapshot and the publish workflow), and the copy follows the rules in
``cfpa.states.oregon.COPY_RULES``.

Offline only: every page is a pinned fixture under ``tests/fixtures/states``
(``or-1.html`` .. ``or-4.html``, the ``oregon-*.html`` set), saved from
https://myodfw.com/fishing/species/trout/stocking-schedule on 2026-10-21 UTC
(the evening of 2026-10-20 Pacific). Nothing here touches the network and
nothing reads a daily-rewritten data file.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import subprocess
import sys
import types
from html.parser import HTMLParser
from pathlib import Path

import httpx
import pytest
import respx

from cfpa import cli, states
from cfpa.states import SOURCES, oregon
from cfpa.states.base import (
    USER_AGENT_TEMPLATE,
    FetchedBody,
    RobotsUnreadableError,
    StateFormatError,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "states"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
UA = USER_AGENT_TEMPLATE.format(version="0.1.0")
NOW = dt.datetime(2026, 10, 21, 19, 0, 0, tzinfo=dt.UTC)
FLAG_ON = {oregon.ENV_FLAG: "1"}


def _text(name: str) -> str:
    return (STATE_FIXTURES / name).read_text(encoding="utf-8")


def _body(text: str, url: str = "file://fixture") -> FetchedBody:
    return FetchedBody(url=url, text=text, fetched_at=NOW, last_modified=None)


def _week_pages() -> list[FetchedBody]:
    return [_body(_text(f"or-{i}.html")) for i in range(1, 5)]


def _zone_pages() -> list[FetchedBody]:
    return [_body(_text(f"oregon-busy-zone{i}.html")) for i in range(1, 7)]


# ---- the flag


def test_oregon_is_off_unless_the_flag_is_exactly_one():
    assert states.oregon_enabled({}) is False
    assert states.oregon_enabled({oregon.ENV_FLAG: ""}) is False
    assert states.oregon_enabled({oregon.ENV_FLAG: "0"}) is False
    assert states.oregon_enabled(FLAG_ON) is True


@pytest.mark.parametrize("value", ["yes", "true", "on", "2"])
def test_a_flag_value_that_is_not_one_or_zero_refuses_instead_of_guessing(value):
    with pytest.raises(ValueError, match="must be 1 or 0"):
        states.oregon_enabled({oregon.ENV_FLAG: value})


def test_the_registry_and_the_daily_run_only_know_oregon_behind_the_flag():
    assert set(states.registered_sources({})) == {"TN", "MA", "MI"}
    assert states.enabled_states({}) == ("TN",)
    assert set(states.registered_sources(FLAG_ON)) == {"TN", "MA", "MI", "OR"}
    assert states.enabled_states(FLAG_ON) == ("TN", "OR")


def _import_state(env_value: str | None) -> dict[str, object]:
    env = {k: v for k, v in os.environ.items() if k != oregon.ENV_FLAG}
    if env_value is not None:
        env[oregon.ENV_FLAG] = env_value
    code = (
        "import json, cfpa.states as s;"
        "print(json.dumps({'sources': sorted(s.SOURCES),"
        " 'enabled': list(s.ENABLED_STATES)}))"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    result: dict[str, object] = json.loads(out.stdout)
    return result


def test_a_fresh_process_has_no_oregon_by_default_and_has_it_with_the_flag():
    assert _import_state(None) == {"sources": ["MA", "MI", "TN"], "enabled": ["TN"]}
    assert _import_state("0") == {"sources": ["MA", "MI", "TN"], "enabled": ["TN"]}
    assert _import_state("1") == {
        "sources": ["MA", "MI", "OR", "TN"],
        "enabled": ["TN", "OR"],
    }


def test_the_publish_workflow_does_not_mention_oregon():
    text = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    assert "or.json" not in text
    assert oregon.ENV_FLAG not in text
    assert "states/tn.json" in text  # the control: the check can see a state


def test_a_default_run_cannot_fetch_oregon(tmp_path: Path, capsys):
    assert "OR" not in SOURCES  # the default registry of this test process
    code = cli.main(
        [
            "--fixture",
            str(FRESH),
            "--fixture-fetched-at",
            "2026-09-13T12:00:00+00:00",
            "--run-today",
            "2026-09-13",
            "--history",
            str(tmp_path / "history.json"),
            "--aliases",
            str(tmp_path / "aliases.json"),
            "--source-log",
            str(tmp_path / "log.json"),
            "--states-dir",
            str(tmp_path / "states"),
            "--states",
            "OR",
            "--states-fixtures",
            str(STATE_FIXTURES),
            "--site-out",
            str(tmp_path / "site"),
        ]
    )
    assert code == 1
    assert "unknown state code" in capsys.readouterr().err


# ---- a default build is byte-identical with or without Oregon registered


class _Clock(dt.datetime):
    @classmethod
    def now(cls, tz: dt.tzinfo | None = None) -> _Clock:
        return cls(2026, 10, 21, 19, 0, 0, tzinfo=tz or dt.UTC)


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    ns = types.SimpleNamespace(**vars(dt))
    ns.datetime = _Clock
    monkeypatch.setattr(cli, "dt", ns)


def _build(root: Path, fetch: tuple[str, ...]) -> Path:
    root.mkdir()
    out = root / "site"
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=fetch,
        states_fixtures=STATE_FIXTURES,
        source_log_path=root / "source_log.json",
    )
    return out


def _digests(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_a_default_build_is_byte_identical_whether_or_not_oregon_is_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_clock: None
):
    default = _digests(_build(tmp_path / "default", ("TN",)))
    # Registered (flag on) but not fetched and with no history: every other
    # state is built from the same fixtures, so any difference is Oregon's.
    monkeypatch.setitem(SOURCES, "OR", oregon.SOURCE)
    registered = _digests(_build(tmp_path / "registered", ("TN",)))
    assert default == registered
    assert not [p for p in default if p.startswith(("or/", "states/or"))]
    assert "or.json" not in {Path(p).name for p in default}
    sitemap = (tmp_path / "default" / "site" / "sitemap.xml").read_text()
    assert "/or/" not in sitemap


def test_with_the_flag_on_and_a_fetch_the_pages_and_sitemap_appear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_clock: None
):
    monkeypatch.setitem(SOURCES, "OR", oregon.SOURCE)
    out = _build(tmp_path / "on", ("TN", "OR"))
    hub = out / "or" / "index.html"
    assert hub.is_file()
    sitemap = (out / "sitemap.xml").read_text()
    assert f"{BASE_URL}/or/" in sitemap
    # Oregon's own history file, written beside Tennessee's.
    assert (tmp_path / "on" / "states" / "or.json").is_file()
    # A control: the same build without the fetch has none of it.
    monkeypatch.delitem(SOURCES, "OR")
    off = _build(tmp_path / "off", ("TN",))
    assert not (off / "or").exists()


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _visible(path: Path) -> str:
    p = _Text()
    p.feed(path.read_text(encoding="utf-8"))
    return " ".join(" ".join(p.parts).split())


def test_the_oregon_pages_say_monday_weeks_and_zones_and_follow_the_copy_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_clock: None
):
    monkeypatch.setitem(SOURCES, "OR", oregon.SOURCE)
    out = _build(tmp_path / "on", ("OR",))
    hub = _visible(out / "or" / "index.html")
    assert "the week starting on a Monday" in hub
    assert "Sunday" not in hub
    assert "This week: the week of 2026-10-19" in hub
    assert "Willamette Zone" in hub  # the Where column and the index carry the zone
    assert "()" not in hub
    water = _visible(next((out / "or" / "water").glob("*/index.html")))
    assert "Zone, Oregon" in water
    for page in (out / "or").rglob("index.html"):
        text = _visible(page)
        # Shared page chrome says "most recent first"; the claim rule is about
        # a happened-stocking, so the page check is the two claim phrases.
        assert not oregon.FORBIDDEN_CLAIMS.search(text), page
    assert "Legal-size trout" in hub


# ---- parsing ODFW's pinned pages


def test_parse_reads_weeks_zones_classes_and_planned_counts():
    feed = oregon.parse(_week_pages())
    assert feed.skipped == 0
    weeks = {r.period.start for r in feed.records}
    assert weeks == {
        dt.date(2026, 10, 19),
        dt.date(2026, 10, 26),
        dt.date(2026, 11, 2),
        dt.date(2026, 11, 9),
    }
    assert {r.period.precision for r in feed.records} == {"week"}
    for r in feed.records:
        assert r.period.start.weekday() == 0
        assert r.period.end == r.period.start + dt.timedelta(days=4)
        assert r.period.label == f"week of {r.period.start.isoformat()}"
    assert {r.species for r in feed.records} <= set(oregon.COLUMNS.values())
    hagg = [r for r in feed.records if r.water_id == "or-henry-hagg-lk-willamette"]
    assert {
        r.species: r.count for r in hagg if r.period.start.isoformat() == "2026-10-19"
    } == {
        "Legal-size trout": 3000,
        "Trophy trout": 1100,
    }
    meta = feed.waters["or-henry-hagg-lk-willamette"]
    assert (meta.name, meta.region, meta.counties) == (
        "Henry Hagg Lake",
        "Willamette",
        (),
    )


def test_the_busy_week_split_by_zone_parses_and_every_fish_is_counted_once():
    bodies = _zone_pages()
    feed = oregon.parse(bodies)
    expected = sum(
        sum(row.counts.values()) for b in bodies for row in oregon.parse_body(b.text)
    )
    assert expected > 0
    assert sum(r.count or 0 for r in feed.records) == expected
    assert {m.region for m in feed.waters.values()} <= set(oregon.ZONES)


def test_two_rows_for_one_water_and_week_are_added_not_overwritten():
    page = _text("or-1.html")
    row_start = page.index("<tr", page.index("<tbody"))
    row_end = page.index("</tr>", row_start) + 5
    doubled = page[:row_end] + page[row_start:row_end] + page[row_end:]
    assert doubled != page  # the sabotage landed
    base = oregon.parse([_body(page)])
    twice = oregon.parse([_body(doubled)])
    assert sum(r.count or 0 for r in twice.records) > sum(
        r.count or 0 for r in base.records
    )
    first = oregon.parse_body(page)[0]
    assert sum(
        r.count or 0
        for r in twice.records
        if r.water_id == oregon.water_id(first.name, first.zone)
        and r.period.start == first.start
    ) == 2 * sum(
        r.count or 0
        for r in base.records
        if r.water_id == oregon.water_id(first.name, first.zone)
        and r.period.start == first.start
    )


def test_a_water_is_a_name_plus_a_zone():
    assert oregon.water_id("LOST LK", "Central") != oregon.water_id(
        "LOST LK", "Northwest"
    )
    assert oregon.water_id("LOST LK", "Central") == "or-lost-lk-central"


def test_an_empty_week_is_believed_only_with_the_filter_form():
    assert oregon.parse_body(_text("oregon-empty-week.html")) == []
    with pytest.raises(StateFormatError, match="neither the table nor the filter form"):
        oregon.parse_body("<html><body><p>Service unavailable</p></body></html>")


def test_a_run_whose_every_week_is_empty_is_refused_not_read_as_nothing_scheduled():
    feed = oregon.parse([_body(_text("oregon-empty-week.html"))])
    assert feed.records == []
    assert len(feed.records) < oregon.SOURCE.min_rows


def test_a_page_at_the_row_cap_is_refused_as_possibly_cut_off():
    capped = _text("oregon-busy-capped.html")
    assert len(oregon.parse_body(capped)) == oregon.ROW_CAP
    with pytest.raises(StateFormatError, match="cap"):
        oregon.parse([_body(capped)])


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (">Legals<", ">Standard<", "headers changed"),
        (">Willamette /", ">Mars /", "is new"),
    ],
)
def test_a_changed_feed_is_refused_and_each_control_really_changed_it(
    old, new, message
):
    page = _text("or-1.html")
    sabotaged = page.replace(old, new, 1)
    assert sabotaged != page
    with pytest.raises(StateFormatError, match=message):
        oregon.parse([_body(sabotaged)])


def test_a_total_that_is_not_the_sum_of_the_columns_is_refused():
    page = _text("or-1.html")
    first = oregon.parse_body(page)[0]
    total = f"{sum(first.counts.values()):,}"
    start = page.index(total, page.index("<tbody"))
    sabotaged = page[:start] + "999999" + page[start + len(total) :]
    assert sabotaged != page
    with pytest.raises(StateFormatError, match="not the sum"):
        oregon.parse([_body(sabotaged)])


def test_a_week_that_does_not_start_on_a_monday_is_refused():
    page = _text("or-1.html")
    sabotaged = page.replace("2026-10-19", "2026-10-18")
    assert sabotaged != page
    with pytest.raises(StateFormatError, match="Monday"):
        oregon.parse([_body(sabotaged)])


def test_names_are_made_readable_without_guessing():
    assert oregon.display_name("HENRY HAGG LK") == "Henry Hagg Lake"
    assert oregon.display_name("APPLEGATE RES") == "Applegate Reservoir"
    # A name with text ODFW wrote in mixed case is left as written.
    assert "Cott. Grv. Pd" in oregon.display_name("ROW R NATURE PK-Fmr Cott. Grv. Pd")


# ---- the fetch


def _routes(pages: dict[tuple[str, str | None], str]):
    def answer(request: httpx.Request) -> httpx.Response:
        q = request.url.params
        key = (q["field_planned_stocking_date_value"], q.get("field_zone_value"))
        return httpx.Response(
            200,
            text=pages.get(key, _text("oregon-empty-week.html")),
            headers={"content-type": "text/html; charset=utf-8"},
        )

    return answer


@respx.mock
def test_fetch_reads_a_fixed_window_politely_and_splits_a_capped_week_by_zone():
    robots = respx.get("https://myodfw.com/robots.txt").respond(
        200,
        text="User-agent: *\nDisallow: /search/",
        headers={"content-type": "text/plain"},
    )
    pages: dict[tuple[str, str | None], str] = {
        ("2027-04-26", None): _text("oregon-busy-capped.html"),
    }
    for i in range(1, len(oregon.ZONES) + 1):
        pages[("2027-04-26", str(i))] = _text(f"oregon-busy-zone{i}.html")
    data = respx.get(oregon.DATA_URL).mock(side_effect=_routes(pages))
    sleeps: list[float] = []
    with httpx.Client() as client:
        bodies = oregon.fetch(client, UA, sleeps.append, today=dt.date(2027, 4, 28))
    assert robots.call_count == 1
    assert data.call_count == oregon.HORIZON_WEEKS + len(oregon.ZONES)
    assert sleeps == [oregon.POLITE_DELAY_SECONDS] * data.call_count
    # The capped page itself is never returned; its six zones are.
    assert len(bodies) == (oregon.HORIZON_WEEKS - 1) + len(oregon.ZONES)
    mondays = [
        c.request.url.params["field_planned_stocking_date_value"] for c in data.calls
    ]
    assert mondays[0] == "2027-04-26"  # the Monday of the week that holds "today"
    ends = {
        c.request.url.params["field_planned_stocking_date_end_value"]
        for c in data.calls[:1]
    }
    assert ends == {"2027-04-30"}
    zones = [
        c.request.url.params["field_zone_value"]
        for c in data.calls
        if "field_zone_value" in c.request.url.params
    ]
    assert zones == ["1", "2", "3", "4", "5", "6"]
    sent = {c.request.headers["user-agent"] for c in data.calls}
    assert sent == {UA}
    assert oregon.parse(bodies).records


@respx.mock
def test_fetch_refuses_a_zone_that_still_fills_the_cap():
    respx.get("https://myodfw.com/robots.txt").respond(
        200, text="User-agent: *\nAllow: /", headers={"content-type": "text/plain"}
    )
    capped = _text("oregon-busy-capped.html")
    respx.get(oregon.DATA_URL).mock(
        side_effect=_routes(
            {
                ("2027-04-26", None): capped,
                **{("2027-04-26", str(i)): capped for i in range(1, 7)},
            }
        )
    )
    with httpx.Client() as client, pytest.raises(StateFormatError, match="still fills"):
        oregon.fetch(client, UA, lambda _s: None, today=dt.date(2027, 4, 26))


@respx.mock
def test_fetch_stops_at_an_unreadable_robots_txt_and_requests_nothing_else():
    respx.get("https://myodfw.com/robots.txt").respond(403, text="no")
    data = respx.get(oregon.DATA_URL)
    with httpx.Client() as client, pytest.raises(RobotsUnreadableError):
        oregon.fetch(client, UA, lambda _s: None, today=dt.date(2026, 10, 21))
    assert data.call_count == 0


def test_the_default_window_starts_on_this_weeks_monday_in_pacific_time():
    assert oregon.monday_of(dt.date(2026, 10, 25)) == dt.date(2026, 10, 19)  # a Sunday
    assert oregon.monday_of(dt.date(2026, 10, 19)) == dt.date(2026, 10, 19)
    assert oregon.window_params(dt.date(2026, 10, 19), "Central") == {
        "field_planned_stocking_date_value": "2026-10-19",
        "field_planned_stocking_date_end_value": "2026-10-23",
        "field_zone_value": "1",
    }


# ---- the licence and the copy rules


def test_the_licence_is_recorded_as_unknown_with_the_evidence_quoted():
    (lic,) = oregon.SOURCE.license_sources
    assert lic.commercial_reuse == "unknown"
    assert lic.terms_url == "https://www.oregon.gov/pages/terms-and-conditions.aspx"
    assert "Copyright 2026 Oregon Department of Fish & Wildlife" in lic.terms_quote
    assert "unknown" in oregon.SOURCE.license_summary


def _oregon_copy() -> list[str]:
    s = oregon.SOURCE
    return [
        s.disclaimer,
        s.license_summary,
        s.attribution_text,
        s.source_name,
        *oregon.COLUMNS.values(),
        *(name for _code, name in s.regions),
        s.week_phrase,
    ]


def test_the_oregon_copy_obeys_the_copy_rules():
    for text in _oregon_copy():
        assert not oregon.FORBIDDEN.search(text), text
    d = oregon.SOURCE.disclaimer
    assert "scheduled" in d and "not confirmed stockings" in d
    assert "Monday that starts the week" in d
    assert "week before or after" in d
    assert "not a rate" in d
    assert "inch" not in " ".join(_oregon_copy()).lower()


def test_the_copy_check_catches_a_banned_word_and_the_sabotage_applied():
    bad = oregon.SOURCE.disclaimer.replace("scheduled weeks", "planted weeks")
    assert bad != oregon.SOURCE.disclaimer
    assert oregon.FORBIDDEN.search(bad)
    bad2 = "Stocked on 2026-10-19"
    assert oregon.FORBIDDEN.search(bad2)


def test_oregon_is_a_schedule_of_weeks_and_nothing_finer():
    s = oregon.SOURCE
    assert (s.semantics, s.date_precisions) == ("schedule", ("week",))
    assert (s.week_starts_on, s.week_days) == (0, 5)
    assert (states.tn.SOURCE.week_starts_on, states.tn.SOURCE.week_days) == (6, 7)
