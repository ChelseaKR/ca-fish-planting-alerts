"""IndexNow on the real fixture build and in the publish workflow.

The key file ships only in the custom-domain build, every URL the sitemap
lists is announceable (own host, built, indexable), robots.txt lets Bingbot in
and names the sitemap, and the workflow selects before the live site is
replaced and submits only after the domain is verified."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from cfpa import cli
from cfpa import indexnow as ix

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
DOMAIN_URL = "https://trouttruck.example"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish.yml"


def _build(root: Path, base_url: str) -> Path:
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=base_url,
        legacy_site_out=None,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    return root / "site"


@pytest.fixture(scope="module")
def domain_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("ixdomain"), DOMAIN_URL)


def test_the_domain_build_carries_exactly_one_matching_key_file(domain_site):
    key = ix.find_key(domain_site)
    assert (domain_site / f"{key}.txt").read_text(encoding="utf-8").strip() == key
    assert re.fullmatch(r"[0-9a-f]{32}", key)


def test_a_build_without_a_custom_domain_has_no_key_file(tmp_path_factory):
    site = _build(
        tmp_path_factory.mktemp("ixnodomain"),
        "https://chelseakr.github.io/ca-fish-planting-alerts",
    )
    assert not [p for p in site.iterdir() if ix.KEY_FILE_RE.match(p.name)]


def test_robots_allows_bingbot_and_lists_the_sitemap(domain_site):
    robots = (domain_site / "robots.txt").read_text(encoding="utf-8")
    assert ix.check_robots(robots, DOMAIN_URL) == []


def test_every_sitemap_url_is_announceable_and_the_sitemap_is_not_empty(domain_site):
    entries = ix.parse_sitemap(
        (domain_site / "sitemap.xml").read_text(encoding="utf-8")
    )
    assert len(entries) > 20
    kept, notes = ix.filter_submittable(
        sorted(entries), base_url=DOMAIN_URL, site_dir=domain_site
    )
    assert notes == []
    assert kept == sorted(entries)


def test_selection_on_the_real_sitemap_finds_exactly_the_edits(domain_site):
    cur = ix.parse_sitemap((domain_site / "sitemap.xml").read_text(encoding="utf-8"))
    urls = sorted(cur)
    prev = dict(cur)
    removed, bumped = urls[3], urls[5]
    del prev[removed]
    prev[bumped] = "2000-01-01"
    assert prev != cur  # the sabotage applied
    assert ix.select_changed(prev, cur) == sorted([removed, bumped])
    assert ix.select_changed(cur, cur) == []


def test_the_noindex_thin_pages_are_not_in_the_sitemap(domain_site):
    entries = set(
        ix.parse_sitemap((domain_site / "sitemap.xml").read_text(encoding="utf-8"))
    )
    noindexed = [
        p
        for p in domain_site.rglob("*.html")
        if ix.is_noindex(p.read_text(encoding="utf-8", errors="replace"))
    ]
    assert noindexed, "the build has no noindex page, so this check proves nothing"
    for p in noindexed:
        rel = p.relative_to(domain_site).as_posix().removesuffix("index.html")
        assert f"{DOMAIN_URL}/{rel}" not in entries


def _steps() -> list[str]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return re.findall(
        r"^      - name: (.+)$",
        text[text.index("\n  build:\n") : text.index("\n  deploy:\n")],
        re.M,
    )


def test_workflow_selects_before_the_push_and_submits_after_the_wait():
    names = _steps()
    select = next(n for n in names if n.startswith("pick the pages to announce"))
    submit = next(
        n for n in names if n.startswith("announce the new and changed pages")
    )
    push = next(n for n in names if n.startswith("push the domain site"))
    wait = next(n for n in names if n.startswith("wait for the domain"))
    assert (
        names.index(select)
        < names.index(push)
        < names.index(wait)
        < names.index(submit)
    )


def test_workflow_indexnow_steps_never_fail_the_run_and_need_no_secret():
    text = WORKFLOW.read_text(encoding="utf-8")
    for name in ("pick the pages to announce", "announce the new and changed pages"):
        start = text.index(f"- name: {name}")
        block = text[start : text.index("\n      - ", start + 10)]
        assert "continue-on-error: true" in block
        assert "vars.SITE_BASE_URL != ''" in block
        assert "secrets." not in block
    # Only the scheduled/manual publish workflow calls it, never PR CI.
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "indexnow" not in ci
