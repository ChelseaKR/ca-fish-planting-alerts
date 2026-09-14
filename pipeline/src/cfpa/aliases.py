"""The alias table: CDFW's own numeric stock id is the stable identifier,
but the *display* name and its spellings still need curation.

CDFW spells waters inconsistently across the calendar (capitalisation,
"Upper"/"upper", punctuation) even though the ``stockid`` in the map link
stays the same. On 2026-09-13, five published names each covered two or
three *different* stock ids ("Silver Lake", "Bass Lake", "Deer Creek",
"Sacramento River", "Blue Lake Upper") -- distinct physical waters sharing a
name. The id, not the name, is what makes a water stable.

This module keeps a per-id table of every spelling ever seen, a curated
canonical display name, and a slug that -- once assigned -- never changes
even if CDFW respells the water later. It is loaded from and saved back to
``pipeline/data/aliases.json``, which is committed to version control so the
alias history is reviewable in ``git log``.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = _SLUG_RE.sub("-", name.lower()).strip("-")
    return s or "water"


@dataclasses.dataclass(slots=True)
class WaterAlias:
    cdfw_stock_id: int
    canonical_name: str
    slug: str
    aliases: list[str]
    reviewed: bool = False

    def to_json(self) -> dict:
        return {
            "cdfw_stock_id": self.cdfw_stock_id,
            "canonical_name": self.canonical_name,
            "slug": self.slug,
            "aliases": self.aliases,
            "reviewed": self.reviewed,
        }

    @classmethod
    def from_json(cls, d: dict) -> "WaterAlias":
        return cls(
            cdfw_stock_id=int(d["cdfw_stock_id"]),
            canonical_name=d["canonical_name"],
            slug=d["slug"],
            aliases=list(d["aliases"]),
            reviewed=bool(d.get("reviewed", False)),
        )


@dataclasses.dataclass(slots=True)
class AliasTable:
    by_id: dict[int, WaterAlias]

    @classmethod
    def load(cls, path: Path) -> "AliasTable":
        if not path.exists():
            return cls(by_id={})
        data = json.loads(path.read_text(encoding="utf-8"))
        by_id = {}
        for entry in data.get("waters", []):
            wa = WaterAlias.from_json(entry)
            by_id[wa.cdfw_stock_id] = wa
        return cls(by_id=by_id)

    def save(self, path: Path) -> None:
        waters = [self.by_id[k].to_json() for k in sorted(self.by_id)]
        payload = {"schema": "cfpa-aliases-v1", "waters": waters}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def used_slugs(self) -> set[str]:
        return {wa.slug for wa in self.by_id.values()}

    def apply(self, stock_id: int, published_name: str) -> tuple[WaterAlias, bool]:
        """Match one observed (stock_id, name) against the table.

        Returns (alias_entry, matched). ``matched`` is True iff this exact
        spelling was already known for this id *before* this call -- i.e. it
        is False both for a brand-new water and for a known water with a
        newly-observed spelling. Either way, the table is updated in memory
        (call .save() to persist) so a name seen once is matched on every
        later run.
        """
        existing = self.by_id.get(stock_id)
        if existing is None:
            slug_base = slugify(published_name)
            slug = slug_base
            n = 2
            used = self.used_slugs()
            while slug in used:
                slug = f"{slug_base}-{n}"
                n += 1
            entry = WaterAlias(
                cdfw_stock_id=stock_id,
                canonical_name=published_name,
                slug=slug,
                aliases=[published_name],
                reviewed=False,
            )
            self.by_id[stock_id] = entry
            return entry, False

        if published_name in existing.aliases:
            return existing, True

        existing.aliases.append(published_name)
        existing.reviewed = False
        return existing, False


@dataclasses.dataclass(frozen=True, slots=True)
class MatchReport:
    names_seen: int
    names_matched: int
    unmatched: list[tuple[int, str]]  # (stock_id, name) newly seen this run

    @property
    def names_unmatched(self) -> int:
        return len(self.unmatched)

    def print_report(self) -> None:
        print(f"names seen: {self.names_seen}  names matched: {self.names_matched}  "
              f"unmatched: {self.names_unmatched}")
        for stock_id, name in self.unmatched:
            print(f"  UNMATCHED cdfw-{stock_id}: {name!r}")


def apply_all(table: AliasTable, observed: list[tuple[int, str]]) -> MatchReport:
    """Apply every observed (stock_id, name) pair from this run's rows.

    ``observed`` may contain duplicates (many weeks, same water); dedupe by
    the pair before counting, so "names seen" means distinct spellings, not
    distinct rows.
    """
    distinct = sorted(set(observed))
    unmatched: list[tuple[int, str]] = []
    matched_count = 0
    for stock_id, name in distinct:
        _, matched = table.apply(stock_id, name)
        if matched:
            matched_count += 1
        else:
            unmatched.append((stock_id, name))
    return MatchReport(names_seen=len(distinct), names_matched=matched_count, unmatched=unmatched)
