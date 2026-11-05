"""The terms of use page: built, linked from every footer, in the sitemap."""

import datetime as dt
import re
from pathlib import Path

from cfpa import cli

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"


def _build_site(tmp_path: Path) -> Path:
    out = tmp_path / "site"
    cli.run(
        fixture_path=str(FRESH),
        history_path=tmp_path / "history.json",
        aliases_path=tmp_path / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url="https://example.invalid/ca-fish-planting-alerts",
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    return out


def _text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_terms_page_names_the_operator_and_the_limits(tmp_path: Path) -> None:
    out = _build_site(tmp_path)
    text = _text((out / "terms" / "index.html").read_text(encoding="utf-8"))
    assert "Chelsea Kelly-Reif" in text
    assert "chelsea@chelseakr.com" in text
    assert "not affiliated with or endorsed by CDFW" in text
    assert "can be wrong or late" in text
    assert "As an Amazon Associate I earn from qualifying purchases." in text
    assert "laws of the State of California" in text
    assert len(text.split()) < 700


def test_every_footer_links_the_terms_page(tmp_path: Path) -> None:
    out = _build_site(tmp_path)
    pages = [p for p in sorted(out.rglob("*.html")) if p.name != "404.html"]
    assert pages
    for page in pages:
        assert 'terms/">terms</a>' in page.read_text(encoding="utf-8"), page


def test_terms_page_is_in_the_sitemap(tmp_path: Path) -> None:
    out = _build_site(tmp_path)
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "/terms/</loc>" in sitemap


OLD_APPS = "apps are sold through app stores"
IPHONE_SOLD = "iPhone app is sold through Apple's App Store"


def _apps_problems(text: str) -> list[str]:
    # DECISIONS 0044: the Android build sells nothing, so the page must not
    # say every app is sold. Only the privacy page names Android
    # (test_site_app_store.test_copy_never_mentions_android).
    problems = []
    if IPHONE_SOLD not in text:
        problems.append("missing the iPhone sale line")
    if OLD_APPS in text:
        problems.append("says every app is sold")
    return problems


def test_terms_page_says_only_the_iphone_app_is_sold(tmp_path: Path) -> None:
    out = _build_site(tmp_path)
    text = _text((out / "terms" / "index.html").read_text(encoding="utf-8"))
    assert _apps_problems(text) == []
    # Negative control: put the old wording back; the sabotage must land
    # before the check is asked to catch it.
    sabotaged = text.replace("iPhone app is sold through Apple's App Store", OLD_APPS)
    assert sabotaged != text
    assert _apps_problems(sabotaged) == [
        "missing the iPhone sale line",
        "says every app is sold",
    ]
