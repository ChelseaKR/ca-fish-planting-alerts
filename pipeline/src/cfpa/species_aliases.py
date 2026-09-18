"""The species normalization table: mirrors ``aliases.py``'s water-name
table, adapted for the one real difference -- CDFW's schedule table gives
waters a stable identifier (the ``stockid`` in the map link) but gives
species nothing but free text. There is no id to key a species catalog by,
and no id to prove two differently-spelled strings name the same species.

So unlike ``AliasTable`` (which *auto-discovers* every new spelling it sees
for a known stock id, because the id already proves it's the same water),
this table is purely hand-curated: it starts empty, and only grows when a
human notices CDFW has actually respelled a species and adds an entry
mapping every known spelling to one canonical name. Until that happens,
every observed species string just normalizes to itself -- exactly today's
behavior for the only two values real data has ever shown, "Trout" and
"Catfish".

Loaded from ``pipeline/data/species_aliases.json``, committed to version
control the same way ``aliases.json`` is, so any curation is a reviewable
``git diff``.

Why this matters: ``species`` is not just a display string. It is one third
of a history record's identity (``cdfw_stock_id``, ``week_start``,
``species`` -- see ``history.py``). If CDFW ever spelled the same species
two different ways across two runs, without normalization that would not
just mislabel a plant -- it would look to ``merge_observations`` like the
first spelling's plant was *removed* and a brand-new species was *added* in
its place, even though nothing about the real stocking changed. Normalizing
species text before it is used to build a history key closes that gap.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_WS_RE = re.compile(r"\s+")


def slugify(name: str) -> str:
    s = _SLUG_RE.sub("-", name.lower()).strip("-")
    return s or "species"


def _clean(raw: str) -> str:
    """Collapse/trim whitespace only -- the one normalization that is always
    mechanically safe. Anything beyond that (a genuinely different spelling,
    a capitalization variant) requires a curated alias entry, the same way
    ``AliasTable`` never auto-fixes a water name's whitespace either (see
    ``test_new_spelling_of_a_known_id_is_reported_unmatched`` in
    test_aliases.py) -- it just records it and leaves merging to a human."""
    return _WS_RE.sub(" ", raw).strip()


@dataclasses.dataclass(slots=True)
class SpeciesAlias:
    canonical_name: str
    slug: str
    aliases: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "slug": self.slug,
            "aliases": self.aliases,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> SpeciesAlias:
        return cls(
            canonical_name=d["canonical_name"],
            slug=d["slug"],
            aliases=list(d["aliases"]),
        )


@dataclasses.dataclass(slots=True)
class SpeciesAliasTable:
    entries: list[SpeciesAlias]

    @classmethod
    def load(cls, path: Path) -> SpeciesAliasTable:
        if not path.exists():
            return cls(entries=[])
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(entries=[SpeciesAlias.from_json(e) for e in data.get("species", [])])

    def save(self, path: Path) -> None:
        payload = {
            "schema": "cfpa-species-aliases-v1",
            "species": [
                e.to_json() for e in sorted(self.entries, key=lambda e: e.slug)
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def normalize(self, observed_name: str) -> str:
        """Return the canonical species name for one observed raw string.

        Whitespace is collapsed/trimmed first (always safe). The cleaned
        string is then matched, exact, against every alias spelling any
        curated entry lists; if found, that entry's canonical_name wins.
        Otherwise the cleaned string is returned unchanged -- a species with
        no curated entry is its own canonical name, which is exactly what
        every species in the real data is today.
        """
        cleaned = _clean(observed_name)
        for entry in self.entries:
            if cleaned in entry.aliases:
                return entry.canonical_name
        return cleaned
