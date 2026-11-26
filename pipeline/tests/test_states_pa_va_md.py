"""Pennsylvania (PFBC), Virginia (DWR) and Maryland (DNR): built and tested,
OFF by default (DECISIONS 0055), the same way as Oregon (0032).

The tests prove three things for each state: the reader reads the agency's
format honestly (refusing a changed, cut-off or inconsistent answer), its
flag keeps it out of a default run entirely (the registry, the pages, the
sitemap, the snapshot and the publish workflow), and its copy follows its
``COPY_RULES``.

Offline only. The fixtures under ``tests/fixtures/states-invented`` are
written by hand in each agency's format, as read on 2026-11-05, and every
water, date, place and count in them is invented. No agency data is
committed here.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
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
from cfpa.states import SOURCES, maryland, pennsylvania, virginia
from cfpa.states.base import (
    USER_AGENT_TEMPLATE,
    FetchedBody,
    RobotsDisallowedError,
    RobotsUnreadableError,
    StateFormatError,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
INVENTED = FIXTURES / "states-invented"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
UA = USER_AGENT_TEMPLATE.format(version="0.1.0")
NOW = dt.datetime(2026, 11, 5, 19, 0, 0, tzinfo=dt.UTC)

MODULES = {"PA": pennsylvania, "VA": virginia, "MD": maryland}
DEFAULT_SOURCES = {"TN", "MA", "MI", "NY"}
DEFAULT_ENABLED = ("TN", "MI", "MA", "NY")
ALL_FLAGS = tuple(flag for flag, _source in states.FLAGGED)


def _text(name: str) -> str:
    return (INVENTED / name).read_text(encoding="utf-8")


def _body(text: str, url: str = "file://fixture") -> FetchedBody:
    return FetchedBody(url=url, text=text, fetched_at=NOW, last_modified=None)


def _pa_bodies() -> list[FetchedBody]:
    return [_body(_text("pa-1.html")), _body(_text("pa-2.html"))]


# ---- the flags


@pytest.mark.parametrize("code", sorted(MODULES))
def test_each_state_is_off_unless_its_flag_is_exactly_one(code):
    flag = MODULES[code].ENV_FLAG
    assert states.flag_enabled(flag, {}) is False
    assert states.flag_enabled(flag, {flag: ""}) is False
    assert states.flag_enabled(flag, {flag: "0"}) is False
    assert states.flag_enabled(flag, {flag: "1"}) is True
    for value in ("yes", "true", "2"):
        with pytest.raises(ValueError, match="must be 1 or 0"):
            states.flag_enabled(flag, {flag: value})


@pytest.mark.parametrize("code", sorted(MODULES))
def test_each_flag_adds_its_own_state_and_nothing_else(code):
    assert set(states.registered_sources({})) == DEFAULT_SOURCES
    assert states.enabled_states({}) == DEFAULT_ENABLED
    on = {MODULES[code].ENV_FLAG: "1"}
    assert set(states.registered_sources(on)) == DEFAULT_SOURCES | {code}
    assert states.enabled_states(on) == (*DEFAULT_ENABLED, code)
    assert states.registered_sources(on)[code] is MODULES[code].SOURCE


def test_the_flags_are_distinct_and_none_is_in_fetched_states():
    assert len(set(ALL_FLAGS)) == len(ALL_FLAGS)
    for code in MODULES:
        assert code not in states.FETCHED_STATES
        assert code not in SOURCES  # this test process runs with no flag set


def _import_state(env_extra: dict[str, str]) -> dict[str, object]:
    env = {k: v for k, v in os.environ.items() if k not in ALL_FLAGS}
    env.update(env_extra)
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
    result: dict[str, object] = json.loads(out.stdout)
    return result


def test_a_fresh_process_has_none_of_them_by_default_and_each_with_its_flag():
    default = {"sources": sorted(DEFAULT_SOURCES), "enabled": list(DEFAULT_ENABLED)}
    assert _import_state({}) == default
    assert _import_state({f: "0" for f in ALL_FLAGS}) == default
    assert _import_state({virginia.ENV_FLAG: "1"}) == {
        "sources": sorted(DEFAULT_SOURCES | {"VA"}),
        "enabled": [*DEFAULT_ENABLED, "VA"],
    }


def test_the_publish_workflow_mentions_none_of_them():
    text = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    for code, mod in MODULES.items():
        assert f"states/{code.lower()}.json" not in text
        assert mod.ENV_FLAG not in text
    assert "states/tn.json" in text  # the control: the check can see a state


@pytest.mark.parametrize("code", sorted(MODULES))
def test_a_default_run_cannot_fetch_them(code, tmp_path: Path, capsys):
    rc = cli.main(
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
            code,
            "--states-fixtures",
            str(INVENTED),
            "--site-out",
            str(tmp_path / "site"),
        ]
    )
    assert rc == 1
    assert "unknown state code" in capsys.readouterr().err


# ---- a default build is byte-identical with or without them registered


class _Clock(dt.datetime):
    @classmethod
    def now(cls, tz: dt.tzinfo | None = None) -> _Clock:
        return cls(2026, 11, 5, 19, 0, 0, tzinfo=tz or dt.UTC)


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    ns = types.SimpleNamespace(**vars(dt))
    ns.datetime = _Clock
    monkeypatch.setattr(cli, "dt", ns)


def _build(root: Path, fetch: tuple[str, ...], fixtures: Path) -> Path:
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
        states_fixtures=fixtures,
        source_log_path=root / "source_log.json",
    )
    return out


def _digests(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_a_default_build_is_byte_identical_whether_or_not_they_are_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_clock: None
):
    real = FIXTURES / "states"
    default = _digests(_build(tmp_path / "default", ("TN",), real))
    for code, mod in MODULES.items():
        monkeypatch.setitem(SOURCES, code, mod.SOURCE)
    registered = _digests(_build(tmp_path / "registered", ("TN",), real))
    assert default == registered
    for code in MODULES:
        lower = code.lower()
        assert not [
            p for p in default if p.startswith((f"{lower}/", f"states/{lower}"))
        ]
    snap = json.loads(
        (tmp_path / "default" / "site" / "snapshot" / "v2.json").read_text()
    )
    assert not {s["code"] for s in snap["states"]} & set(MODULES)
    sitemap = (tmp_path / "default" / "site" / "sitemap.xml").read_text()
    for code in MODULES:
        assert f"/{code.lower()}/" not in sitemap


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


@pytest.mark.parametrize("code", sorted(MODULES))
def test_with_the_flag_on_and_a_fetch_the_pages_appear_and_follow_the_copy_rules(
    code, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_clock: None
):
    mod = MODULES[code]
    monkeypatch.setitem(SOURCES, code, mod.SOURCE)
    out = _build(tmp_path / "on", (code,), INVENTED)
    lower = code.lower()
    hub = out / lower / "index.html"
    assert hub.is_file()
    assert f"{BASE_URL}/{lower}/" in (out / "sitemap.xml").read_text()
    assert (tmp_path / "on" / "states" / f"{lower}.json").is_file()
    text = _visible(hub)
    assert mod.SOURCE.agency_short_name in text
    for page in (out / lower).rglob("index.html"):
        visible = _visible(page)
        if mod.SOURCE.semantics == "schedule":
            assert "stocked on" not in visible.lower(), page
        assert "planted" not in visible.lower(), page
        assert "None" not in visible.split(), page  # absence is never a value
    # A control: the same build without the fetch has none of it.
    monkeypatch.delitem(SOURCES, code)
    off = _build(tmp_path / "off", (), INVENTED)
    assert not (off / lower).exists()


def test_the_pennsylvania_pages_say_monday_weeks_sections_and_counties(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_clock: None
):
    monkeypatch.setitem(SOURCES, "PA", pennsylvania.SOURCE)
    out = _build(tmp_path / "pa", ("PA",), INVENTED)
    hub = _visible(out / "pa" / "index.html")
    assert "the week starting on a Monday" in hub
    assert "Hemlock Run, section 2" in hub
    waters = " ".join(_visible(p) for p in (out / "pa" / "water").glob("*/index.html"))
    assert "Clinton County, Pennsylvania" in waters


def test_the_virginia_city_is_a_place_and_never_a_county(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_clock: None
):
    monkeypatch.setitem(SOURCES, "VA", virginia.SOURCE)
    out = _build(tmp_path / "va", ("VA",), INVENTED)
    pages = " ".join(_visible(p) for p in (out / "va").rglob("index.html"))
    assert "City of Exampleton" in pages
    assert "City of Exampleton County" not in pages


# ---- Maryland: parsing


def test_maryland_reads_days_counts_ids_and_two_county_rows():
    feed = maryland.parse([_body(_text("md.json"))])
    assert {r.period.precision for r in feed.records} == {"day"}
    cedar = feed.waters["md-901"]
    assert (cedar.name, cedar.counties, cedar.source_id) == (
        "Cedar Hollow Pond",
        ("Garrett",),
        "901",
    )
    # Two rows for one location, day and species are added together.
    oct20 = [
        r
        for r in feed.records
        if r.water_id == "md-901" and r.period.start == dt.date(2026, 10, 20)
    ]
    assert [(r.species, r.count) for r in oct20] == [("Rainbow/Golden trout", 1000)]
    assert feed.waters["md-902"].counties == ("Howard", "Montgomery")
    assert feed.waters["md-903"].counties == ("Cecil",)  # DNR's "Cecill"


def test_maryland_never_guesses_a_county_or_a_count():
    feed = maryland.parse([_body(_text("md.json"))])
    assert feed.waters["md-904"].counties == ()  # DNR wrote the bare word "County"
    assert any("'County' is not a Maryland county" in n for n in feed.skipped_notes)
    (heron,) = [r for r in feed.records if r.water_id == "md-905"]
    assert heron.count is None  # an empty NumOfFish is unknown, never 0
    assert heron.species == "Rainbow/Golden/Brown trout"


def test_maryland_a_blank_count_makes_a_shared_day_unknown_not_partial():
    rows = json.loads(_text("md.json"))
    rows[1]["NumOfFish"] = ""
    feed = maryland.parse([_body(json.dumps(rows))])
    (r,) = [
        r
        for r in feed.records
        if r.water_id == "md-901" and r.period.start == dt.date(2026, 10, 20)
    ]
    assert r.count is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda rows: rows[0].pop("ActivityDate"), "missing"),
        (lambda rows: rows[0].__setitem__("ActivityDate", "20 Oct"), "not a date"),
        (lambda rows: rows[1].__setitem__("LOCATION", "Other Name"), "two names"),
        (lambda rows: rows[0].__setitem__("Species", "Rainbow+Gold"), "species"),
    ],
)
def test_maryland_a_changed_feed_is_refused_and_each_control_really_changed_it(
    change, message
):
    rows = json.loads(_text("md.json"))
    before = json.dumps(rows)
    change(rows)
    assert json.dumps(rows) != before
    with pytest.raises(StateFormatError, match=message):
        maryland.parse([_body(json.dumps(rows))])


def test_maryland_refuses_a_feed_that_is_not_a_list():
    with pytest.raises(StateFormatError, match="not a list"):
        maryland.parse([_body('{"data": []}')])
    with pytest.raises(StateFormatError, match="not JSON"):
        maryland.parse([_body("<html>Service unavailable</html>")])


def test_maryland_an_empty_feed_is_below_min_rows():
    feed = maryland.parse([_body("[]")])
    assert len(feed.records) < maryland.SOURCE.min_rows


# ---- Virginia: parsing


def test_virginia_reads_days_places_and_skips_a_row_with_no_date():
    feed = virginia.parse([_body(_text("va.html"))])
    assert {r.period.precision for r in feed.records} == {"day"}
    assert {r.species for r in feed.records} == {"Trout"}
    assert all(r.count is None for r in feed.records)
    assert feed.skipped == 1
    assert feed.skipped_notes == (
        'skipped Otter Bend Run (Madison County) has no date (DWR: "postponed")',
    )
    bland = feed.waters[virginia.water_id("Wren Creek [Bland]", "Bland County")]
    giles = feed.waters[virginia.water_id("Wren Creek [Giles]", "Giles County")]
    assert bland.id != giles.id
    assert bland.counties == ("Bland",)
    city = feed.waters[virginia.water_id("Maple Park Pond", "City of Exampleton")]
    assert (city.counties, city.towns) == ((), ("City of Exampleton",))
    juniper = feed.waters[
        virginia.water_id("Juniper Lake \u2013 Upper", "Craig County")
    ]
    assert juniper.name == "Juniper Lake \u2013 Upper"  # the &#8211; entity decoded
    days = sorted(r.period.start for r in feed.records if r.water_id == bland.id)
    assert days == [dt.date(2026, 10, 30), dt.date(2026, 11, 6)]


def test_virginia_is_a_schedule_of_days_from_the_monthly_page_only():
    s = virginia.SOURCE
    assert (s.semantics, s.date_precisions) == ("schedule", ("day",))
    assert s.data_urls == (virginia.PAGE_URL,)
    assert virginia.DAILY_URL not in s.data_urls


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("Date of stocking\t", "Stocking date\t", "headers changed"),
        ("Trout stocking schedule for November", "Stockings in November", "caption"),
        ("11/16/2026", "2026-11-16", "MM/DD/YYYY"),
        ("Craig County", "Craig Parish", "neither a county nor a city"),
        ('class="trout-stockings__table"', 'class="other-table"', "no monthly"),
    ],
)
def test_virginia_a_changed_page_is_refused_and_each_control_really_changed_it(
    old, new, message
):
    page = _text("va.html")
    sabotaged = page.replace(old, new)
    assert sabotaged != page
    with pytest.raises(StateFormatError, match=message):
        virginia.parse([_body(sabotaged)])


# ---- Pennsylvania: parsing


def test_pennsylvania_reads_days_monday_weeks_sections_and_species_marks():
    feed = pennsylvania.parse(_pa_bodies())
    hemlock2 = pennsylvania.water_id("Clinton", "Hemlock Run", "2")
    hemlock3 = pennsylvania.water_id("Clinton", "Hemlock Run", "3")
    kettle = pennsylvania.water_id("Clinton", "Kettle Pond", "0")
    assert feed.waters[hemlock2].name == "Hemlock Run, section 2"
    assert feed.waters[kettle].name == "Kettle Pond"
    assert feed.waters[kettle].counties == ("Clinton",)
    by_water: dict[str, set[tuple[str, str, str]]] = {}
    for r in feed.records:
        by_water.setdefault(r.water_id, set()).add(
            (r.period.precision, r.period.start.isoformat(), r.species)
        )
        assert r.count is None  # PFBC marks species; it gives no number
    assert by_water[hemlock2] == {
        ("day", "2026-11-10", "Brown trout"),
        ("day", "2026-11-10", "Rainbow trout"),
    }
    assert by_water[hemlock3] == {("week", "2026-11-16", "Rainbow trout")}
    (week,) = [r.period for r in feed.records if r.water_id == hemlock3]
    assert (week.end - week.start).days == pennsylvania.WEEK_DAYS - 1
    assert week.start.weekday() == 0
    # Two meeting places for one stocking are one record per species.
    assert by_water[kettle] == {
        ("day", "2026-11-12", "Brook trout"),
        ("day", "2026-11-12", "Rainbow trout"),
        ("day", "2026-11-12", "Golden trout"),
    }
    assert feed.skipped == 1  # Quiet Hollow Run has neither a date nor a week


def test_pennsylvania_an_empty_county_is_believed_only_with_pfbc_s_sentence():
    assert pennsylvania.parse_body(_text("pa-2.html"), "Potter") == []
    broken = _text("pa-2.html").replace(pennsylvania.EMPTY_SENTENCE, "Error")
    assert broken != _text("pa-2.html")
    with pytest.raises(StateFormatError, match="no stockings and no"):
        pennsylvania.parse_body(broken, "Potter")
    with pytest.raises(StateFormatError, match="does not name a county"):
        pennsylvania.parse_body("<html><body>Service unavailable</body></html>")


def test_pennsylvania_an_answer_for_another_county_is_refused():
    with pytest.raises(StateFormatError, match="asked PFBC for Centre"):
        pennsylvania.parse_body(_text("pa-1.html"), "Centre")


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("|11-16-2026|", "|11-17-2026|", "not a Monday"),
        ("|2026-11-10|", "|11/10/2026|", "not YYYY-MM-DD"),
        ("Stocked Trout Water|https://example.invalid/regs.pdf|F", "x|y|Q", "season"),
        ("|X|X||Example Fire Hall lot", "|Y|X||Example Fire Hall lot", "not X"),
        ("Hemlock Run|Clinton|2|", "Hemlock Run|Lycoming|2|", "stocking is in"),
        ("|Example Hatchery|", "|Example|Hatchery|", "fields"),
    ],
)
def test_pennsylvania_a_changed_answer_is_refused_and_each_control_really_changed_it(
    old, new, message
):
    page = _text("pa-1.html")
    sabotaged = page.replace(old, new, 2)
    assert sabotaged != page
    with pytest.raises(StateFormatError, match=message):
        pennsylvania.parse([_body(sabotaged)])


def test_pennsylvania_is_a_schedule_of_days_and_monday_weeks():
    s = pennsylvania.SOURCE
    assert (s.semantics, s.date_precisions) == ("schedule", ("day", "week"))
    assert (s.week_starts_on, s.week_days) == (0, 7)
    assert len(pennsylvania.COUNTIES) == 67
    assert len(set(pennsylvania.COUNTIES)) == 67


# ---- the fetches


def _robots(host: str, text: str = "User-agent: *\nDisallow: /private/") -> respx.Route:
    return respx.get(f"https://{host}/robots.txt").respond(
        200, text=text, headers={"content-type": "text/plain"}
    )


@respx.mock
def test_maryland_fetch_reads_robots_then_one_honest_get():
    robots = respx.get("https://webapps02.dnr.state.md.us/robots.txt").respond(404)
    data = respx.get(maryland.DATA_URL).respond(
        200, text=_text("md.json"), headers={"content-type": "application/json"}
    )
    with httpx.Client() as client:
        bodies = maryland.fetch(client, UA, lambda _s: None)
    assert (robots.call_count, data.call_count) == (1, 1)
    assert data.calls[0].request.headers["user-agent"] == UA
    assert maryland.parse(bodies).records


@respx.mock
def test_virginia_fetch_stops_at_a_disallowing_robots_txt_and_requests_nothing_else():
    _robots("dwr.virginia.gov", "User-agent: *\nDisallow: /fishing/")
    data = respx.get(virginia.DATA_URL)
    with httpx.Client() as client, pytest.raises(RobotsDisallowedError):
        virginia.fetch(client, UA, lambda _s: None)
    assert data.call_count == 0


@respx.mock
def test_virginia_fetch_reads_the_monthly_page_once():
    _robots("dwr.virginia.gov")
    data = respx.get(virginia.DATA_URL).respond(
        200, text=_text("va.html"), headers={"content-type": "text/html"}
    )
    daily = respx.get(virginia.DAILY_URL)
    with httpx.Client() as client:
        bodies = virginia.fetch(client, UA, lambda _s: None)
    assert (data.call_count, daily.call_count) == (1, 0)
    assert data.calls[0].request.headers["user-agent"] == UA
    assert virginia.parse(bodies).records


def _pa_answer(request: httpx.Request) -> httpx.Response:
    county = json.loads(request.content)["County"]
    if county == "Clinton":
        text = _text("pa-1.html")
    else:
        text = _text("pa-2.html").replace("is Potter", f"is {county}")
    return httpx.Response(200, text=text, headers={"content-type": "text/html"})


@respx.mock
def test_pennsylvania_fetch_posts_once_per_county_politely_and_honestly():
    robots = respx.get("https://fbweb.pa.gov/robots.txt").respond(404)
    data = respx.post(pennsylvania.DATA_URL).mock(side_effect=_pa_answer)
    sleeps: list[float] = []
    with httpx.Client() as client:
        bodies = pennsylvania.fetch(
            client, UA, sleeps.append, today=dt.date(2026, 11, 5)
        )
    assert robots.call_count == 1
    assert data.call_count == len(pennsylvania.COUNTIES) == len(bodies)
    assert sleeps == [pennsylvania.POLITE_DELAY_SECONDS] * data.call_count
    sent = [json.loads(c.request.content) for c in data.calls]
    assert [s["County"] for s in sent] == list(pennsylvania.COUNTIES)
    assert {s["StartDate"] for s in sent} == {"2026-10-22"}  # 14 days back
    assert {s["EndDate"] for s in sent} == {""}
    assert {c.request.headers["user-agent"] for c in data.calls} == {UA}
    assert pennsylvania.parse(bodies).records


@respx.mock
def test_pennsylvania_fetch_refuses_an_answer_for_the_wrong_county():
    respx.get("https://fbweb.pa.gov/robots.txt").respond(404)
    respx.post(pennsylvania.DATA_URL).respond(
        200, text=_text("pa-1.html"), headers={"content-type": "text/html"}
    )
    with httpx.Client() as client, pytest.raises(StateFormatError, match="asked PFBC"):
        pennsylvania.fetch(client, UA, lambda _s: None, today=dt.date(2026, 11, 5))


@respx.mock
def test_pennsylvania_fetch_stops_at_an_unreadable_robots_txt():
    respx.get("https://fbweb.pa.gov/robots.txt").respond(403, text="no")
    data = respx.post(pennsylvania.DATA_URL)
    with httpx.Client() as client, pytest.raises(RobotsUnreadableError):
        pennsylvania.fetch(client, UA, lambda _s: None, today=dt.date(2026, 11, 5))
    assert data.call_count == 0


# ---- the licences and the copy rules


@pytest.mark.parametrize("code", sorted(MODULES))
def test_each_licence_is_unknown_with_the_evidence_quoted(code):
    s = MODULES[code].SOURCE
    (lic,) = s.license_sources
    assert lic.commercial_reuse == "unknown"
    assert lic.terms_read_on == "2026-11-05"
    assert lic.terms_quote
    assert "unknown" in s.license_summary


def _copy(code: str) -> list[str]:
    s = MODULES[code].SOURCE
    return [
        s.disclaimer,
        s.license_summary,
        s.attribution_text,
        s.source_name,
        *(name for _code, name in s.regions),
    ]


@pytest.mark.parametrize("code", sorted(MODULES))
def test_each_state_s_copy_obeys_its_copy_rules(code):
    mod = MODULES[code]
    for text in _copy(code):
        assert not mod.FORBIDDEN.search(text), text
    d = mod.SOURCE.disclaimer
    assert "not endorsed" in d
    if mod.SOURCE.semantics == "schedule":
        assert "not confirmed stockings" in d
    else:
        assert "reported as done" in d


def test_the_copy_checks_catch_a_banned_word_and_each_sabotage_applied():
    for code, word in (("PA", "planted"), ("VA", "stocked on"), ("MD", "scheduled")):
        mod = MODULES[code]
        bad = mod.SOURCE.disclaimer + f" {word} "
        assert bad != mod.SOURCE.disclaimer
        assert mod.FORBIDDEN.search(bad)
