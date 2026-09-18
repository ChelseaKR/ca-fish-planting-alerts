import datetime as dt
from pathlib import Path

import httpx
import pytest

from cfpa import fetch

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
STALE = FIXTURES / "schedule-stale-2025-cache.html"
EMPTY_WEEK_MONDAY = FIXTURES / "schedule-empty-week-2026-09-14.html"
MIDWEEK = FIXTURES / "schedule-midweek-2026-09-17.html"


def test_extract_stated_today_reads_the_pages_own_date():
    html = FRESH.read_text(encoding="utf-8")
    assert fetch.extract_stated_today(html) == dt.date(2026, 9, 13)


def test_extract_stated_period():
    html = FRESH.read_text(encoding="utf-8")
    start, end = fetch.extract_stated_period(html)
    assert (start, end) == (dt.date(2025, 9, 13), dt.date(2026, 9, 27))


def test_stated_date_is_cdfws_week_start_not_the_fetch_day():
    """Real responses fetched on a Monday (2026-09-14) and a Thursday
    (2026-09-17, 03:10 UTC 09-18) both state 9/13/2026 -- the Sunday that
    begins CDFW's week. The widget states the current WEEK, not "today"."""
    for fixture in (FRESH, EMPTY_WEEK_MONDAY, MIDWEEK):
        stated = fetch.extract_stated_today(fixture.read_text(encoding="utf-8"))
        assert stated == dt.date(2026, 9, 13)
        assert stated.weekday() == 6  # Sunday


@pytest.mark.parametrize("day", range(13, 20))  # Sun 2026-09-13 .. Sat 2026-09-19
def test_page_for_this_week_is_fresh_on_every_day_of_the_week(day):
    """Regression: the old check read the week start as "today" and refused
    every scheduled run from Tuesday on ("2/3/4 day(s) stale") while the
    page was live -- publish.yml failed 2026-09-15, -16 and -17."""
    html = MIDWEEK.read_text(encoding="utf-8")
    stated = fetch.extract_stated_today(html)
    fetch.assert_fresh(stated, run_today=dt.date(2026, 9, day))  # must not raise


def test_last_weeks_page_is_refused_midweek():
    with pytest.raises(fetch.StalePageError) as excinfo:
        fetch.assert_fresh(dt.date(2026, 9, 6), run_today=dt.date(2026, 9, 17))
    assert "2026-09-06" in str(excinfo.value)
    assert "2026-09-13" in str(excinfo.value)


def test_last_weeks_page_is_allowed_on_sunday_only_as_rollover_skew():
    # Sunday run, CDFW's server not yet rolled over: one day of skew.
    fetch.assert_fresh(dt.date(2026, 9, 6), run_today=dt.date(2026, 9, 13))
    # Monday run: that is a cache, not skew.
    with pytest.raises(fetch.StalePageError):
        fetch.assert_fresh(dt.date(2026, 9, 6), run_today=dt.date(2026, 9, 14))


def test_next_weeks_page_is_allowed_on_saturday_only_as_rollover_skew():
    fetch.assert_fresh(dt.date(2026, 9, 20), run_today=dt.date(2026, 9, 19))
    with pytest.raises(fetch.StalePageError):
        fetch.assert_fresh(dt.date(2026, 9, 20), run_today=dt.date(2026, 9, 18))


def test_a_stated_date_that_is_not_a_sunday_is_format_drift_not_fresh_data():
    """If CDFW's widget ever starts stating the real day, the week-start
    comparison would silently accept it on Sundays only; refuse loudly."""
    html = FRESH.read_text(encoding="utf-8").replace(
        'text="Current-Future Plants (9/13/2026 - 9/27/2026)"',
        'text="Current-Future Plants (9/17/2026 - 10/1/2026)"',
    )
    assert "9/17/2026 - 10/1/2026" in html  # the mutation really landed
    with pytest.raises(fetch.PageFormatError, match="Thursday"):
        fetch.extract_stated_today(html)


def test_week_start_containing():
    assert fetch.week_start_containing(dt.date(2026, 9, 13)) == dt.date(2026, 9, 13)
    assert fetch.week_start_containing(dt.date(2026, 9, 17)) == dt.date(2026, 9, 13)
    assert fetch.week_start_containing(dt.date(2026, 9, 19)) == dt.date(2026, 9, 13)
    assert fetch.week_start_containing(dt.date(2026, 9, 20)) == dt.date(2026, 9, 20)


def test_fresh_fixture_passes_freshness_check():
    html = FRESH.read_text(encoding="utf-8")
    stated = fetch.extract_stated_today(html)
    fetch.assert_fresh(stated, run_today=dt.date(2026, 9, 13))  # must not raise


def test_stale_page_is_refused_not_treated_as_no_plants():
    """The core risk from the 2026-09-13 research notes: a stale cached page
    must never be silently accepted as this week's (possibly empty) data."""
    html = STALE.read_text(encoding="utf-8")
    stated = fetch.extract_stated_today(html)
    assert stated == dt.date(2025, 9, 14)
    with pytest.raises(fetch.StalePageError) as excinfo:
        fetch.assert_fresh(stated, run_today=dt.date(2026, 9, 13))
    assert "2025-09-14" in str(excinfo.value)
    assert "2026-09-13" in str(excinfo.value)


def test_load_fixture_stale_page_raises_end_to_end():
    with pytest.raises(fetch.StalePageError):
        page = fetch.load_fixture(str(STALE))
        fetch.assert_fresh(page.stated_today, run_today=dt.date(2026, 9, 13))


def test_load_fixture_populates_all_fields():
    page = fetch.load_fixture(str(FRESH))
    assert page.stated_today == dt.date(2026, 9, 13)
    assert page.stated_period_start == dt.date(2025, 9, 13)
    assert page.stated_period_end == dt.date(2026, 9, 27)
    assert len(page.content_sha256) == 64
    assert page.html


def test_robots_txt_permissive_allows_fetch(respx_mock):
    respx_mock.get(fetch.ROBOTS_URL).mock(
        return_value=httpx.Response(
            200, text="Sitemap: http://nrm.dfg.ca.gov/sitemap.xml\n"
        )
    )
    with httpx.Client() as client:
        fetch.check_robots(
            "ca-fish-planting-alerts/0.1.0 (+test)", client
        )  # must not raise


def test_robots_txt_disallow_blocks_fetch(respx_mock):
    respx_mock.get(fetch.ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /FishPlants/\n")
    )
    with httpx.Client() as client, pytest.raises(fetch.RobotsDisallowedError):
        fetch.check_robots("ca-fish-planting-alerts/0.1.0 (+test)", client)


def test_fetch_schedule_raises_fetch_error_on_http_failure(respx_mock):
    respx_mock.get(fetch.ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    respx_mock.get(fetch.SCHEDULE_URL).mock(return_value=httpx.Response(500))
    with httpx.Client() as client, pytest.raises(fetch.FetchError):
        fetch.fetch_schedule(version="0.1.0", client=client)


def test_fetch_schedule_raises_stale_on_live_stale_response(respx_mock):
    respx_mock.get(fetch.ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    respx_mock.get(fetch.SCHEDULE_URL).mock(
        return_value=httpx.Response(200, text=STALE.read_text(encoding="utf-8"))
    )
    with httpx.Client() as client, pytest.raises(fetch.StalePageError):
        fetch.fetch_schedule(
            version="0.1.0", run_today=dt.date(2026, 9, 13), client=client
        )


def test_user_agent_names_the_repo():
    ua = fetch.USER_AGENT_TEMPLATE.format(version="0.1.0")
    assert "ca-fish-planting-alerts" in ua
    assert "github.com/ChelseaKR/ca-fish-planting-alerts" in ua
