"""Whether a water is still or moving, read from the agency's own name for it
(DECISIONS 0045).

The data carries no lake-or-stream field, but the names the agencies publish
nearly always end in one: "Collins Lake", "Kings River, Below Pine Flat Dam",
"Pine Creek Reservoir". The gear block uses the answer to pick searches that
fit the water (bait and bobbers at a lake, spinners and waders on a stream).
A name with neither kind of word gets ``None``, and the page keeps the
general four searches: an unknown kind is never guessed.

Only the part before the first comma counts ("Trinity River, above Clair
Engle Lake" is a river), and within it the last kind word wins ("Pine Creek
Reservoir" is a reservoir, "Rock Creek Lake" a lake).
"""

from __future__ import annotations

import re
from typing import Literal

WaterKind = Literal["still", "moving"]

STILL_WORDS = frozenset(
    {
        "lake",
        "lakes",
        "pond",
        "ponds",
        "reservoir",
        "forebay",
        "afterbay",
        "lagoon",
        "pool",
        "basin",
    }
)
MOVING_WORDS = frozenset({"river", "creek", "stream", "fork", "canal", "slough"})

_WORD = re.compile(r"[a-z]+")


def water_kind(name: str) -> WaterKind | None:
    """``"still"``, ``"moving"``, or ``None`` when the name does not say."""
    head = name.split(",", 1)[0].lower()
    kind: WaterKind | None = None
    for word in _WORD.findall(head):
        if word in STILL_WORDS:
            kind = "still"
        elif word in MOVING_WORDS:
            kind = "moving"
    return kind
