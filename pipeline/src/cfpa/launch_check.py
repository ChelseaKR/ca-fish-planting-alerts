"""One consistency check for every App Store surface of a built site.

The launch switch (site.py APP_STORE_LIVE_DEFAULT / the APP_STORE_LIVE
variable) is one flag, but the site shows it in five places: Safari's Smart
App Banner tag, Apple's badge, the install links, the MobileApplication
JSON-LD and the GA4 click event (with the badge file and the "not in the App
Store yet" sentence as the other two sides). ``surface_problems`` reads a
built site and returns every place that disagrees with the state it is told
to expect, so a half-on site is a failing test and a failing preflight
rather than something a visitor finds.

It reads HTML with the standard library's parser, not regular expressions.
"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from cfpa import site

# Pages that carry the badge, and the placement each reports.
BADGE_PAGES = {"index.html": "home", "support/index.html": "support"}
# Pages that carry a text install link, and the placement each reports.
LINK_PAGES = {"index.html": "home", "about/index.html": "about"}
NOT_YET = "not in the App Store yet"
REQUIRED_APP_FIELDS = (
    "@type",
    "@id",
    "name",
    "operatingSystem",
    "applicationCategory",
    "description",
    "url",
    "downloadUrl",
    "offers",
)
FORBIDDEN_APP_FIELDS = frozenset({"aggregateRating", "review", "interactionStatistic"})


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.banners: list[tuple[str | None, bool]] = []
        self.app_links: list[dict[str, str | None]] = []
        self.ld: list[str] = []
        self.scripts: list[str] = []
        self._script: tuple[str | None, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "head":
            self.in_head = True
        elif tag == "meta" and a.get("name") == "apple-itunes-app":
            self.banners.append((a.get("content"), self.in_head))
        elif tag == "a" and "apps.apple.com" in (a.get("href") or ""):
            self.app_links.append(a)
        elif tag == "script":
            self._script = (a.get("type"), [])

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self.in_head = False
        elif tag == "script" and self._script is not None:
            kind, parts = self._script
            text = "".join(parts)
            if kind == "application/ld+json":
                self.ld.append(text)
            else:
                self.scripts.append(text)
            self._script = None

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._script[1].append(data)


def _parse(html: str) -> _Page:
    page = _Page()
    page.feed(html)
    page.close()
    return page


def _apps(page: _Page) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for block in page.ld:
        data = json.loads(block)
        graph = data.get("@graph", [data]) if isinstance(data, dict) else data
        found += [n for n in graph if n.get("@type") == "MobileApplication"]
    return found


def _page_problems(
    name: str, page: _Page, text: str, *, live: bool, url: str, has_ga: bool
) -> list[str]:
    """Banner, links, badges, JSON-LD and click event of one page."""
    problems: list[str] = []
    # Safari's Smart App Banner: one tag in <head> on every page, or none.
    want = [(f"app-id={site.APP_STORE_ID}", True)] if live else []
    if page.banners != want:
        problems.append(f"{name}: banner tags {page.banners!r}, want {want!r}")
    problems += _link_problems(name, page, live=live, url=url)
    problems += _schema_problems(name, page, text, live=live, url=url)
    # The click event lives in the GA4 tag, so only where the tag is.
    has_event = "app_store_click" in text
    if has_ga and has_event != live:
        problems.append(f"{name}: app_store_click present={has_event}, want {live}")
    if not has_ga and has_event:
        problems.append(f"{name}: app_store_click outside the GA4 tag")
    return problems


def _link_problems(name: str, page: _Page, *, live: bool, url: str) -> list[str]:
    problems: list[str] = []
    for a in page.app_links:
        if not live:
            problems.append(f"{name}: App Store link while off: {a.get('href')}")
            continue
        if a.get("href") != url:
            problems.append(
                f"{name}: App Store link to {a.get('href')!r}, want {url!r}"
            )
        if not a.get("data-app-store-placement"):
            problems.append(f"{name}: App Store link without a placement")
        if a.get("data-app-store-kind") not in ("badge", "link"):
            problems.append(f"{name}: App Store link without a kind")
    if live:
        problems += _live_placement_problems(name, page)
    return problems


def _live_placement_problems(name: str, page: _Page) -> list[str]:
    """Where a live site must show the badge and the text link."""
    problems: list[str] = []
    badges = [a for a in page.app_links if a.get("data-app-store-kind") == "badge"]
    if len(badges) != (name in BADGE_PAGES):
        problems.append(
            f"{name}: {len(badges)} badges, want {int(name in BADGE_PAGES)}"
        )
    for a in badges:
        if a.get("data-app-store-placement") != BADGE_PAGES.get(name):
            problems.append(
                f"{name}: badge placement {a.get('data-app-store-placement')!r}"
            )
    wants_link = name in LINK_PAGES or (
        name.startswith("water/") and name.endswith("/index.html")
    )
    if wants_link and not any(
        a.get("data-app-store-kind") == "link" for a in page.app_links
    ):
        problems.append(f"{name}: install link missing")
    return problems


def _schema_problems(
    name: str, page: _Page, text: str, *, live: bool, url: str
) -> list[str]:
    """The MobileApplication JSON-LD: home and support when live, else none."""
    problems: list[str] = []
    apps = _apps(page)
    want = 1 if live and name in BADGE_PAGES else 0
    if len(apps) != want:
        problems.append(f"{name}: {len(apps)} MobileApplication blocks, want {want}")
    for app in apps:
        problems += [
            f"{name}: MobileApplication lacks {field}"
            for field in REQUIRED_APP_FIELDS
            if field not in app
        ]
        problems += [
            f"{name}: MobileApplication invents {field}"
            for field in sorted(FORBIDDEN_APP_FIELDS & set(app))
        ]
        if app.get("url") != url or app.get("downloadUrl") != url:
            problems.append(f"{name}: MobileApplication points at {app.get('url')!r}")
    if not live and "MobileApplication" in text:
        problems.append(f"{name}: MobileApplication text while off")
    return problems


def surface_problems(
    out: Path, *, live: bool, url: str = site.APP_STORE_CANONICAL_URL
) -> list[str]:
    """Every App Store surface of the site in ``out`` that does not match
    ``live``. An empty list means all on (live) or all off (not live)."""
    names = [str(f.relative_to(out)) for f in sorted(out.rglob("*.html"))]
    if len(names) < 10:
        return [f"only {len(names)} pages built; the check would prove nothing"]
    problems: list[str] = []
    texts = {n: (out / n).read_text(encoding="utf-8") for n in names}
    pages = {n: _parse(t) for n, t in texts.items()}
    if live and not any(n.startswith("water/") for n in names):
        problems.append("no water pages built; the install-link check proved nothing")
    for name in names:
        has_ga = any("gtag" in s for s in pages[name].scripts)
        problems += _page_problems(
            name, pages[name], texts[name], live=live, url=url, has_ga=has_ga
        )
    # The about page says so while the app is not in the store, and only then.
    about = texts.get("about/index.html", "")
    if live and NOT_YET in about:
        problems.append("about/index.html: still says the app is not in the store")
    if not live and NOT_YET not in about:
        problems.append("about/index.html: lost its 'not in the App Store yet' copy")
    badge_file = out / "assets" / site.APP_STORE_BADGE_FILE
    if badge_file.exists() != live:
        problems.append(f"badge file exists={badge_file.exists()}, want {live}")
    return problems
