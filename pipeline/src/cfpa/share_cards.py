"""Share cards: the 1200x630 image a link preview shows (Open Graph, Twitter).

One card per *kind* of page, not per page. The text on a card depends only on
the kind (home, county, water, state, ...) plus the date the schedule was
last checked, so a site of 580 pages needs a handful of PNGs, not 580. The
kinds live in ``CARD_KINDS``: a new page type (region pages, species pages)
adds one entry and one line in ``site.py`` naming the kind it uses; nothing
else changes.

Wording rule: a card says "scheduled", never "stocked". The schedule is
week-level and subject to change, and a preview must not read as a promise
that fish are in the water. Every string a card shows is in ``CARD_KINDS``,
``SITE_NAME`` or the freshness line built here, so the exact copy is
reviewable in one place.

Look: the site's "raceway" identity (style.css, from the design audit of
2026-11-05). A raceway-teal ground, the site's gold trout mark over two
ripple rings, Bitter 800 for the name and the headline,
Atkinson Hyperlegible Next for the rest, and the gold, redband-rose and
silver stripe along the bottom edge. The colors are the style.css tokens of
the same names (``PALETTE``); tests/test_share_cards.py reads style.css and
fails if the two drift apart. The fonts are the site's own self-hosted
files (SIL OFL 1.1, templates/fonts), so nothing is fetched to draw a card.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

CARD_WIDTH = 1200
CARD_HEIGHT = 630
CARD_DIR = "assets/share"

# The style.css tokens a card uses, by their CSS names (light scheme: a
# link preview has no dark mode). Text sits on the masthead teal only.
PALETTE: dict[str, str] = {
    "masthead-bg": "#0c3a36",
    "masthead-fg": "#f4efe2",
    "trout-gold": "#e6bd6d",
    "redband": "#a3324f",
    "flank-silver": "#c9d6d2",
}
# The dark-scheme masthead (#0a2a27) is the bottom of the ground's gentle
# fall, so the card reads as the site's header band at any size.
MASTHEAD_DEEP = "#0a2a27"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


_TOP = _rgb(PALETTE["masthead-bg"])
_BOTTOM = _rgb(MASTHEAD_DEEP)
_NAME = _rgb(PALETTE["trout-gold"])
_TITLE = _rgb(PALETTE["masthead-fg"])
_BODY = _rgb(PALETTE["masthead-fg"])
_MUTED = _rgb(PALETTE["flank-silver"])
# The stripe under every masthead, scaled from the site's 2px/4px/3px.
STRIPE: tuple[tuple[str, int], ...] = (
    ("trout-gold", 6),
    ("redband", 12),
    ("flank-silver", 9),
)
STRIPE_HEIGHT = sum(h for _, h in STRIPE)

_MARK_SIZE = 380
_MARK_X = 70
_TEXT_X = 520
_TEXT_RIGHT = CARD_WIDTH - 60
_FRESHNESS_Y = CARD_HEIGHT - STRIPE_HEIGHT - 80

_FONT_DIR = Path(__file__).parent / "templates" / "fonts"
_DISPLAY_FONT = _FONT_DIR / "bitter-latin.woff2"
_BODY_FONT = _FONT_DIR / "atkinson-hyperlegible-next-latin.woff2"

# The mark, in the 32x32 units of the SVG in style.css (.site-name a::before).
# The fish outline is that path with its curves written out absolutely:
# each entry is a line to a point, or a cubic curve (two controls, an end).
_FISH_START = (3.0, 15.0)
_FISH: tuple[tuple[tuple[float, float], ...], ...] = (
    ((6.0, 10.5), (11.0, 8.5), (16.0, 9.0)),
    ((19.4, 9.3), (22.0, 10.8), (24.0, 12.8)),
    ((28.5, 9.5),),
    ((27.1, 15.0),),
    ((28.5, 20.5),),
    ((24.0, 17.2),),
    ((22.0, 19.2), (19.4, 20.7), (16.0, 21.0)),
    ((11.0, 21.5), (6.0, 19.5), (3.0, 15.0)),
)
# Eye, then three spots: (cx, cy, r).
_FISH_DOTS = ((8.0, 13.6, 1.1), (14.0, 11.6, 0.7), (17.5, 11.4, 0.7), (21.0, 12.4, 0.7))
# Ripple rings: (cx, cy, rx, ry), stroked 1.2 units at 60% opacity.
_RIPPLES = ((16.0, 25.0, 11.5, 3.2), (16.0, 25.0, 6.5, 1.7))
_RIPPLE_WIDTH = 1.2
_RIPPLE_OPACITY = 0.6
# Drawn this many times larger, then scaled down: smooth edges, same bytes
# every run.
_SUPERSAMPLE = 4


@dataclass(frozen=True)
class CardKind:
    """The copy one kind of page's card carries."""

    title: str
    subtitle: str


CARD_KINDS: dict[str, CardKind] = {
    "home": CardKind(
        "California trout planting schedule",
        "Waters scheduled for trout plantings, by county and week",
    ),
    "county": CardKind(
        "Trout plantings by county",
        "Which waters in this county are scheduled, and when",
    ),
    "region": CardKind(
        "Trout plantings by CDFW region",
        "Waters scheduled across this region, and when",
    ),
    "water": CardKind(
        "Scheduled trout plantings for this water",
        "Week-level schedule, subject to change",
    ),
    "species": CardKind(
        "Scheduled plantings by species",
        "Waters scheduled for this species, this week and next",
    ),
    "state": CardKind(
        "Trout plantings by state",
        "Each state's own schedule or report, at the precision it gives",
    ),
}


def freshness_line(checked_on: str) -> str:
    """'Schedule checked Oct 21, 2026' from an ISO date (YYYY-MM-DD)."""
    day = dt.date.fromisoformat(checked_on[:10])
    return f"Schedule checked {day.strftime('%b')} {day.day}, {day.year}"


def card_filename(kind: str) -> str:
    if kind not in CARD_KINDS:
        raise ValueError(f"unknown share card kind {kind!r}")
    return f"{kind}.png"


def card_alt(kind: str, *, site_name: str, checked_on: str) -> str:
    """The alt text: every sentence the card shows, in reading order."""
    c = CARD_KINDS[kind]
    return f"{site_name}. {c.title}. {c.subtitle}. {freshness_line(checked_on)}."


def card_meta(
    kind: str, *, base_url: str, site_name: str, checked_on: str
) -> dict[str, Any]:
    """The values base.html.jinja needs for one kind's og:image tags."""
    return {
        "url": f"{base_url}/{CARD_DIR}/{card_filename(kind)}",
        "width": CARD_WIDTH,
        "height": CARD_HEIGHT,
        "alt": card_alt(kind, site_name=site_name, checked_on=checked_on),
    }


@cache
def _font(size: int, *, display: bool = False, weight: int = 400) -> Any:
    """Bitter (display) or Atkinson Hyperlegible Next at one weight."""
    font = ImageFont.truetype(str(_DISPLAY_FONT if display else _BODY_FONT), size)
    font.set_variation_by_axes([weight])
    return font


def _cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 24,
) -> list[tuple[float, float]]:
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append(
            (
                u**3 * p0[0]
                + 3 * u * u * t * p1[0]
                + 3 * u * t * t * p2[0]
                + t**3 * p3[0],
                u**3 * p0[1]
                + 3 * u * u * t * p1[1]
                + 3 * u * t * t * p2[1]
                + t**3 * p3[1],
            )
        )
    return out


def _fish_outline() -> list[tuple[float, float]]:
    points = [_FISH_START]
    for seg in _FISH:
        if len(seg) == 1:
            points.append(seg[0])
        else:
            points.extend(_cubic(points[-1], seg[0], seg[1], seg[2]))
    return points


def _blend(
    fg: tuple[int, int, int], bg: tuple[int, int, int], alpha: float
) -> tuple[int, int, int]:
    r, g, b = (round(f * alpha + k * (1 - alpha)) for f, k in zip(fg, bg, strict=True))
    return r, g, b


def _mark(size: int) -> Image.Image:
    """The site's mark (gold trout over two ripple rings) as a size x size
    RGBA image, drawn from the same shapes as the SVG in style.css."""
    big = size * _SUPERSAMPLE
    scale = big / 32
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    ring = (*_NAME, round(255 * _RIPPLE_OPACITY))
    half = _RIPPLE_WIDTH * scale / 2
    for cx, cy, rx, ry in _RIPPLES:
        draw.ellipse(
            (
                (cx - rx) * scale - half,
                (cy - ry) * scale - half,
                (cx + rx) * scale + half,
                (cy + ry) * scale + half,
            ),
            outline=ring,
            width=round(_RIPPLE_WIDTH * scale),
        )
    draw.polygon([(x * scale, y * scale) for x, y in _fish_outline()], fill=_NAME)
    for cx, cy, r in _FISH_DOTS:
        draw.ellipse(
            ((cx - r) * scale, (cy - r) * scale, (cx + r) * scale, (cy + r) * scale),
            fill=_TOP,
        )
    return img.resize((size, size), Image.Resampling.LANCZOS)


@cache
def _background() -> Image.Image:
    """The teal ground, the mark and the stripe. Cached: the same for every
    card."""
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT))
    px = ImageDraw.Draw(img)
    ground = CARD_HEIGHT - STRIPE_HEIGHT
    for y in range(ground):
        t = y / (ground - 1)
        px.line(
            [(0, y), (CARD_WIDTH, y)],
            fill=tuple(
                round(a + (b - a) * t) for a, b in zip(_TOP, _BOTTOM, strict=True)
            ),
        )
    y = ground
    for token, height in STRIPE:
        px.rectangle((0, y, CARD_WIDTH, y + height - 1), fill=_rgb(PALETTE[token]))
        y += height
    mark = _mark(_MARK_SIZE)
    img.paste(mark, (_MARK_X, (ground - _MARK_SIZE) // 2), mark)
    return img


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, width: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and draw.textlength(trial, font=font) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def render_card(kind: str, *, site_name: str, checked_on: str) -> bytes:
    """The PNG bytes for one kind. Deterministic: same input, same bytes.

    Raises ValueError if a kind's copy runs into the freshness line, so a
    new kind with long copy fails the build instead of shipping overlapped
    text."""
    if kind not in CARD_KINDS:
        raise ValueError(f"unknown share card kind {kind!r}")
    c = CARD_KINDS[kind]
    img = _background().copy()
    draw = ImageDraw.Draw(img)
    width = _TEXT_RIGHT - _TEXT_X
    y = 64
    draw.text(
        (_TEXT_X, y), site_name, font=_font(44, display=True, weight=800), fill=_NAME
    )
    y += 92
    title_font = _font(54, display=True, weight=800)
    for line in _wrap(draw, c.title, title_font, width):
        draw.text((_TEXT_X, y), line, font=title_font, fill=_TITLE)
        y += 66
    y += 18
    sub_font = _font(32)
    for line in _wrap(draw, c.subtitle, sub_font, width):
        draw.text((_TEXT_X, y), line, font=sub_font, fill=_BODY)
        y += 44
    if y > _FRESHNESS_Y:
        raise ValueError(f"share card {kind!r}: the copy runs into the date line")
    draw.text(
        (_TEXT_X, _FRESHNESS_Y),
        freshness_line(checked_on),
        font=_font(30),
        fill=_MUTED,
    )
    return _png_bytes(img)


def _png_bytes(img: Image.Image) -> bytes:
    import io

    buf = io.BytesIO()
    img.quantize(colors=256, dither=Image.Dither.FLOYDSTEINBERG).save(
        buf, format="PNG", optimize=True
    )
    return buf.getvalue()


def write_cards(
    out_dir: Path,
    kinds: list[str],
    *,
    site_name: str,
    checked_on: str,
    written: list[Path],
) -> None:
    """Write assets/share/<kind>.png for each kind in use."""
    card_dir = out_dir / CARD_DIR
    card_dir.mkdir(parents=True, exist_ok=True)
    for kind in kinds:
        path = card_dir / card_filename(kind)
        path.write_bytes(render_card(kind, site_name=site_name, checked_on=checked_on))
        written.append(path)
