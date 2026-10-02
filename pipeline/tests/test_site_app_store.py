"""The App Store launch switch (site.py APP_STORE_LIVE).

Off (the default, and production until Apple approves the app): no Smart App
Banner tag, no badge, no badge file, no extra CSS, and no App Store link
anywhere. On: every page carries ``<meta name="apple-itunes-app">`` with the
app's ID, and the home and support pages carry Apple's badge linking to the
app's US listing, with accurate price copy.

Every negative control asserts that its sabotage changed the input before it
asserts that the check caught it; a sabotage that silently no-ops would
otherwise read as a pass.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"

APP_ID = "6818637427"
APP_URL = "https://apps.apple.com/us/app/id6818637427"
BANNER = f'<meta name="apple-itunes-app" content="app-id={APP_ID}">'
BADGE_ALT = 'alt="Download on the App Store"'
PRICE_COPY = "For iPhone. Free on the App Store; optional $9.99 Full Access."
# The vendored file, byte for byte as Apple's marketing tools served it on
# 2026-10-02 (site.py APP_STORE_BADGE_FILE). A changed hash means the artwork
# was edited, which Apple's guidelines forbid.
BADGE_SHA256 = "a26fc5b38380272c92e9019a2eb8b45542a66814b3e2b203772db8904b9fb99f"

# Anything that only exists when the switch is on.
LIVE_MARKERS = (
    "apple-itunes-app",
    "app-store-badge",
    "app-store-cta",
    "app_store_badge_click",
    "apps.apple.com",
    "Download on the App Store",
)


def _build(root: Path, **extra) -> Path:
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
        **extra,
    )
    return out


def _main_argv(root: Path, *extra: str) -> list[str]:
    return [
        "--fixture", str(FRESH),
        "--fixture-fetched-at", "2026-09-13T12:00:00Z",
        "--run-today", "2026-09-13",
        "--history", str(root / "history.json"),
        "--aliases", str(root / "aliases.json"),
        "--site-out", str(root / "site"),
        "--base-url", BASE_URL,
        *extra,
    ]  # fmt: skip


def _pages(out: Path) -> dict[str, str]:
    pages = {
        str(f.relative_to(out)): f.read_text(encoding="utf-8")
        for f in sorted(out.rglob("*.html"))
    }
    assert len(pages) > 10, sorted(pages)
    return pages


def _off_problems(out: Path) -> list[str]:
    """Everything that would make an off build differ from the pre-switch one."""
    problems = []
    for name, html in _pages(out).items():
        for marker in LIVE_MARKERS:
            if marker in html:
                problems.append(f"{name}: {marker}")
    if (out / "assets" / site.APP_STORE_BADGE_FILE).exists():
        problems.append("badge file written")
    css = (out / "assets" / "style.css").read_text(encoding="utf-8")
    if css != (site.TEMPLATES_DIR / "style.css").read_text(encoding="utf-8"):
        problems.append("style.css differs from the template")
    return problems


_BADGE_LINK = re.compile(
    r'<a class="app-store-badge" href="([^"]+)" data-app-store-badge="([a-z]+)">'
    r'<img src="([^"]+)" width="120" height="40" alt="Download on the App Store"></a>'
)


def _banner_problems(pages: dict[str, str]) -> list[str]:
    problems = []
    for name, html in pages.items():
        if html.count(BANNER) != 1:
            problems.append(f"{name}: banner tag count {html.count(BANNER)}")
        elif BANNER not in html.split("</head>", 1)[0]:
            problems.append(f"{name}: banner tag not in <head>")
    return problems


def _badge_problems(pages: dict[str, str]) -> list[str]:
    problems = []
    expected = {"index.html": ("home", "./"), "support/index.html": ("support", "../")}
    for name, html in pages.items():
        links = _BADGE_LINK.findall(html)
        if name not in expected:
            if links:
                problems.append(f"{name}: badge on a page it does not belong on")
            continue
        placement, root = expected[name]
        if links != [(APP_URL, placement, f"{root}assets/app-store-badge.svg")]:
            problems.append(f"{name}: badge link {links!r}")
        if PRICE_COPY not in html:
            problems.append(f"{name}: price copy missing")
    return problems


def _on_problems(out: Path) -> list[str]:
    """What a live build must carry, page by page, plus its assets."""
    pages = _pages(out)
    problems = _banner_problems(pages) + _badge_problems(pages)
    badge = out / "assets" / site.APP_STORE_BADGE_FILE
    if not badge.exists():
        problems.append("badge file missing")
    elif hashlib.sha256(badge.read_bytes()).hexdigest() != BADGE_SHA256:
        problems.append("badge file is not Apple's artwork byte for byte")
    css = (out / "assets" / "style.css").read_text(encoding="utf-8")
    if ".app-store-badge" not in css:
        problems.append("badge CSS missing")
    return problems


# ---- the switch's parser


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("false", False),
        ("FALSE", False),
        (" false ", False),
        ("true", True),
        ("True", True),
        (" true\n", True),
    ],
)
def test_switch_values(value, expected):
    assert site.app_store_live_or_false(value) is expected


@pytest.mark.parametrize("value", ["ture", "yes", "1", "on", "true false"])
def test_switch_refuses_anything_else(value):
    with pytest.raises(ValueError, match="APP_STORE_LIVE"):
        site.app_store_live_or_false(value)


def test_constants_name_the_real_listing():
    assert site.APP_STORE_ID == APP_ID
    assert site.APP_STORE_CANONICAL_URL == APP_URL


# ---- off


def test_off_by_default_adds_nothing(tmp_path):
    assert _off_problems(_build(tmp_path)) == []


@pytest.mark.parametrize("value", [None, "", "false"])
def test_off_through_the_production_entry_point(tmp_path, value):
    extra = () if value is None else ("--app-store-live", value)
    assert cli.main(_main_argv(tmp_path, *extra)) == 0
    assert _off_problems(tmp_path / "site") == []


def test_off_build_is_identical_to_a_build_without_the_argument(tmp_path):
    """The switch off and the switch absent produce the same files, byte for
    byte, apart from nothing: both runs use the same fixture and clock."""
    a = _build(tmp_path / "a")
    b = _build(tmp_path / "b", app_store_live=False)
    files_a = {p.relative_to(a): p for p in a.rglob("*") if p.is_file()}
    files_b = {p.relative_to(b): p for p in b.rglob("*") if p.is_file()}
    assert sorted(files_a) == sorted(files_b)
    noisy = {Path("snapshot/v1.json"), Path("index.html"), Path("about/index.html")}
    for rel, path in files_a.items():
        if rel in noisy:
            continue  # carry generated_at, which is the wall clock
        assert path.read_bytes() == files_b[rel].read_bytes(), rel


# ---- on


def test_on_adds_banner_everywhere_and_badge_on_home_and_support(tmp_path):
    out = _build(tmp_path, app_store_live=True)
    assert _on_problems(out) == []


def test_on_through_the_production_entry_point(tmp_path):
    assert cli.main(_main_argv(tmp_path, "--app-store-live", "true")) == 0
    assert _on_problems(tmp_path / "site") == []


def test_on_respects_an_explicit_app_store_url(tmp_path):
    other = "https://apps.apple.com/us/app/trout-truck/id6818637427"
    out = _build(tmp_path, app_store_live=True, app_store_url=other)
    index = (out / "index.html").read_text(encoding="utf-8")
    assert f'class="app-store-badge" href="{other}"' in index
    assert BANNER in index


def test_bad_switch_value_refuses_the_run_and_writes_nothing(tmp_path, capsys):
    assert cli.main(_main_argv(tmp_path, "--app-store-live", "ture")) == 1
    assert not (tmp_path / "site").exists()
    assert "APP_STORE_LIVE" in capsys.readouterr().err


def test_copy_never_mentions_android(tmp_path):
    out = _build(tmp_path, app_store_live=True)
    for name, html in _pages(out).items():
        assert "android" not in html.lower(), name
        assert "google play" not in html.lower(), name


def test_publish_workflow_passes_the_repository_variable():
    wf = (REPO_ROOT / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )
    assert "APP_STORE_LIVE: ${{ vars.APP_STORE_LIVE }}" in wf
    assert '--app-store-live "$APP_STORE_LIVE"' in wf


# ---- negative controls: the checks above can fail


def test_negative_control_off_check_catches_a_live_build(tmp_path):
    out = _build(tmp_path, app_store_live=True)
    problems = _off_problems(out)
    assert any("apple-itunes-app" in p for p in problems)
    assert "badge file written" in problems
    assert "style.css differs from the template" in problems


def test_negative_control_on_check_catches_an_off_build(tmp_path):
    problems = _on_problems(_build(tmp_path))
    assert "badge file missing" in problems
    assert any("banner tag count 0" in p for p in problems)


def test_negative_control_on_check_catches_a_wrong_app_id(tmp_path, monkeypatch):
    monkeypatch.setattr(site, "APP_STORE_ID", "6818637465")  # Queer Frame's
    assert site.APP_STORE_ID != APP_ID  # the sabotage landed
    out = _build(tmp_path, app_store_live=True)
    assert any("banner tag count 0" in p for p in _on_problems(out))


def test_negative_control_on_check_catches_an_edited_badge(tmp_path):
    out = _build(tmp_path, app_store_live=True)
    badge = out / "assets" / site.APP_STORE_BADGE_FILE
    original = badge.read_bytes()
    badge.write_bytes(original.replace(b"#a6a6a6", b"#000000", 1))
    assert badge.read_bytes() != original  # the sabotage landed
    assert "badge file is not Apple's artwork byte for byte" in _on_problems(out)


def test_negative_control_on_check_catches_wrong_price_copy(tmp_path):
    out = _build(tmp_path, app_store_live=True)
    page = out / "support" / "index.html"
    original = page.read_text(encoding="utf-8")
    page.write_text(original.replace("$9.99", "$4.99"), encoding="utf-8")
    assert page.read_text(encoding="utf-8") != original  # the sabotage landed
    assert "support/index.html: price copy missing" in _on_problems(out)


# ---- the GA4 click event, executed under node


_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[2], "utf8");
const c = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const listeners = {};
const anchor = {
  href: "https://apps.apple.com/us/app/id6818637427",
  getAttribute: (k) => (k === "data-app-store-badge" ? "home" : null),
};
const document = {
  addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
  getElementById: () => null,
  createElement: () => ({}),
  head: { appendChild: () => {} },
};
const window = Object.assign({ localStorage: { getItem: () => null } }, c.window);
const navigator = Object.assign({}, c.navigator);
vm.runInContext(code, vm.createContext({ window, navigator, document, Date }));
if (c.disableAfterLoad) window[c.disableAfterLoad] = true;
const img = { closest: (sel) => (sel === "a[data-app-store-badge]" ? anchor : null) };
(listeners.click || []).forEach((f) => f({ target: img }));
const events = (window.dataLayer || [])
  .map((a) => Array.from(a))
  .filter((a) => a[0] === "event");
process.stdout.write(JSON.stringify({ clickListeners: (listeners.click || []).length, events }));
"""

_SCRIPT = re.compile(r"<script>(.*?)</script>", re.DOTALL)


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI to execute the GA4 click event")
        pytest.skip("node is not installed; the click event is only string-checked")
    return node


def _click(tmp_path: Path, js: str, case: dict[str, object]) -> dict[str, object]:
    node = _node()
    (tmp_path / "h.js").write_text(_HARNESS, encoding="utf-8")
    (tmp_path / "tag.js").write_text(js, encoding="utf-8")
    (tmp_path / "case.json").write_text(json.dumps(case), encoding="utf-8")
    result = subprocess.run(
        [
            node,
            str(tmp_path / "h.js"),
            str(tmp_path / "tag.js"),
            str(tmp_path / "case.json"),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    parsed: dict[str, object] = json.loads(result.stdout)
    return parsed


@pytest.fixture
def live_tag_js(tmp_path_factory) -> str:
    out = _build(
        tmp_path_factory.mktemp("live-ga4"),
        app_store_live=True,
        ga4_measurement_id="G-TEST12345",
    )
    scripts = _SCRIPT.findall((out / "index.html").read_text(encoding="utf-8"))
    assert len(scripts) == 1
    return scripts[0]


def test_ga4_tag_has_no_click_event_when_off(tmp_path):
    out = _build(tmp_path, ga4_measurement_id="G-TEST12345")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "googletagmanager" in html  # the tag itself is there
    assert "app_store_badge_click" not in html


def test_badge_click_is_sent_through_the_existing_tag(tmp_path, live_tag_js):
    ran = _click(tmp_path, live_tag_js, {"navigator": {"doNotTrack": "0"}})
    assert ran["events"] == [
        ["event", "app_store_badge_click", {"placement": "home", "link_url": APP_URL}]
    ]


@pytest.mark.parametrize(
    "case",
    [
        {"navigator": {"globalPrivacyControl": True}},
        {"navigator": {"doNotTrack": "1"}},
        {"navigator": {}, "disableAfterLoad": "ga-disable-G-TEST12345"},
    ],
)
def test_badge_click_is_not_sent_under_gpc_dnt_or_opt_out(tmp_path, live_tag_js, case):
    ran = _click(tmp_path, live_tag_js, case)
    assert ran["events"] == []


def test_negative_control_click_check_catches_a_removed_opt_out_check(
    tmp_path, live_tag_js
):
    guard = 'if (!a || w["ga-disable-" + id]) return;'
    sabotaged = live_tag_js.replace(guard, "if (!a) return;")
    assert sabotaged != live_tag_js  # the sabotage landed
    ran = _click(
        tmp_path,
        sabotaged,
        {"navigator": {}, "disableAfterLoad": "ga-disable-G-TEST12345"},
    )
    assert ran["events"] != []
