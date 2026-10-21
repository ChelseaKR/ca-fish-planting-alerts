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

Rendering uses Pillow with the font Pillow itself ships (Aileron, CC0). No
font file is committed and none is fetched. The icon on each card is the
app icon already in the package (``social-card.png``).
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

# The icon's own background gradient (top and bottom edge pixels), so the
# card and the icon meet without a seam.
_TOP = (15, 122, 76)
_BOTTOM = (8, 64, 42)
_TITLE = (255, 255, 255)
_BODY = (214, 236, 223)
_MUTED = (190, 220, 202)
_ICON_SIZE = 380
_TEXT_X = 520
_TEXT_RIGHT = CARD_WIDTH - 60

_ICON_FILE = Path(__file__).parent / "templates" / "social-card.png"


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
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size)


@cache
def _background() -> Image.Image:
    """The gradient with the icon on it. Cached: it is the same for every card."""
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT))
    px = ImageDraw.Draw(img)
    for y in range(CARD_HEIGHT):
        t = y / (CARD_HEIGHT - 1)
        px.line(
            [(0, y), (CARD_WIDTH, y)],
            fill=tuple(
                round(a + (b - a) * t) for a, b in zip(_TOP, _BOTTOM, strict=True)
            ),
        )
    icon = Image.open(_ICON_FILE).convert("RGB")
    icon = icon.resize((_ICON_SIZE, _ICON_SIZE), Image.Resampling.LANCZOS)
    # Rounded like an app icon, so its own gradient edge never shows as a box.
    mask = Image.new("L", (_ICON_SIZE, _ICON_SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, _ICON_SIZE - 1, _ICON_SIZE - 1), radius=84, fill=255
    )
    img.paste(icon, (70, (CARD_HEIGHT - _ICON_SIZE) // 2), mask)
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
    """The PNG bytes for one kind. Deterministic: same input, same bytes."""
    if kind not in CARD_KINDS:
        raise ValueError(f"unknown share card kind {kind!r}")
    c = CARD_KINDS[kind]
    img = _background().copy()
    draw = ImageDraw.Draw(img)
    width = _TEXT_RIGHT - _TEXT_X
    y = 70
    draw.text((_TEXT_X, y), site_name, font=_font(40), fill=_MUTED)
    y += 90
    title_font = _font(58)
    for line in _wrap(draw, c.title, title_font, width):
        draw.text((_TEXT_X, y), line, font=title_font, fill=_TITLE)
        y += 70
    y += 20
    sub_font = _font(34)
    for line in _wrap(draw, c.subtitle, sub_font, width):
        draw.text((_TEXT_X, y), line, font=sub_font, fill=_BODY)
        y += 46
    draw.text(
        (_TEXT_X, CARD_HEIGHT - 90),
        freshness_line(checked_on),
        font=_font(32),
        fill=_MUTED,
    )
    out = _png_bytes(img)
    return out


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
