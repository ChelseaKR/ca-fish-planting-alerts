"""The web push control on the built site (DECISIONS 0069).

With a push config the calendar box of every California and Tennessee water
page carries the "Alert me about this water" control, the site root the
service worker and the manifest, and the privacy page its section. Without
one, none of that exists. The page script's policy (which one view the box
shows) runs under node for an iPhone in a Safari tab, an iPhone web app, an
Android browser, a blocked permission and a browser with no Push API.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from markupsafe import escape as html_escape

from cfpa import cli, push, site

FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "states"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
API = "https://abc.lambda-url.us-east-1.on.aws"
KEY = base64.urlsafe_b64encode(b"\x04" + b"\x07" * 64).decode().rstrip("=")
GA4_ID = "G-TEST12345"
BUTTON = "Alert me about this water"
STOP = "Stop these notifications"
# The box's visible words follow the pages' rules: no superlatives, no
# "stocked", and no phone platform other than Apple's (test_site_app_store).
BANNED = re.compile(
    r"\b(stocked|planted on|only|first|best|guarantee\w*|android)\b", re.I
)
_TAGS = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script\b[^>]*>", re.I | re.S)


def _build(root: Path, *, push_on: bool, ga4: bool = True) -> Path:
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA,
        site_out=root / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=("TN", "MA", "MI"),
        states_fixtures=STATE_FIXTURES,
        ga4_measurement_id=GA4_ID if ga4 else None,
        push=push.PushConfig(api_url=API, vapid_public_key=KEY) if push_on else None,
    )
    return root / "site"


@pytest.fixture(scope="module")
def on(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("push-on"), push_on=True)


@pytest.fixture(scope="module")
def off(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("push-off"), push_on=False)


def _v2(out: Path) -> dict[str, Any]:
    return json.loads((out / "snapshot" / "v2.json").read_text("utf-8"))


def _waters(out: Path, code: str) -> list[dict[str, Any]]:
    return [w for w in _v2(out)["waters"] if w["state"] == code]


def _page(out: Path, w: dict[str, Any]) -> str:
    return (out / w["site_path"].strip("/") / "index.html").read_text("utf-8")


def _pages(out: Path) -> dict[str, str]:
    return {
        str(f.relative_to(out)): f.read_text(encoding="utf-8")
        for f in sorted(out.rglob("*.html"))
    }


def _visible(html: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub(" ", _SCRIPT.sub(" ", html)))


def _box(html: str) -> str:
    m = re.search(
        r'<div class="push-subscribe".*?</div>\s*<script src="[^"]*assets/push\.js" defer></script>',
        html,
        re.S,
    )
    assert m, "no push control"
    return m.group(0)


# ---- where the control is -------------------------------------------------------


def test_every_california_water_page_has_the_control_inside_the_calendar_box(on: Path):
    waters = _waters(on, "CA")
    assert waters
    for w in waters:
        html = _page(on, w)
        box = _box(html)
        # Inside the calendar box: after its two calendar buttons, before its
        # fine print, so it never competes with them for the first screen.
        cal = html.index('<div class="calendar-subscribe"')
        google = html.index('data-ga-type="google"')
        fine = html.index("Other\n    calendar apps", google)
        assert cal < google < html.index('<div class="push-subscribe"') < fine
        assert f'data-push-water="{w["id"]}"' in box
        assert f'data-push-water-name="{html_escape(w["name"])}"' in box
        assert f'data-push-api="{API}"' in box
        assert f'data-push-public="{KEY}"' in box
        assert 'data-push-worker="../../push-worker.js"' in box
        assert 'data-push-scope="../../"' in box
        assert BUTTON in box and STOP in box
        assert (
            'data-ga-event="calendar_subscribe_click" data-ga-placement="water" data-ga-type="push"'
            in box
        )
        assert '<button type="button"' in box
        assert 'href="../../privacy/#push"' in box
        assert "Add to Home\n    Screen" in box
        assert '<link rel="manifest" href="../../manifest.webmanifest">' in html


def test_every_tennessee_water_page_has_it_too_under_twras_name(on: Path):
    waters = _waters(on, "TN")
    assert waters
    for w in waters:
        box = _box(_page(on, w))
        assert f'data-push-water="{w["id"]}"' in box
        assert "TWRA adds, moves or" in box
        assert 'data-ga-placement="state_water" data-ga-type="push"' in box
        assert 'data-push-worker="../../../push-worker.js"' in box


def test_report_states_and_non_water_pages_have_no_control(on: Path):
    for code in ("MA", "MI"):
        waters = _waters(on, code)
        assert waters
        for w in waters:
            assert "push-subscribe" not in _page(on, w)
            assert BUTTON not in _page(on, w)
    for name, html in _pages(on).items():
        if "/water/" in f"/{name}":
            continue
        assert "push-subscribe" not in html, name
        assert BUTTON not in html, name


def test_the_control_is_hidden_until_the_script_runs_and_shows_one_view_at_a_time(
    on: Path,
):
    box = _box(_page(on, _waters(on, "CA")[0]))
    assert box.startswith('<div class="push-subscribe"')
    assert re.search(r'<div class="push-subscribe"[^>]*\shidden>', box)
    views = re.findall(r'data-push-view="([a-z]+)"', box)
    assert views == ["idle", "busy", "on", "ios", "blocked", "unsupported"]
    assert 'role="status" aria-live="polite"' in box


def test_the_boxs_words_follow_the_pages_rules(on: Path):
    for code in ("CA", "TN"):
        for w in _waters(on, code):
            # The water's name is the agency's data, not the box's copy
            # ("Covington First Baptist Church Pond" is a TWRA water).
            text = _visible(_box(_page(on, w))).replace(w["name"], "WATER")
            assert not BANNED.search(text), text
            assert "scheduled, not confirmed" in text
            assert "no account or email address" in text
            assert "One water per browser" in text
    # The check is not vacuous.
    assert BANNED.search("the first and only Android alert, stocked")


# ---- the files ------------------------------------------------------------------


def test_the_script_the_worker_and_the_manifest_are_written_at_their_places(on: Path):
    assert (on / "assets" / "push.js").read_text("utf-8") == (
        site.TEMPLATES_DIR / "push.js"
    ).read_text("utf-8")
    worker = (on / "push-worker.js").read_text("utf-8")
    assert f'var API = "{API}";' in worker
    assert f'var SERVER_PUBLIC = "{KEY}";' in worker
    assert "pushsubscriptionchange" in worker
    assert "showNotification" in worker
    assert 'fetch(API + "/subscribe"' in worker
    manifest = json.loads((on / "manifest.webmanifest").read_text("utf-8"))
    assert manifest == {
        "name": "Trout Truck",
        "short_name": "Trout Truck",
        "display": "standalone",
        "scope": "/ca-fish-planting-alerts/",
    }
    index = (on / "index.html").read_text("utf-8")
    assert '<link rel="manifest" href="./manifest.webmanifest">' in index


def _push_traces(out: Path) -> list[str]:
    traces = [
        path
        for path in ("assets/push.js", "push-worker.js", "manifest.webmanifest")
        if (out / path).exists()
    ]
    for name, html in _pages(out).items():
        for marker in ("push-subscribe", "manifest.webmanifest", BUTTON, 'id="push"'):
            if marker in html:
                traces.append(f"{name}: {marker}")
    return traces


def test_without_a_config_nothing_of_it_exists(off: Path, on: Path):
    assert _push_traces(off) == []
    # The negative control: the same detector finds every trace on the on build.
    found = _push_traces(on)
    assert "push-worker.js" in found and "manifest.webmanifest" in found
    assert any(t.endswith(BUTTON) for t in found)
    assert any(t.endswith('id="push"') for t in found)


# ---- the privacy page -------------------------------------------------------------


def test_the_privacy_page_says_what_is_stored_where_and_how_to_stop(on: Path):
    html = (on / "privacy" / "index.html").read_text("utf-8")
    text = _visible(html)
    assert '<h2 id="push">Web push notifications</h2>' in html
    assert f"<code>{API}</code>" in html
    # The templates write HTML entities, which the build keeps as they are.
    for phrase in (
        "subscription&rsquo;s address",
        "two encryption keys",
        "the water you chose",
        "when you subscribed and when the last notification was sent",
        "no account, no name, no email address",
        "IP address; the service does not keep it",
        "Stop these notifications",
        "deleted the next time a message to it fails",
        "about 13 months",
        "utm_source=web-push",
        "calendar-subscribe click of type &ldquo;push&rdquo;",
    ):
        assert phrase in text, phrase
    assert "Last updated 2026-11-08" in text
    assert "which asks for neither" in text
    # The section this change adds never says "no tracking" (the apps' lede
    # on this page still does; #144 owns that line and removes the phrase).
    assert "no tracking" not in _push_section(html).lower()
    assert "no tracking" not in _website_section(html).lower()


def _push_section(html: str) -> str:
    start = html.index('<h2 id="push">')
    return _visible(html[start : html.index('<h2 id="location">', start)])


def _website_section(html: str) -> str:
    start = html.index('<h2 id="site">')
    end = (
        html.index('<h2 id="push">')
        if '<h2 id="push">' in html
        else html.index('<h2 id="location">')
    )
    return _visible(html[start:end])


def test_the_privacy_page_without_push_is_as_before(off: Path):
    html = (off / "privacy" / "index.html").read_text("utf-8")
    text = _visible(html)
    assert 'id="push"' not in html
    assert "Last updated 2026-11-04" in text
    assert "no sign-up, anywhere on this site." in text
    assert "no tracking" not in _website_section(html).lower()


def test_privacy_copy_without_analytics_still_describes_push(tmp_path: Path):
    out = _build(tmp_path, push_on=True, ga4=False)
    html = (out / "privacy" / "index.html").read_text("utf-8")
    text = _visible(html)
    assert "this site has no analytics, so nothing reads them" in text
    assert "except the request this site makes to its own notification service" in text
    assert "no tracking" not in _push_section(html).lower()
    assert "no tracking" not in _website_section(html).lower()


# ---- the GA4 tag ------------------------------------------------------------------

_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const [script, casePath] = process.argv.slice(2);
const code = fs.readFileSync(script, "utf8");
const c = JSON.parse(fs.readFileSync(casePath, "utf8"));
const clicks = [];
const window = {};
const document = {
  createElement: (tag) => ({ tagName: tag }),
  head: { appendChild: () => {} },
  addEventListener: (type, f) => { if (type === "click") clicks.push(f); },
};
const context = { navigator: {}, window, document, Date, encodeURIComponent };
vm.runInContext(code, vm.createContext(context));
const el = {
  getAttribute: (name) => c.attrs[name] === undefined ? null : c.attrs[name],
  hostname: c.hostname,
};
// A <button>: it matches "[data-ga-event]" but never "a[data-ga-event]".
const target = { closest: (sel) => (sel === "[data-ga-event]" || (c.isLink && sel === "a[data-ga-event]") ? el : null) };
clicks.forEach((f) => f({ target }));
const events = (window.dataLayer || []).map((a) => Array.from(a)).filter((a) => a[0] === "event");
process.stdout.write(JSON.stringify(events));
"""


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI")
        pytest.skip("node is not installed")
    return node


def _tag_js(out: Path) -> str:
    html = (out / "index.html").read_text("utf-8")
    scripts = [
        body
        for opening, body in re.findall(
            r"(<script\b[^>]*>)(.*?)</script\b[^>]*>", html, re.I | re.S
        )
        if "ld+json" not in opening and "src=" not in opening
    ]
    assert len(scripts) == 1
    return scripts[0]


def _run_click(
    tmp_path: Path, js: str, attrs: dict[str, str], hostname: str | None
) -> list[list[Any]]:
    harness = tmp_path / "harness.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    script = tmp_path / "tag.js"
    script.write_text(js, encoding="utf-8")
    case = tmp_path / "case.json"
    case.write_text(
        json.dumps(
            {"attrs": attrs, "hostname": hostname, "isLink": hostname is not None}
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [_node(), str(harness), str(script), str(case)],
        capture_output=True, text=True, check=True, timeout=30,
    )  # fmt: skip
    parsed: list[list[Any]] = json.loads(result.stdout)
    return parsed


def test_the_tag_counts_the_push_button_as_a_calendar_subscribe_click_with_no_host(
    tmp_path: Path, on: Path
):
    js = _tag_js(on)
    assert 't.closest("[data-ga-event]")' in js
    button = {
        "data-ga-event": "calendar_subscribe_click",
        "data-ga-placement": "water",
        "data-ga-type": "push",
    }
    events = _run_click(tmp_path, js, button, hostname=None)
    assert events == [
        [
            "event",
            "calendar_subscribe_click",
            {"placement": "water", "link_type": "push"},
        ]
    ]
    # A link still reports its host, as before.
    link = {**button, "data-ga-type": "ics"}
    events = _run_click(tmp_path, js, link, hostname="example.invalid")
    assert events == [
        [
            "event",
            "calendar_subscribe_click",
            {"placement": "water", "link_type": "ics", "link_host": "example.invalid"},
        ]
    ]
    # The control: a tag with the old anchor-only selector ignores the button.
    old = js.replace('t.closest("[data-ga-event]")', 't.closest("a[data-ga-event]")', 1)
    assert old != js
    assert _run_click(tmp_path, old, button, hostname=None) == []


# ---- the page script's policy, under node ---------------------------------------

_DECIDE = r"""
const m = require(process.argv[2]);
const cases = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
process.stdout.write(JSON.stringify(cases.map((c) => m.decide(c))));
"""

IOS_SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
ANDROID_CHROME = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Mobile Safari/537.36"
)
DESKTOP_FIREFOX = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:130.0) Gecko/20100101 Firefox/130.0"


def _base(**over: Any) -> dict[str, Any]:
    env = {
        "userAgent": ANDROID_CHROME, "platform": "Linux armv81", "maxTouchPoints": 5,
        "standalone": False, "secureContext": True, "serviceWorker": True,
        "pushManager": True, "notification": True, "permission": "default",
        "saved": None, "waterId": "cdfw-123",
    }  # fmt: skip
    env.update(over)
    return env


def _decide(tmp_path: Path, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runner = tmp_path / "decide.js"
    runner.write_text(_DECIDE, encoding="utf-8")
    case = tmp_path / "cases.json"
    case.write_text(json.dumps(cases), encoding="utf-8")
    result = subprocess.run(
        [_node(), str(runner), str(site.TEMPLATES_DIR / "push.js"), str(case)],
        capture_output=True, text=True, check=True, timeout=30,
    )  # fmt: skip
    parsed: list[dict[str, Any]] = json.loads(result.stdout)
    return parsed


def test_an_iphone_in_a_safari_tab_gets_the_two_step_instruction_not_a_button(
    tmp_path: Path,
):
    # In a tab, iOS Safari has no Push API at all; the same iPhone as a Home
    # Screen web app has it and gets the button.
    tab = _base(
        userAgent=IOS_SAFARI, platform="iPhone", standalone=False, pushManager=False
    )
    web_app = _base(userAgent=IOS_SAFARI, platform="iPhone", standalone=True)
    ipad = _base(userAgent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
                 platform="MacIntel", maxTouchPoints=5, standalone=False, pushManager=False)  # fmt: skip
    mac = _base(userAgent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Safari/605.1.15",
                platform="MacIntel", maxTouchPoints=0, standalone=False)  # fmt: skip
    got = _decide(tmp_path, [tab, web_app, ipad, mac])
    assert [g["view"] for g in got] == ["ios", "idle", "ios", "idle"]


def test_the_other_views(tmp_path: Path):
    cases = [
        _base(),
        _base(permission="denied"),
        _base(
            userAgent=DESKTOP_FIREFOX,
            platform="MacIntel",
            maxTouchPoints=0,
            pushManager=False,
        ),
        _base(secureContext=False),
        _base(
            saved={
                "water_id": "cdfw-123",
                "water_name": "Shadow Cliff Lake",
                "endpoint": "e",
            }
        ),
        _base(
            saved={"water_id": "cdfw-999", "water_name": "Other Lake", "endpoint": "e"}
        ),
        _base(permission="granted"),
    ]
    got = _decide(tmp_path, cases)
    assert [g["view"] for g in got] == [
        "idle",
        "blocked",
        "unsupported",
        "unsupported",
        "on",
        "idle",
        "idle",
    ]
    assert got[5]["otherName"] == "Other Lake"
    assert "otherName" not in got[0]


# ---- the CLI --------------------------------------------------------------------


def _argv(root: Path) -> list[str]:
    return [
        "--fixture", str(FRESH),
        "--fixture-fetched-at", "2026-09-13T12:00:00Z",
        "--run-today", "2026-09-13",
        "--history", str(root / "history.json"),
        "--aliases", str(root / "aliases.json"),
        "--site-out", str(root / "site"),
        "--base-url", BASE,
    ]  # fmt: skip


def test_cli_main_builds_the_control_from_the_two_flags(tmp_path: Path):
    assert (
        cli.main(
            [
                *_argv(tmp_path),
                "--push-api-url",
                API + "/",
                "--push-vapid-public-key",
                KEY,
            ]
        )
        == 0
    )
    assert (tmp_path / "site" / "push-worker.js").exists()
    water_pages = list((tmp_path / "site" / "water").glob("*/index.html"))
    assert water_pages
    assert all(BUTTON in p.read_text("utf-8") for p in water_pages)


@pytest.mark.parametrize(
    "flags",
    [
        ["--push-api-url", API],
        ["--push-vapid-public-key", KEY],
        [
            "--push-api-url",
            "http://abc.lambda-url.us-east-1.on.aws",
            "--push-vapid-public-key",
            KEY,
        ],
        ["--push-api-url", API, "--push-vapid-public-key", "not-a-key"],
    ],
)
def test_cli_main_refuses_a_half_or_bad_config_before_writing_anything(
    tmp_path: Path, flags: list[str], capsys
):
    assert cli.main([*_argv(tmp_path), *flags]) == 1
    assert not (tmp_path / "site").exists()
    assert "PUSH_" in capsys.readouterr().err


def test_cli_main_with_both_flags_empty_builds_without_push(tmp_path: Path):
    assert (
        cli.main(
            [*_argv(tmp_path), "--push-api-url", "", "--push-vapid-public-key", ""]
        )
        == 0
    )
    assert not (tmp_path / "site" / "push-worker.js").exists()


# ---- the publish job's secret scan ----------------------------------------------


def _gitleaks(path: Path) -> int:
    gitleaks = shutil.which("gitleaks")
    if gitleaks is None:
        if os.environ.get("CI"):
            pytest.fail("gitleaks is required in CI")
        pytest.skip("gitleaks is not installed")
    return subprocess.run(
        [gitleaks, "dir", str(path), "--redact", "--no-banner", "--exit-code", "1"],
        capture_output=True,
        check=False,
        timeout=120,
    ).returncode


def test_a_real_looking_public_key_passes_the_publish_jobs_gitleaks_scan(
    tmp_path: Path,
):
    """publish.yml runs `gitleaks dir site` before it deploys, so a build the
    scan flags would stop every publish. The fixture key above is too regular
    to trip it; this one has a real key's entropy."""
    raw = b"\x04" + hashlib.sha512(b"trout truck test only").digest()
    key = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    built = tmp_path / "site"
    built.mkdir()
    env = site._env()
    config = push.PushConfig(api_url=API, vapid_public_key=key)
    site._write_push_files(env, built, [], push=config, base_url=BASE)
    water = env.get_template("_push_subscribe.html.jinja").render(
        push=config.to_template(),
        push_water_id="cdfw-123",
        water={"name": "Shadow Cliff Lake"},
        root="../../",
        site_name="Trout Truck",
        cal_agency="CDFW",
        cal_placement="water",
    )
    assert key in water
    (built / "water.html").write_text(water, encoding="utf-8")
    assert _gitleaks(built) == 0
    # The control: the name this replaced, on the same value, is a finding.
    sabotaged = water.replace("data-push-public=", "data-push-key=")
    assert sabotaged != water
    (built / "water.html").write_text(sabotaged, encoding="utf-8")
    assert _gitleaks(built) == 1


# ---- the about page ---------------------------------------------------------------


def test_the_about_page_says_what_push_changes_only_when_it_is_on(
    tmp_path: Path, on: Path, off: Path
):
    with_ga = _visible((on / "about" / "index.html").read_text("utf-8"))
    assert "apart from the optional web push notification" in with_ga
    assert "apart from" not in _visible(
        (off / "about" / "index.html").read_text("utf-8")
    )
    no_ga = _visible(
        (_build(tmp_path, push_on=True, ga4=False) / "about" / "index.html").read_text(
            "utf-8"
        )
    )
    assert "except the web push control's call" in no_ga
    assert "The one script" not in no_ga


def test_publish_workflow_passes_the_two_variables():
    wf = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "publish.yml"
    ).read_text("utf-8")
    assert "PUSH_API_URL: ${{ vars.PUSH_API_URL }}" in wf
    assert "PUSH_VAPID_PUBLIC_KEY: ${{ vars.PUSH_VAPID_PUBLIC_KEY }}" in wf
    assert '--push-api-url "$PUSH_API_URL"' in wf
    assert '--push-vapid-public-key "$PUSH_VAPID_PUBLIC_KEY"' in wf
