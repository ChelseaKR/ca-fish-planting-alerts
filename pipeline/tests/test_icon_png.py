"""The site icon as files a search engine can show.

The tab icon is an SVG written inside every page. Google Search shows a
site's icon only from a crawlable file in a raster format, square, at a
multiple of 48 px, so the same icon also ships as PNG at 48, 96 and 192 px,
linked from every page, plus /favicon.ico for clients that ask for it
unprompted.

Pages are read with html.parser, never a regular expression over markup.
Each check has a control that proves it can fail.
"""

from __future__ import annotations

import datetime as dt
import io
import struct
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.robotparser import RobotFileParser

import pytest
from PIL import Image

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
TEMPLATES = Path(site.__file__).parent / "templates"
INLINE = "data:image/svg+xml,"
# The inline icon's own colors, and where each sits on its 32-unit grid: the
# raceway square, the trout, the stripe under it.
SQUARE = (0x0C, 0x3A, 0x36)
TROUT = (0xE6, 0xBD, 0x6D)
STRIPE = (0xA3, 0x32, 0x4F)
SPOTS = {(16.0, 3.0): SQUARE, (16.0, 15.0): TROUT, (16.0, 27.5): STRIPE}


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("icons")
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
    )
    return out


class _Icons(HTMLParser):
    """Every <link rel="icon"> in a page, as its attributes."""

    def __init__(self) -> None:
        super().__init__()
        self.icons: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = {name: value or "" for name, value in attrs}
        if tag == "link" and found.get("rel") == "icon":
            self.icons.append(found)


def icons_of(html: str) -> list[dict[str, str]]:
    parser = _Icons()
    parser.feed(html)
    return parser.icons


def icon_problems(page: Path, root: Path) -> list[str]:
    """What is wrong with one built page's icon links; empty when nothing.
    `root` is the build's top directory: the 404 page is served at any path,
    so its links start at the site's own path, not at the page."""
    problems = []
    icons = icons_of(page.read_text(encoding="utf-8"))
    pngs = {i.get("sizes", ""): i for i in icons if i.get("type") == "image/png"}
    for size in site.ICON_PNG_SIZES:
        link = pngs.get(f"{size}x{size}")
        if link is None:
            problems.append(f"no {size} px PNG icon link")
            continue
        href = link["href"]
        if href.startswith("/"):
            target = root / href.removeprefix(urlsplit(BASE_URL).path).lstrip("/")
        else:
            target = (page.parent / href).resolve()
        if not target.is_file():
            problems.append(f"{href} is not a file in the build")
        elif Image.open(target).size != (size, size):
            problems.append(f"{href} is not {size} px square")
    inline = [i for i in icons if i.get("href", "").startswith(INLINE)]
    if len(inline) != 1 or icons[-1:] != inline:
        problems.append("the inline SVG icon is not the one, last icon link")
    return problems


def test_the_png_icons_are_square_multiples_of_48_and_ship_unchanged(
    built: Path,
) -> None:
    assert site.ICON_PNG_SIZES == (48, 96, 192)
    for size in site.ICON_PNG_SIZES:
        assert size % 48 == 0
        packaged = (TEMPLATES / f"icon-{size}.png").read_bytes()
        image = Image.open(io.BytesIO(packaged))
        assert (image.format, image.size) == ("PNG", (size, size))
        built_file = built / "assets" / f"icon-{size}.png"
        assert built_file.read_bytes() == packaged, "the build must copy, not redraw"


@pytest.mark.parametrize("size", site.ICON_PNG_SIZES)
def test_each_icon_is_the_inline_icon_in_its_own_colors(size: int) -> None:
    image = Image.open(TEMPLATES / f"icon-{size}.png").convert("RGBA")
    scale = size / 32
    for (x, y), color in SPOTS.items():
        assert image.getpixel((int(x * scale), int(y * scale))) == (*color, 255), (x, y)
    # The square's corners are rounded, so the very corner is clear.
    assert image.getpixel((0, 0))[3] == 0
    # The inline icon still has those colors: the files were made from it.
    home = (TEMPLATES / "base.html.jinja").read_text(encoding="utf-8")
    inline = [i["href"] for i in icons_of(home) if i.get("href", "").startswith(INLINE)]
    assert len(inline) == 1
    svg = unquote(inline[0])
    for color in (SQUARE, TROUT, STRIPE):
        assert "#{:02x}{:02x}{:02x}".format(*color) in svg


def test_every_page_links_the_three_png_icons_and_each_file_exists(
    built: Path,
) -> None:
    pages = sorted(built.rglob("*.html"))
    assert len(pages) > 20
    for page in pages:
        assert icon_problems(page, built) == [], page


def test_favicon_ico_sits_at_the_site_root_with_the_icon_at_16_32_and_48(
    built: Path,
) -> None:
    data = (built / site.FAVICON_ICO_FILE).read_bytes()
    assert data == (TEMPLATES / site.FAVICON_ICO_FILE).read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind, count) == (0, 1, 3)
    sizes = []
    for n in range(count):
        entry = data[6 + 16 * n : 22 + 16 * n]
        width, height, _, _, _, bits, length, offset = struct.unpack("<BBBBHHII", entry)
        image = Image.open(io.BytesIO(data[offset : offset + length]))
        assert (image.format, image.size, bits) == ("PNG", (width, height), 32)
        sizes.append(width)
    assert sizes == [16, 32, 48]


def test_robots_txt_lets_an_image_crawler_fetch_the_icons(built: Path) -> None:
    robots = RobotFileParser()
    robots.parse((built / "robots.txt").read_text(encoding="utf-8").splitlines())
    paths = (
        site.FAVICON_ICO_FILE,
        *(f"assets/icon-{s}.png" for s in site.ICON_PNG_SIZES),
    )
    for path in paths:
        for agent in ("Googlebot-Image", "Googlebot", "bingbot"):
            assert robots.can_fetch(agent, f"{BASE_URL}/{path}"), (agent, path)


def test_the_link_tags_add_no_word_a_reader_sees(built: Path) -> None:
    for icon in icons_of((built / "index.html").read_text(encoding="utf-8")):
        assert set(icon) <= {"rel", "href", "type", "sizes"}, icon


# -- controls: each check can fail -----------------------------------------


def test_control_a_page_without_the_png_links_is_reported(
    built: Path, tmp_path: Path
) -> None:
    home = (built / "index.html").read_text(encoding="utf-8")
    kept = [
        line
        for line in home.splitlines()
        if not ('rel="icon"' in line and "image/png" in line)
    ]
    assert len(kept) == len(home.splitlines()) - 3  # the sabotage applied
    page = tmp_path / "index.html"
    page.write_text("\n".join(kept), encoding="utf-8")
    assert icon_problems(page, built) == [
        "no 48 px PNG icon link",
        "no 96 px PNG icon link",
        "no 192 px PNG icon link",
    ]


def test_control_a_missing_file_a_wrong_size_and_a_lost_inline_icon_are_reported(
    built: Path, tmp_path: Path
) -> None:
    copy = tmp_path / "site"
    (copy / "assets").mkdir(parents=True)
    home = (built / "index.html").read_text(encoding="utf-8")
    without_inline = "\n".join(line for line in home.splitlines() if INLINE not in line)
    assert without_inline != home  # the sabotage applied
    (copy / "index.html").write_text(without_inline, encoding="utf-8")
    for name in ("icon-48.png", "icon-96.png"):
        (copy / "assets" / name).write_bytes(
            (built / "assets" / "icon-96.png").read_bytes()
        )
    assert icon_problems(copy / "index.html", copy) == [
        "./assets/icon-48.png is not 48 px square",
        "./assets/icon-192.png is not a file in the build",
        "the inline SVG icon is not the one, last icon link",
    ]


def test_control_a_robots_file_that_blocks_assets_fails_the_crawl_check() -> None:
    robots = RobotFileParser()
    robots.parse(["User-agent: *", "Disallow: /assets/"])
    assert not robots.can_fetch(
        "Googlebot-Image", "https://example.invalid/assets/icon-48.png"
    )
