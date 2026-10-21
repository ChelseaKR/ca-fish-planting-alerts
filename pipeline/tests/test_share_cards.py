"""Share cards (1200x630 link-preview images): one per kind of page.

Checks the generator on its own (size, determinism, wording) and the built
site (which kind each page type names, that every named file exists, and that
the set of files stays small). Negative controls apply their sabotage and
assert it took effect before asserting the check notices.
"""

from __future__ import annotations

import datetime as dt
import struct
from html.parser import HTMLParser
from pathlib import Path

import pytest

from cfpa import cli, share_cards, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# The sizes a 580-page site must stay under: one card is ~30 KB, so ten of
# them are well inside this. A per-page card would blow past it.
MAX_CARD_BYTES = 60_000
MAX_CARD_FILES = 10


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == PNG_MAGIC
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


class _Meta(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        a = dict(attrs)
        key = a.get("property") or a.get("name")
        if key and a.get("content") is not None:
            self.tags[key] = a["content"] or ""


def _meta(path: Path) -> dict[str, str]:
    p = _Meta()
    p.feed(path.read_text(encoding="utf-8"))
    return p.tags


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("share-cards")
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=("TN", "MA", "MI"),
        states_fixtures=FIXTURES / "states",
    )
    return root / "site"


# ---- the generator ---------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(share_cards.CARD_KINDS))
def test_every_kind_renders_a_1200_by_630_png(kind: str) -> None:
    data = share_cards.render_card(
        kind, site_name="Trout Truck", checked_on="2026-10-21"
    )
    assert _png_size(data) == (1200, 630)
    assert len(data) < MAX_CARD_BYTES


def test_rendering_is_deterministic() -> None:
    a = share_cards.render_card(
        "water", site_name="Trout Truck", checked_on="2026-10-21"
    )
    b = share_cards.render_card(
        "water", site_name="Trout Truck", checked_on="2026-10-21"
    )
    assert a == b


def test_the_freshness_date_changes_the_image() -> None:
    a = share_cards.render_card(
        "home", site_name="Trout Truck", checked_on="2026-10-21"
    )
    b = share_cards.render_card(
        "home", site_name="Trout Truck", checked_on="2026-10-22"
    )
    assert a != b


def test_freshness_line_is_american_english_and_dated() -> None:
    assert share_cards.freshness_line("2026-10-21") == "Schedule checked Oct 21, 2026"
    assert share_cards.freshness_line("2026-09-03T12:00:00Z") == (
        "Schedule checked Sep 3, 2026"
    )


def _wording_problems(kinds: dict[str, share_cards.CardKind]) -> list[str]:
    out = []
    for kind, c in kinds.items():
        alt = share_cards.card_alt(
            kind, site_name="Trout Truck", checked_on="2026-10-21"
        )
        text = f"{c.title} {c.subtitle} {alt}".lower()
        if "stock" in text:
            out.append(f"{kind}: says stocked")
        if "colour" in text or "favour" in text:
            out.append(f"{kind}: British spelling")
    return out


def test_cards_say_scheduled_and_never_stocked() -> None:
    assert _wording_problems(share_cards.CARD_KINDS) == []
    assert "scheduled" in share_cards.CARD_KINDS["water"].title.lower()


def test_control_a_card_that_says_stocked_is_caught() -> None:
    sabotaged = {
        **share_cards.CARD_KINDS,
        "water": share_cards.CardKind("Stocked trout", "x"),
    }
    assert sabotaged["water"].title == "Stocked trout"  # the sabotage applied
    assert _wording_problems(sabotaged) == ["water: says stocked"]


def test_the_alt_text_carries_every_sentence_the_card_shows() -> None:
    alt = share_cards.card_alt(
        "water", site_name="Trout Truck", checked_on="2026-10-21"
    )
    c = share_cards.CARD_KINDS["water"]
    assert (
        alt == f"Trout Truck. {c.title}. {c.subtitle}. Schedule checked Oct 21, 2026."
    )


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown share card kind"):
        share_cards.render_card(
            "nope", site_name="Trout Truck", checked_on="2026-10-21"
        )
    with pytest.raises(ValueError, match="unknown share card kind"):
        share_cards.card_filename("nope")


# ---- the built site --------------------------------------------------------


def test_the_build_writes_a_handful_of_small_cards_not_one_per_page(
    built: Path,
) -> None:
    cards = sorted((built / "assets" / "share").glob("*.png"))
    assert [c.name for c in cards] == [
        "county.png",
        "home.png",
        "region.png",
        "species.png",
        "state.png",
        "water.png",
    ]
    assert len(cards) <= MAX_CARD_FILES
    for c in cards:
        assert _png_size(c.read_bytes()) == (1200, 630)
        assert c.stat().st_size < MAX_CARD_BYTES
    assert len(list(built.rglob("index.html"))) > 20 * len(cards)


@pytest.mark.parametrize(
    ("rel", "kind"),
    [
        ("index.html", "home"),
        ("about/index.html", "home"),
        ("county/index.html", "county"),
        ("states/index.html", "state"),
        ("species/trout/index.html", "species"),
    ],
)
def test_each_page_type_names_its_kinds_card(built: Path, rel: str, kind: str) -> None:
    tags = _meta(built / rel)
    assert tags["og:image"] == f"{BASE_URL}/assets/share/{kind}.png"
    assert tags["twitter:image"] == tags["og:image"]
    assert tags["twitter:card"] == "summary_large_image"
    assert (tags["og:image:width"], tags["og:image:height"]) == ("1200", "630")
    assert tags["og:image:alt"] == tags["twitter:image:alt"]
    assert "Schedule checked Sep 13, 2026" in tags["og:image:alt"]


def test_county_water_and_state_pages_use_their_own_cards(built: Path) -> None:
    def card(glob: str) -> set[str]:
        files = sorted(built.glob(glob))
        assert files, glob
        return {_meta(f)["og:image"].rsplit("/", 1)[1] for f in files}

    assert card("county/*/index.html") == {"county.png"}
    assert card("water/*/index.html") == {"water.png"}
    assert card("region/*/index.html") == {"region.png"}
    assert card("tn/index.html") == {"state.png"}
    assert card("tn/water/*/index.html") == {"state.png"}


def test_control_a_page_naming_a_missing_kind_fails_the_build(tmp_path: Path) -> None:
    """Negative control: sabotage the kind list, assert it applied, then see it
    fail loudly (a template naming a kind with no card must not ship a dead
    og:image)."""
    saved = dict(share_cards.CARD_KINDS)
    try:
        del share_cards.CARD_KINDS["water"]
        assert "water" not in share_cards.CARD_KINDS  # the sabotage applied
        with pytest.raises(ValueError, match="unknown share card kind"):
            share_cards.card_filename("water")
    finally:
        share_cards.CARD_KINDS.update(saved)
    assert "water" in share_cards.CARD_KINDS


def test_a_california_only_build_writes_no_state_card(tmp_path: Path) -> None:
    root = tmp_path
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    names = {p.name for p in (root / "site" / "assets" / "share").glob("*.png")}
    assert names == {"county.png", "home.png", "region.png", "species.png", "water.png"}
    assert site.SHARE_CARD_DEFAULT_KIND == "home"
