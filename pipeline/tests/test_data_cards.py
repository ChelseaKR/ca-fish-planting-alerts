"""Every source the pipeline ingests has a complete data card (DG-01).

DATA-GOVERNANCE-STANDARD §1 asks for one committed card per ingest source
under docs/data/, enumerated against the repository's declared source list.
Here that list is the set of URLs the pipeline fetches data from
(`INGEST_SOURCES`), so adding a new source to fetch.py without a card, or
writing a card that leaves out a field, fails this test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cfpa import fetch

REPO_ROOT = Path(__file__).resolve().parents[2]
CARDS_DIR = REPO_ROOT / "docs" / "data"

# Data sources, not every URL fetch.py touches: robots.txt is read to decide
# whether a fetch is allowed and contributes no data.
INGEST_SOURCES = (fetch.SCHEDULE_URL,)

REQUIRED_SECTIONS = (
    "Source",
    "License",
    "Fetch/refresh cadence",
    "Fetch timestamp",
    "Tier",
    "Known limitations",
    "Retention",
)


def _cards() -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8") for p in sorted(CARDS_DIR.glob("*.md"))}


def _sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## +(.+?)\s*$", text, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts), 2)}


def test_there_is_at_least_one_card() -> None:
    assert _cards(), f"no data cards under {CARDS_DIR}"


@pytest.mark.parametrize("url", INGEST_SOURCES)
def test_every_ingest_source_has_exactly_one_card(url: str) -> None:
    naming = [
        p.name
        for p, text in _cards().items()
        if url in _sections(text).get("Source", "")
    ]
    assert len(naming) == 1, f"{url}: named in the Source section of {naming}"


@pytest.mark.parametrize("card", sorted(CARDS_DIR.glob("*.md")), ids=lambda p: p.name)
def test_every_card_has_every_required_section_filled(card: Path) -> None:
    sections = _sections(card.read_text(encoding="utf-8"))
    missing = [s for s in REQUIRED_SECTIONS if not sections.get(s)]
    assert not missing, f"{card.name} is missing or has empty: {missing}"


@pytest.mark.parametrize("card", sorted(CARDS_DIR.glob("*.md")), ids=lambda p: p.name)
def test_every_card_states_its_tier(card: Path) -> None:
    tier = _sections(card.read_text(encoding="utf-8")).get("Tier", "")
    assert re.search(r"\bL[0-3]\b", tier), (
        f"{card.name}: Tier section names no L0-L3 tier"
    )
