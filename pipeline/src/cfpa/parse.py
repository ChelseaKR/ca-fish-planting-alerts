"""Parse the CDFW schedule table into rows.

The table format will drift eventually (it's someone else's ASP.NET app).
Every assumption here is checked; on drift we raise ParseError rather than
emit a partial table as if it were complete. A silent partial parse would be
worse than no data: it would look like a real (low) week.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import re

STOCKID_RE = re.compile(r"stockid=(\d+)")
WEEK_RANGE_RE = re.compile(
    r"(\d{1,2})/(\d{1,2})/(\d{4})\s*-\s*(\d{1,2})/(\d{1,2})/(\d{4})"
)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


class ParseError(RuntimeError):
    """The table did not match the expected shape. Fail loudly."""


@dataclasses.dataclass(frozen=True, slots=True)
class RawRow:
    week_start: dt.date
    week_end: dt.date
    cdfw_stock_id: int
    water_name: str
    counties: tuple[str, ...]
    species: str


def _strip_tags(fragment: str) -> str:
    return WS_RE.sub(" ", html.unescape(TAG_RE.sub(" ", fragment))).strip()


def _parse_week(cell_html: str) -> tuple[dt.date, dt.date]:
    m = WEEK_RANGE_RE.search(cell_html)
    if not m:
        raise ParseError(
            f"'Week of Plant' cell did not match <m>/<d>/<y>-<m>/<d>/<y>: {cell_html!r}"
        )
    m1, d1, y1, m2, d2, y2 = (int(g) for g in m.groups())
    start = dt.date(y1, m1, d1)
    end = dt.date(y2, m2, d2)
    if end != start + dt.timedelta(days=6):
        raise ParseError(
            f"week range is not exactly 7 days (Sunday..Saturday): {start} - {end}"
        )
    if start.weekday() != 6:  # Python: Monday=0 .. Sunday=6
        raise ParseError(f"week start {start} is not a Sunday (CDFW's own week shape)")
    return start, end


def _parse_water_cell(cell_html: str) -> tuple[int, str]:
    m = STOCKID_RE.search(cell_html)
    if not m:
        raise ParseError(
            f"'Water Name' cell has no stockid= map link -- id source lost: {cell_html!r}"
        )
    stock_id = int(m.group(1))
    name = _strip_tags(cell_html)
    name = re.sub(r"\s*View Water Body in Map\s*$", "", name).strip()
    if not name:
        raise ParseError(f"water name is empty after stripping markup: {cell_html!r}")
    return stock_id, name


def parse_schedule_table(html_doc: str) -> list[RawRow]:
    """Parse every row of the '#fishPlantsExternal' table.

    Raises ParseError on any structural surprise: missing table, wrong
    column count, unparseable cell. Never returns a partial list silently --
    either every row parses, or the function raises.
    """
    table_m = re.search(
        r'(?s)<table[^>]*id="fishPlantsExternal"[^>]*>(.*?)</table>', html_doc
    )
    if not table_m:
        raise ParseError("no <table id=\"fishPlantsExternal\"> found in the page")
    table_html = table_m.group(1)

    thead_m = re.search(r"(?s)<thead>(.*?)</thead>", table_html)
    if not thead_m:
        raise ParseError("schedule table has no <thead>")
    headers = [_strip_tags(h) for h in re.findall(r"(?s)<th[^>]*>(.*?)</th>", thead_m.group(1))]
    expected_headers = ["Week of Plant", "Water Name", "Counties", "Species"]
    if headers != expected_headers:
        raise ParseError(f"table headers changed: expected {expected_headers}, got {headers}")

    tbody_m = re.search(r"(?s)<tbody>(.*?)</tbody>", table_html)
    if not tbody_m:
        raise ParseError("schedule table has no <tbody>")

    row_htmls = re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", tbody_m.group(1))
    if not row_htmls:
        raise ParseError(
            "schedule table body has zero rows -- refusing to treat as 'no plants'; "
            "this is a parse/format problem, not a real empty week"
        )

    rows: list[RawRow] = []
    for i, row_html in enumerate(row_htmls):
        cells = re.findall(r"(?s)<td[^>]*>(.*?)</td>", row_html)
        if len(cells) != len(expected_headers):
            raise ParseError(
                f"row {i} has {len(cells)} <td> cells, expected {len(expected_headers)}: "
                f"{row_html!r}"
            )
        week_start, week_end = _parse_week(cells[0])
        stock_id, name = _parse_water_cell(cells[1])
        counties_text = _strip_tags(cells[2])
        if not counties_text:
            raise ParseError(f"row {i} has an empty Counties cell for {name!r}")
        counties = tuple(c.strip() for c in counties_text.split(",") if c.strip())
        species = _strip_tags(cells[3])
        if not species:
            raise ParseError(f"row {i} has an empty Species cell for {name!r}")

        rows.append(
            RawRow(
                week_start=week_start,
                week_end=week_end,
                cdfw_stock_id=stock_id,
                water_name=name,
                counties=counties,
                species=species,
            )
        )
    return rows


@dataclasses.dataclass(frozen=True, slots=True)
class SelectOption:
    value: str
    label: str


def parse_select_options(html_doc: str, select_id: str) -> list[SelectOption]:
    """Parse a <select id="..."> element's <option>s (used for coverage: how
    many waters CDFW's own picker knows about, region and county lists)."""
    sel_m = re.search(
        rf'(?s)<select[^>]*id="{re.escape(select_id)}"[^>]*>(.*?)</select>', html_doc
    )
    if not sel_m:
        raise ParseError(f"no <select id=\"{select_id}\"> found in the page")
    opts = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>\s*([^<]*?)\s*</option>', sel_m.group(1))
    return [SelectOption(value=v, label=html.unescape(lbl)) for v, lbl in opts if v]
