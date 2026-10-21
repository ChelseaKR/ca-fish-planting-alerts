"""Privacy page accuracy for the Android app, the link scope and the request.

Three corrections, each pinned by its own test, each with a negative control
that asserts its sabotage changed the page before it asserts the check
caught it (a sabotage that silently no-ops would otherwise read as a pass):

1. The page covers the iPhone and Android apps and their widgets, and does
   not say "no third-party SDK" about Android, which ships two Google
   libraries (Play Billing and Play In-App Review).
2. This site's Google Analytics is described as applying to this site's own
   pages only; CDFW and other sites have their own policies.
3. The schedule request is not said to "carry no identifier": it sends a
   fixed User-Agent and an ETag, both the same for every user.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from cfpa import cli

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
TEST_ID = "G-TEST12345"


def _privacy(root: Path, ga4_measurement_id: str | None) -> str:
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
        ga4_measurement_id=ga4_measurement_id,
    )
    return (out / "privacy" / "index.html").read_text(encoding="utf-8")


def _text(html: str) -> str:
    body = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", body).replace("&rsquo;", "'").lower()


@pytest.fixture(scope="module")
def with_id(tmp_path_factory: pytest.TempPathFactory) -> str:
    return _text(_privacy(tmp_path_factory.mktemp("acc-id"), TEST_ID))


@pytest.fixture(scope="module")
def without_id(tmp_path_factory: pytest.TempPathFactory) -> str:
    return _text(_privacy(tmp_path_factory.mktemp("acc-noid"), None))


# ---- correction 1: Android and widgets

OLD_SCOPE = "covers this website and the trout truck ios app."
OLD_LEDE = "the trout truck ios app collects no data at all"
OLD_SDK = "no third-party sdk. the website's google analytics"


def _coverage_problems(text: str) -> list[str]:
    problems = []
    for needed in (
        "covers this website and the trout truck apps for iphone and android.",
        "apps for iphone (with apple watch and widgets) and for android collect no data",
        "includes two libraries from google",
        "google play billing",
        "google play in-app review",
        "android home-screen widget",
        "excluded from cloud backup",
        "device-to-device transfer",
        "handled entirely by apple on iphone and by google play on android",
        "apple's privacy policy",
        "google's privacy policy",
        "local notifications",
        "by ios or by android",
    ):
        if needed not in text:
            problems.append(f"missing {needed!r}")
    for stale in (OLD_SCOPE, OLD_LEDE, OLD_SDK):
        if stale in text:
            problems.append(f"stale {stale!r}")
    return problems


@pytest.mark.parametrize("fixture_name", ["with_id", "without_id"])
def test_apps_section_names_android_and_its_google_libraries(
    fixture_name: str, request: pytest.FixtureRequest
):
    text = request.getfixturevalue(fixture_name)
    if fixture_name == "without_id":
        # The no-analytics variant has no lede about the apps' libraries, but
        # it must still cover Android and must not claim "no SDK" for it.
        assert "apps for iphone and android" in text
        assert "no third-party script or sdk" not in text
        assert "its ios app" not in text
        return
    assert _coverage_problems(text) == []
    # Android is never described as free of third-party SDKs.
    assert not re.search(r"android[^.]*no third-party sdk", text)


def test_coverage_check_fails_on_the_old_wording(with_id: str):
    sabotaged = with_id.replace(
        "covers this website and the trout truck apps for iphone and android.",
        OLD_SCOPE,
    ).replace("includes two libraries from google", "includes no third-party sdk")
    assert sabotaged != with_id  # the sabotage landed
    problems = _coverage_problems(sabotaged)
    assert any("missing" in p for p in problems)
    assert any(OLD_SCOPE in p for p in problems)


# ---- correction 2: link scope

NEW_LINKS = (
    "links to cdfw's map, to cdfw's schedule and to the other source sites open in "
    "your browser, on those sites. cdfw and those sites have their own privacy "
    "policies, and this site's analytics does not apply to them. this site's "
    "google analytics applies to this site's own pages only"
)
OLD_LINKS = "links to cdfw's map or to this site open in your browser"


def test_link_scope_says_analytics_is_this_sites_own_pages_only(with_id: str):
    assert NEW_LINKS in with_id
    assert OLD_LINKS not in with_id
    assert "cdfw's map or to this site" not in with_id


def test_link_scope_without_analytics_still_defers_to_other_sites(without_id: str):
    assert "have their own privacy policies" in without_id
    assert "google analytics applies" not in without_id


def test_link_scope_check_fails_on_the_old_wording(with_id: str):
    sabotaged = with_id.replace(
        NEW_LINKS, OLD_LINKS + ", where this site's google analytics applies"
    )
    assert sabotaged != with_id  # the sabotage landed
    assert NEW_LINKS not in sabotaged
    assert OLD_LINKS in sabotaged


# ---- correction 3: the request is not "identifier-free"

NEW_REQUEST = (
    "the request has no account, device or advertising identifier, and nothing "
    "about you or your favorites. it carries a fixed app name in its user-agent "
    "header and, once the app already has a copy, a cache tag (etag) that github "
    "pages issued for that file. both are the same for every user, so nothing in "
    "the request distinguishes one user from another."
)
OLD_REQUEST = "carries no identifier and nothing about you"


@pytest.mark.parametrize("fixture_name", ["with_id", "without_id"])
def test_request_wording_names_what_is_sent(
    fixture_name: str, request: pytest.FixtureRequest
):
    text = request.getfixturevalue(fixture_name)
    assert NEW_REQUEST in text
    assert OLD_REQUEST not in text
    assert "no identifier" not in text


def test_request_check_fails_on_the_old_wording(with_id: str):
    sabotaged = with_id.replace(NEW_REQUEST, "the request " + OLD_REQUEST + ";")
    assert sabotaged != with_id  # the sabotage landed
    assert NEW_REQUEST not in sabotaged
    assert OLD_REQUEST in sabotaged


# ---- the copy rules still hold on the corrected sections


def test_corrected_copy_keeps_the_site_rules(with_id: str, without_id: str):
    banned = re.compile(
        r"\b(the only|only place|only app|first app|the first|no one else|nobody else|the app for)\b"
    )
    for text in (with_id, without_id):
        assert not banned.search(text)
        assert "stocked" not in text
        # American English
        assert not re.search(r"\b(favourite|colour|behaviour|licence|centre)", text)
