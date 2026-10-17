"""The water pages' Gear line (DECISIONS 0028).

Three promises, each checked against a real fixture build of California and
Tennessee:

1. With no affiliate link configured (GEAR_LINK_TEMPLATE = "", as committed),
   nothing changes: the build with the link set, minus the Gear paragraph, is
   byte for byte the build without it, and the build without it carries no
   paid link anywhere.
2. With it set, every water page (California and every other state) carries
   exactly one Gear link: rel="sponsored noopener", "(Paid link)" right after
   it, the destination URL-encoded into the template, and a line saying the
   agency does not endorse it. No other page carries one.
3. The Gear line sits apart from the agency attribution: not in the footer,
   and not in a state page's "Source and terms" section.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "states"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO = Path(__file__).resolve().parents[2]
V1_SCHEMA = REPO / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
TEMPLATE = "https://basspro.pxf.io/c/1234567/123456/12345?u={url}"
HREF = TEMPLATE.replace("{url}", quote(site.GEAR_DESTINATION_URL, safe=""))

# The Gear paragraph as the templates render it, blank line after included,
# and the privacy page's paragraph about it.
_GEAR = re.compile(
    r'<p class="muted gear">.*?</p>\n\n|<p id="paid-links">.*?</p>\n', re.S
)


@pytest.fixture(scope="module")
def builds(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("gear")
    v1 = cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=V1_SCHEMA,
        site_out=root / "run",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=("TN",),
        states_fixtures=STATE_FIXTURES,
    )
    v2 = json.loads((root / "run" / "snapshot" / "v2.json").read_text("utf-8"))
    site.build_site(v1, root / "without", base_url=BASE, snapshot_v2=v2)
    site.build_site(
        v1, root / "with", base_url=BASE, snapshot_v2=v2, gear_link_template=TEMPLATE
    )
    return root / "without", root / "with"


def _pages(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): p.read_text("utf-8")
        for p in sorted(root.rglob("*.html"))
    }


def _is_water_page(rel: str) -> bool:
    # California: water/<slug>/index.html. Other states: <st>/water/<slug>/index.html.
    return re.fullmatch(r"(?:[a-z]{2}/)?water/[^/]+/index\.html", rel) is not None


def test_the_committed_template_is_empty_or_valid():
    assert site.GEAR_LINK_TEMPLATE == "" or site.gear_link_or_none(
        site.GEAR_LINK_TEMPLATE
    )


def test_no_template_changes_nothing(builds: tuple[Path, Path]):
    without, with_ = builds
    a = {
        p.relative_to(without).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(without.rglob("*"))
        if p.is_file()
    }
    b_pages = _pages(with_)
    # Same files; only HTML pages may differ, and only by the Gear paragraph.
    assert sorted(a) == sorted(
        p.relative_to(with_).as_posix() for p in with_.rglob("*") if p.is_file()
    )
    for rel, digest in a.items():
        if rel in b_pages:
            stripped = _GEAR.sub("", b_pages[rel]).encode("utf-8")
            assert hashlib.sha256(stripped).hexdigest() == digest, rel
        else:
            assert hashlib.sha256((with_ / rel).read_bytes()).hexdigest() == digest, rel
    for rel, html in _pages(without).items():
        assert "sponsored" not in html, rel
        assert "Paid link" not in html, rel
        assert 'id="paid-links"' not in html, rel


def test_every_water_page_carries_one_labeled_gear_link(builds: tuple[Path, Path]):
    _, with_ = builds
    pages = _pages(with_)
    water = [rel for rel in pages if _is_water_page(rel)]
    assert any(rel.startswith("water/") for rel in water)
    assert any(rel.startswith("tn/water/") for rel in water)
    for rel, html in pages.items():
        links = re.findall(r'<a href="([^"]+)" rel="sponsored noopener">', html)
        if rel == "privacy/index.html":
            assert 'id="paid-links"' in html
        if not _is_water_page(rel):
            assert links == [], rel
            continue
        assert links == [HREF], rel
        assert (
            f'rel="sponsored noopener">trout fishing gear at {site.GEAR_MERCHANT_NAME}'
            "</a> (Paid link)." in html
        ), rel
        agency = "CDFW" if rel.startswith("water/") else "TWRA"
        assert f"{agency} does not endorse it" in html, rel


def test_the_gear_line_sits_apart_from_the_attribution(builds: tuple[Path, Path]):
    _, with_ = builds
    for rel, html in _pages(with_).items():
        if not _is_water_page(rel):
            continue
        gear = html.index('<p class="muted gear">')
        footer = html.index('<footer class="site-footer">')
        assert gear < footer, rel
        if "<h2>Source and terms</h2>" in html:
            assert gear < html.index("<h2>Source and terms</h2>"), rel
        # And before the page's own "About this water" facts, not inside them.
        assert gear < html.index("<h2>About this water</h2>"), rel


@pytest.mark.parametrize(
    "bad",
    [
        "http://basspro.pxf.io/c/1/2/3?u={url}",
        "https://basspro.pxf.io/c/1/2/3",
        "https://basspro.pxf.io/c/1/2/3?u={url}&v={url}",
        "https://basspro.pxf.io/c/1/2/3?u={url}&sub={reader}",
        " https://basspro.pxf.io/c/1/2/3?u={url}",
        "javascript:alert(1)//{url}",
    ],
)
def test_a_malformed_template_is_refused(bad: str):
    with pytest.raises(ValueError, match="gear link template"):
        site.gear_link_or_none(bad)


def test_the_destination_is_url_encoded_into_the_template():
    assert site.gear_link_or_none("") is None
    assert site.gear_link_or_none(None) is None
    assert site.gear_link_or_none(TEMPLATE) == (
        "https://basspro.pxf.io/c/1234567/123456/12345?u="
        "https%3A%2F%2Fwww.basspro.com%2Fl%2Ftrout-fishing-gear"
    )
