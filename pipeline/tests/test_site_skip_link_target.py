"""The "Skip to main content" link moves keyboard focus into the page (2.4.1).

Found by the 2026-11-19 accessibility conformance audit (docs/a11y/ACR.md).
In Chrome, pressing Enter on the skip link scrolled to <main> and set the
address to #main, but focus stayed behind: activeElement was <body>, and the
next Tab went to the header's first link ("Trout Truck"), the link right after
the skip link. A keyboard user who used the skip link skipped nothing. axe,
pa11y and Lighthouse all pass the page, because each only checks that the
link's target exists.

A target that can take focus fixes it in every engine: <main> gets
tabindex="-1", which makes it focusable from the link but never a Tab stop of
its own. The region does not draw a focus ring around the whole page body;
the links and buttons inside keep theirs.

The pattern is the repository's own (test_site_footer_link_targets.py): check
the built pages and the source stylesheet, and prove with a negative control
that the check notices when the fix is gone.
"""

from __future__ import annotations

import datetime as dt
import re
from html.parser import HTMLParser
from pathlib import Path

from cfpa import cli

TEMPLATES = Path(__file__).parents[1] / "src" / "cfpa" / "templates"
STYLE = TEMPLATES / "style.css"
FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"


class _SkipLinkProbe(HTMLParser):
    """The skip link's href and the attributes of the element it names."""

    def __init__(self) -> None:
        super().__init__()
        self.skip_href: str | None = None
        self.elements: dict[str, tuple[str, dict[str, str | None]]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = dict(attrs)
        if "skip-link" in (found.get("class") or "").split() and self.skip_href is None:
            self.skip_href = found.get("href")
        element_id = found.get("id")
        if element_id:
            self.elements[element_id] = (tag, found)


def _skip_target_problem(html: str) -> str | None:
    """None when the skip link names a <main> that can take focus without
    being a Tab stop; otherwise what is wrong."""
    probe = _SkipLinkProbe()
    probe.feed(html)
    if not probe.skip_href or not probe.skip_href.startswith("#"):
        return f"no in-page skip link (href {probe.skip_href!r})"
    target = probe.elements.get(probe.skip_href[1:])
    if target is None:
        return f"nothing has id {probe.skip_href[1:]!r}"
    tag, attrs = target
    if tag != "main":
        return f"the skip link names a <{tag}>, not <main>"
    if attrs.get("tabindex") != "-1":
        return f'<main> has tabindex {attrs.get("tabindex")!r}, not "-1"'
    return None


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


def test_every_page_skip_link_names_a_main_that_takes_focus(tmp_path: Path) -> None:
    out = _build_site(tmp_path)
    pages = sorted(out.rglob("*.html"))
    assert len(pages) > 10
    problems = [
        f"{page.relative_to(out)}: {problem}"
        for page in pages
        if (problem := _skip_target_problem(page.read_text(encoding="utf-8")))
    ]
    assert problems == []


def _rule(css: str, selector: str) -> str:
    """The declarations of the rule whose selector is exactly ``selector``."""
    plain = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    bodies = [
        body
        for found, body in re.findall(r"([^{}]+)\{([^{}]*)\}", plain)
        if selector in [part.strip() for part in found.split(",")]
    ]
    return " ".join(" ".join(bodies).split())


def test_main_draws_no_ring_but_controls_inside_keep_theirs() -> None:
    css = STYLE.read_text(encoding="utf-8")
    assert _rule(css, "#main:focus") == "outline: none;"
    # The ring the links and buttons draw is untouched.
    assert "outline: var(--focus-width) solid var(--focus);" in _rule(
        css, "a:focus-visible"
    )
    # Only the region opts out: no rule anywhere removes the ring from a
    # link or a button.
    plain = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", plain):
        if "outline: none" in body or "outline:none" in body:
            assert selectors.strip() == "#main:focus", selectors


def test_negative_control_the_check_notices_a_main_without_tabindex() -> None:
    fixed = (
        '<a class="skip-link" href="#main">Skip to main content</a>'
        '<header><a href="./">Trout Truck</a></header>'
        '<main id="main" class="wrap" tabindex="-1"><h1>A page</h1></main>'
    )
    assert _skip_target_problem(fixed) is None
    before = fixed.replace(' tabindex="-1"', "")
    assert _skip_target_problem(before) == '<main> has tabindex None, not "-1"'
    assert _skip_target_problem(fixed.replace('tabindex="-1"', 'tabindex="0"'))
    assert _skip_target_problem(fixed.replace('id="main"', 'id="content"'))
