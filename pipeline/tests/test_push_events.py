"""The web push diff and its words (DECISIONS 0069, ``cfpa.push``).

A message exists for a water whose listed, dated, this-week-or-later schedule
differs between the snapshot that was live and the one just built: a new
week or day, a date the agency dropped, a date that moved. It never exists
for a TBD month, a month letter, a past week, a water new to or gone from
the snapshot, a report state, a plan state, or a cold start with no previous
snapshot. Every message uses the pages' own words. Each negative control
shows its sabotage changed the input before it shows the check caught it.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from cfpa import push

BASE = "https://example.invalid"
# The pages' rules: a schedule is not a confirmation, a message is not a
# promise, and the box's words are never superlatives.
BANNED = re.compile(
    r"\b(stocked|planted on|stocked on|only|first|best|guarantee\w*|alert\w*|notification\w*)\b",
    re.I,
)

CA: dict[str, Any] = {
    "code": "CA",
    "name": "California",
    "semantics": "schedule",
    "agency": {
        "name": "California Department of Fish and Wildlife",
        "short_name": "CDFW",
    },
    "current_week": {
        "start": "2026-11-08",
        "end": "2026-11-14",
        "label": "week of 2026-11-08",
    },
}
TN: dict[str, Any] = {
    "code": "TN",
    "name": "Tennessee",
    "semantics": "schedule",
    "agency": {"name": "Tennessee Wildlife Resources Agency", "short_name": "TWRA"},
    "current_week": {
        "start": "2026-11-08",
        "end": "2026-11-14",
        "label": "week of 2026-11-08",
    },
}
MA: dict[str, Any] = {**TN, "code": "MA", "name": "Massachusetts", "semantics": "report",
                      "agency": {"name": "MassWildlife", "short_name": "MassWildlife"}}  # fmt: skip
NY: dict[str, Any] = {**TN, "code": "NY", "name": "New York", "semantics": "plan",
                      "agency": {"name": "NYS DEC", "short_name": "NYS DEC"}}  # fmt: skip


def _period(precision: str, start: str) -> dict[str, str]:
    d = dt.date.fromisoformat(start)
    if precision == "day":
        end = d
    elif precision == "week":
        end = d + dt.timedelta(days=6)
    elif precision == "month":
        nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        end = nxt - dt.timedelta(days=1)
    else:
        end = d + dt.timedelta(days=30)
    return {
        "precision": precision,
        "start": start,
        "end": end.isoformat(),
        "label": start,
    }


def _plant(
    precision: str, start: str, species: str = "Trout", status: str = "listed"
) -> dict[str, Any]:
    return {
        "period": _period(precision, start),
        "species": species,
        "status": status,
        "count": None,
        "first_observed_at": "2026-10-12T19:18:13Z",
        "last_observed_at": "2026-11-08T13:20:00Z",
    }


def _water(
    state: str,
    plants: list[dict[str, Any]],
    *,
    wid: str = "cdfw-123",
    name: str = "Shadow Cliff Lake",
    site_path: str = "/water/shadow-cliff-lake/",
    months_note: str | None = None,
) -> dict[str, Any]:
    return {
        "id": wid,
        "state": state,
        "name": name,
        "site_path": site_path,
        "months_note": months_note,
        "plants": plants,
    }


def _snap(states: list[dict[str, Any]], waters: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": "test", "states": states, "waters": waters}


def _diff(
    before: dict[str, Any] | None, after: dict[str, Any]
) -> list[push.Notification]:
    return push.diff_snapshots(before, after, base_url=BASE)


WEEK_A = _plant("week", "2026-11-08")
WEEK_B = _plant("week", "2026-11-15")
WEEK_C = _plant("week", "2026-11-22")


# ---- California -----------------------------------------------------------------


def test_a_new_week_is_one_message_in_the_pages_words():
    before = _snap([CA], [_water("CA", [WEEK_A])])
    after = _snap([CA], [_water("CA", [WEEK_A, WEEK_B])])
    (n,) = _diff(before, after)
    assert n.water_id == "cdfw-123"
    assert n.state == "CA"
    assert n.title == "Shadow Cliff Lake: scheduled, week of Nov 15"
    assert n.body == (
        "CDFW lists Shadow Cliff Lake for planting the week of Sunday, November 15, "
        "2026. Scheduled, not confirmed: CDFW's plans can change."
    )
    assert n.url == (
        f"{BASE}/water/shadow-cliff-lake/?utm_source=web-push&utm_medium=push"
        "&utm_campaign=schedule-change"
    )
    assert n.tag == "cdfw-123"
    assert n.to_json() == {
        "water_id": "cdfw-123", "state": "CA", "title": n.title, "body": n.body,
        "url": n.url, "tag": "cdfw-123",
    }  # fmt: skip


def test_a_dropped_week_is_a_schedule_change_in_cdfws_own_status_word():
    before = _snap([CA], [_water("CA", [WEEK_A, WEEK_B])])
    after = _snap(
        [CA], [_water("CA", [WEEK_A, _plant("week", "2026-11-15", status="removed")])]
    )
    (n,) = _diff(before, after)
    assert n.title == "Shadow Cliff Lake: schedule changed"
    assert n.body == (
        "CDFW took the week of Sunday, November 15, 2026 off its planting schedule. "
        "CDFW's plans can change."
    )


def test_a_moved_week_says_from_and_to():
    before = _snap([CA], [_water("CA", [WEEK_B])])
    after = _snap(
        [CA], [_water("CA", [_plant("week", "2026-11-15", status="removed"), WEEK_C])]
    )
    (n,) = _diff(before, after)
    assert n.title == "Shadow Cliff Lake: schedule changed"
    assert n.body == (
        "CDFW moved Shadow Cliff Lake from the week of Sunday, November 15, 2026 to "
        "the week of Sunday, November 22, 2026. Scheduled, not confirmed: CDFW's "
        "plans can change."
    )


def test_several_changes_list_what_is_now_and_no_longer_listed():
    before = _snap([CA], [_water("CA", [WEEK_A])])
    after = _snap(
        [CA],
        [
            _water(
                "CA", [_plant("week", "2026-11-08", status="removed"), WEEK_B, WEEK_C]
            )
        ],
    )
    (n,) = _diff(before, after)
    assert n.body == (
        "Now listed: the week of Sunday, November 15, 2026 and the week of Sunday, "
        "November 22, 2026. No longer listed: the week of Sunday, November 8, 2026. "
        "Scheduled, not confirmed: CDFW's plans can change."
    )


def test_a_dozen_new_dates_stay_short_enough_for_the_service():
    weeks = [_plant("week", f"2027-0{m}-0{d}") for m in (1, 2, 3, 4) for d in (3, 4, 5)]
    long_name = {
        "name": "A Very Long Water Name Reservoir Below The Old Dam North Fork"
    }
    before = _snap([CA], [_water("CA", [WEEK_A], **long_name)])
    after = _snap([CA], [_water("CA", [*weeks], **long_name)])
    (n,) = _diff(before, after)
    assert "12 dates, from" in n.body
    assert "No longer listed: the week of Sunday, November 8, 2026." in n.body
    assert len(n.title) <= 200 and len(n.body) <= 600


def test_one_message_per_water_and_only_for_the_waters_that_changed():
    quiet = _water(
        "CA", [WEEK_A], wid="cdfw-1", name="Quiet Lake", site_path="/water/quiet-lake/"
    )
    before = _snap([CA], [quiet, _water("CA", [WEEK_A])])
    after = _snap([CA], [quiet, _water("CA", [WEEK_A, WEEK_B])])
    out = _diff(before, after)
    assert [n.water_id for n in out] == ["cdfw-123"]


# ---- Tennessee ------------------------------------------------------------------


def test_a_tennessee_day_names_twras_species_and_twras_caveat():
    doe = dict(
        wid="tn-carter-doe-river",
        name="Doe River",
        site_path="/tn/water/doe-river-carter-county/",
    )
    before = _snap([TN], [_water("TN", [], **doe)])
    after = _snap(
        [TN], [_water("TN", [_plant("day", "2026-12-03", "Rainbow Trout")], **doe)]
    )
    (n,) = _diff(before, after)
    assert n.title == "Doe River: scheduled, Dec 3"
    weekday = dt.date(2026, 12, 3).strftime("%A")
    assert n.body == (
        f"TWRA lists Rainbow Trout at Doe River for {weekday}, December 3, 2026. "
        "Scheduled, not confirmed: TWRA says any stocking could be postponed or "
        "cancelled."
    )
    assert n.url.startswith(
        f"{BASE}/tn/water/doe-river-carter-county/?utm_source=web-push"
    )


def test_a_tennessee_week_carries_twras_five_day_rule_and_names_both_species():
    doe = dict(
        wid="tn-carter-doe-river",
        name="Doe River",
        site_path="/tn/water/doe-river-carter-county/",
    )
    before = _snap([TN], [_water("TN", [], **doe)])
    after = _snap(
        [TN],
        [
            _water(
                "TN",
                [
                    _plant("week", "2026-12-06", "Rainbow Trout"),
                    _plant("week", "2026-12-06", "Brook Trout"),
                ],
                **doe,
            )
        ],
    )
    (n,) = _diff(before, after)
    assert n.title == "Doe River: scheduled, week of Dec 6"
    assert n.body == (
        "TWRA lists Brook Trout and Rainbow Trout at Doe River for the week of Sunday, "
        "December 6, 2026; TWRA says a week-of stocking falls within five days after "
        "that Sunday. Scheduled, not confirmed: TWRA says any stocking could be "
        "postponed or cancelled."
    )


def test_a_tbd_month_and_month_letters_never_notify():
    doe = dict(
        wid="tn-carter-doe-river",
        name="Doe River",
        site_path="/tn/water/doe-river-carter-county/",
    )
    before = _snap([TN], [_water("TN", [], **doe)])
    after = _snap(
        [TN], [_water("TN", [_plant("month", "2026-12-01", "Rainbow Trout")], **doe)]
    )
    assert _diff(before, after) == []
    lettered = _snap([TN], [_water("TN", [], months_note="M, A, M, J", **doe)])
    assert _diff(before, lettered) == []
    # The control: a day in the same water does notify.
    dated = _snap(
        [TN], [_water("TN", [_plant("day", "2026-12-03", "Rainbow Trout")], **doe)]
    )
    assert len(_diff(before, dated)) == 1


# ---- what is never a message ---------------------------------------------------


def test_no_change_sends_nothing_and_the_check_would_see_a_change():
    before = _snap([CA], [_water("CA", [WEEK_A, WEEK_B])])
    after = json.loads(json.dumps(before))
    assert _diff(before, after) == []
    # Negative control: the same differ sees one added week.
    after["waters"][0]["plants"].append(WEEK_C)
    assert after != before
    assert len(_diff(before, after)) == 1


def test_no_previous_snapshot_sends_nothing():
    after = _snap([CA], [_water("CA", [WEEK_A, WEEK_B, WEEK_C])])
    assert _diff(None, after) == []
    # The control: with an empty-but-present previous snapshot of the same
    # water, the weeks would be news.
    assert len(_diff(_snap([CA], [_water("CA", [])]), after)) == 1


def test_a_past_week_is_history_not_news():
    old = _plant("week", "2026-10-25")  # ended 2026-10-31, before the current week
    before = _snap([CA], [_water("CA", [old, WEEK_A])])
    after = _snap(
        [CA], [_water("CA", [_plant("week", "2026-10-25", status="removed"), WEEK_A])]
    )
    assert _diff(before, after) == []
    # The current week itself still counts: it ends after the floor.
    gone_now = _snap(
        [CA], [_water("CA", [old, _plant("week", "2026-11-08", status="removed")])]
    )
    assert len(_diff(before, gone_now)) == 1


def test_a_water_new_to_the_snapshot_or_gone_from_it_is_not_a_change():
    before = _snap([CA], [_water("CA", [WEEK_A])])
    newcomer = _water(
        "CA", [WEEK_B], wid="cdfw-777", name="New Pond", site_path="/water/new-pond/"
    )
    assert _diff(before, _snap([CA], [_water("CA", [WEEK_A]), newcomer])) == []
    # Gone (DECISIONS 0017: CDFW no longer lists it; not a removal).
    assert _diff(before, _snap([CA], [])) == []


def test_report_and_plan_states_never_notify():
    ma = _water("MA", [], wid="ma-x-pond", name="X Pond", site_path="/ma/water/x-pond/")
    ma_after = _water(
        "MA", [_plant("day", "2026-11-10", "Rainbow Trout", status="reported")],
        wid="ma-x-pond", name="X Pond", site_path="/ma/water/x-pond/",
    )  # fmt: skip
    assert _diff(_snap([MA], [ma]), _snap([MA], [ma_after])) == []
    ny = _water(
        "NY", [], wid="ny-y-creek", name="Y Creek", site_path="/ny/water/y-creek/"
    )
    ny_after = _water(
        "NY", [_plant("approximate", "2027-04-15", "Brown Trout")],
        wid="ny-y-creek", name="Y Creek", site_path="/ny/water/y-creek/",
    )  # fmt: skip
    assert _diff(_snap([NY], [ny]), _snap([NY], [ny_after])) == []
    assert not push.has_push(MA) and not push.has_push(NY)
    assert push.has_push(CA) and push.has_push(TN)


# ---- the words ------------------------------------------------------------------


def _every_message() -> list[push.Notification]:
    doe = dict(
        wid="tn-carter-doe-river",
        name="Doe River",
        site_path="/tn/water/doe-river-carter-county/",
    )
    cases = [
        (_snap([CA], [_water("CA", [WEEK_A])]), _snap([CA], [_water("CA", [WEEK_A, WEEK_B])])),
        (_snap([CA], [_water("CA", [WEEK_A, WEEK_B])]), _snap([CA], [_water("CA", [WEEK_A])])),
        (_snap([CA], [_water("CA", [WEEK_B])]), _snap([CA], [_water("CA", [WEEK_C])])),
        (_snap([CA], [_water("CA", [WEEK_A])]), _snap([CA], [_water("CA", [WEEK_B, WEEK_C])])),
        (_snap([TN], [_water("TN", [], **doe)]), _snap([TN], [_water("TN", [_plant("day", "2026-12-03", "Rainbow Trout")], **doe)])),
        (_snap([TN], [_water("TN", [], **doe)]), _snap([TN], [_water("TN", [_plant("week", "2026-12-06", "Rainbow Trout")], **doe)])),
        (_snap([TN], [_water("TN", [_plant("day", "2026-12-03", "Rainbow Trout")], **doe)]), _snap([TN], [_water("TN", [], **doe)])),
        (_snap([TN], [_water("TN", [_plant("day", "2026-12-03", "Rainbow Trout")], **doe)]), _snap([TN], [_water("TN", [_plant("day", "2026-12-10", "Rainbow Trout")], **doe)])),
    ]  # fmt: skip
    out = []
    for before, after in cases:
        got = _diff(before, after)
        assert len(got) == 1
        out += got
    return out


def test_every_message_says_scheduled_credits_the_agency_and_never_a_banned_word():
    for n in _every_message():
        text = f"{n.title} {n.body}"
        assert not BANNED.search(text), text
        agency = "CDFW" if n.state == "CA" else "TWRA"
        assert agency in n.body
        assert "Scheduled, not confirmed" in n.body or "plans can change" in n.body
        assert n.url.startswith(BASE + "/")
        assert len(n.title) <= 200 and len(n.body) <= 600


def test_the_banned_word_check_is_not_vacuous():
    assert BANNED.search("Shadow Cliff Lake stocked on 2026-11-15")
    assert BANNED.search("the first alert")
    assert not BANNED.search("CDFW lists it for planting the week of Sunday")


# ---- the settings ---------------------------------------------------------------


def _key() -> str:
    return base64.urlsafe_b64encode(b"\x04" + b"\x07" * 64).decode().rstrip("=")


def test_a_valid_config_and_both_empty_is_off():
    cfg = push.push_config_or_none("https://abc.lambda-url.us-east-1.on.aws/", _key())
    assert cfg == push.PushConfig(
        api_url="https://abc.lambda-url.us-east-1.on.aws", vapid_public_key=_key()
    )
    assert cfg.to_template() == {
        "api_url": "https://abc.lambda-url.us-east-1.on.aws",
        "vapid_public_key": _key(),
    }
    assert push.push_config_or_none("", "") is None
    assert push.push_config_or_none(None, None) is None
    assert push.push_config_or_none("  ", None) is None


@pytest.mark.parametrize(
    ("api", "key"),
    [
        ("https://abc.lambda-url.us-east-1.on.aws", ""),
        ("", "B" + "A" * 86),
        ("http://abc.lambda-url.us-east-1.on.aws", "B" + "A" * 86),
        ("https://abc.lambda-url.us-east-1.on.aws/?x=1", "B" + "A" * 86),
        ("https://localhost", "B" + "A" * 86),
        ("https://abc.lambda-url.us-east-1.on.aws", "short"),
        ("https://abc.lambda-url.us-east-1.on.aws", "B" + "A" * 85 + "="),
        # 87 chars that decode to a compressed point (0x02 first), not 0x04
        (
            "https://abc.lambda-url.us-east-1.on.aws",
            base64.urlsafe_b64encode(b"\x02" + b"\x07" * 64).decode().rstrip("="),
        ),
    ],
)
def test_a_half_or_malformed_config_is_refused(api: str, key: str):
    with pytest.raises(ValueError):
        push.push_config_or_none(api, key)


# ---- the two workflow commands -------------------------------------------------


def _write(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_diff_command_writes_the_events_file(tmp_path: Path, capsys):
    before = _write(tmp_path / "before.json", _snap([CA], [_water("CA", [WEEK_A])]))
    after = _write(
        tmp_path / "after.json", _snap([CA], [_water("CA", [WEEK_A, WEEK_B])])
    )
    out = tmp_path / "events.json"
    rc = push.main(
        [
            "diff",
            "--before",
            str(before),
            "--after",
            str(after),
            "--base-url",
            BASE,
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    events = json.loads(out.read_text("utf-8"))["events"]
    assert [e["water_id"] for e in events] == ["cdfw-123"]
    assert "1 water with a schedule change" in capsys.readouterr().out


@respx.mock
def test_diff_command_reads_the_live_snapshot_and_sends_nothing_when_it_cannot(
    tmp_path: Path, capsys
):
    after = _write(
        tmp_path / "after.json", _snap([CA], [_water("CA", [WEEK_A, WEEK_B])])
    )
    out = tmp_path / "events.json"
    live = respx.get(f"{BASE}/snapshot/v2.json")
    live.mock(
        return_value=httpx.Response(200, json=_snap([CA], [_water("CA", [WEEK_A])]))
    )
    rc = push.main(
        [
            "diff",
            "--before-url",
            f"{BASE}/snapshot/v2.json",
            "--after",
            str(after),
            "--base-url",
            BASE,
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    assert len(json.loads(out.read_text("utf-8"))["events"]) == 1
    # Unreadable: a 503, then a body that is not a snapshot, then a network error.
    for response in (
        httpx.Response(503),
        httpx.Response(200, json={"not": "a snapshot"}),
    ):
        live.mock(return_value=response)
        rc = push.main(
            [
                "diff",
                "--before-url",
                f"{BASE}/snapshot/v2.json",
                "--after",
                str(after),
                "--base-url",
                BASE,
                "--out",
                str(out),
            ]
        )
        assert rc == 0
        assert json.loads(out.read_text("utf-8"))["events"] == []
        assert "could not be read" in capsys.readouterr().out
    live.mock(side_effect=httpx.ConnectError("no route"))
    assert push.fetch_live_snapshot(f"{BASE}/snapshot/v2.json") is None


def test_send_command_skips_an_empty_events_file_without_calling_anyone(
    tmp_path: Path, monkeypatch, capsys
):
    events = _write(tmp_path / "events.json", {"events": []})

    def never(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("send_events must not be called with nothing to send")

    monkeypatch.setattr(push, "send_events", never)
    monkeypatch.setenv(push.SENDER_AUTH_VARIABLE, "x" * 48)
    assert (
        push.main(
            [
                "send",
                "--events",
                str(events),
                "--api-url",
                "https://abc.lambda-url.us-east-1.on.aws",
            ]
        )
        == 0
    )
    assert "nothing to send" in capsys.readouterr().out


def test_send_command_needs_the_token_and_reports_the_services_counts(
    tmp_path: Path, monkeypatch, capsys
):
    (n,) = _diff(
        _snap([CA], [_water("CA", [WEEK_A])]),
        _snap([CA], [_water("CA", [WEEK_A, WEEK_B])]),
    )
    events = _write(tmp_path / "events.json", {"events": [n.to_json()]})
    monkeypatch.delenv(push.SENDER_AUTH_VARIABLE, raising=False)
    assert (
        push.main(
            [
                "send",
                "--events",
                str(events),
                "--api-url",
                "https://abc.lambda-url.us-east-1.on.aws",
            ]
        )
        == 1
    )
    assert push.SENDER_AUTH_VARIABLE in capsys.readouterr().err

    seen: dict[str, Any] = {}

    def fake(
        evs: list[dict[str, str]], *, api_url: str, token: str, timeout: float = 60.0
    ) -> dict[str, Any]:
        seen.update(events=evs, api_url=api_url, token=token)
        return {"events": 1, "subscribers": 3, "sent": 2, "failed": 0, "removed": 1}

    monkeypatch.setattr(push, "send_events", fake)
    monkeypatch.setenv(push.SENDER_AUTH_VARIABLE, "x" * 48)
    assert (
        push.main(
            [
                "send",
                "--events",
                str(events),
                "--api-url",
                "https://abc.lambda-url.us-east-1.on.aws",
            ]
        )
        == 0
    )
    assert seen["events"] == [n.to_json()]
    assert seen["token"] == "x" * 48
    assert (
        "1 events, 3 subscriptions, 2 sent, 0 failed, 1 dead endpoints removed"
        in capsys.readouterr().out
    )


@respx.mock
def test_send_events_posts_a_bearer_token_and_fails_loudly_on_an_error():
    api = "https://abc.lambda-url.us-east-1.on.aws"
    route = respx.post(f"{api}/send").mock(
        return_value=httpx.Response(200, json={"sent": 1})
    )
    result = push.send_events(
        [{"water_id": "cdfw-1"}], api_url=api + "/", token="tok" * 16
    )
    assert result == {"sent": 1}
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer " + "tok" * 16
    assert json.loads(request.content) == {"events": [{"water_id": "cdfw-1"}]}
    route.mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
    with pytest.raises(httpx.HTTPStatusError):
        push.send_events([{"water_id": "cdfw-1"}], api_url=api, token="tok" * 16)


@respx.mock
def test_send_events_splits_a_big_run_into_calls_the_service_accepts():
    api = "https://abc.lambda-url.us-east-1.on.aws"
    route = respx.post(f"{api}/send").mock(
        side_effect=lambda request: httpx.Response(
            200, json={"events": len(json.loads(request.content)["events"]), "sent": 2}
        )
    )
    events = [{"water_id": f"cdfw-{i}"} for i in range(push.EVENTS_PER_CALL * 2 + 1)]
    result = push.send_events(events, api_url=api, token="tok" * 16)
    assert route.call_count == 3
    assert result == {"events": len(events), "sent": 6}
