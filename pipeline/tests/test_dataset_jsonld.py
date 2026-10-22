"""Every page's ld+json parses, and every Dataset follows schema.org's rules.

Built from the pinned fixtures. The validator is a plain function so a
negative control can run it on a sabotaged copy and assert it objects.
Checked per Dataset node: name, description, url, creator, distribution
(each entry with contentUrl and encodingFormat), isBasedOn with the
agency's terms, temporalCoverage as a schema.org interval, and every URL the
site mints on the site's own host. Absence is never rendered as a value: a
key is either present with real content or not there at all.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from cfpa import cli

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
V1_SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
OWN_HOST = urlparse(BASE).netloc
PLACEHOLDERS = {"", "n/a", "na", "none", "null", "unknown", "tbd", "0", "-"}
INTERVAL = re.compile(r"^\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}$")


class _LdScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self._in = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self._in = True
            self.blocks.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in = False

    def handle_data(self, data: str) -> None:
        if self._in:
            self.blocks[-1] += data


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("jsonld")
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=V1_SCHEMA,
        site_out=root / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=("TN",),
        states_fixtures=FIXTURES / "states",
    )
    return root / "site"


def _blocks(html: Path) -> list[Any]:
    p = _LdScripts()
    p.feed(html.read_text("utf-8"))
    return [json.loads(b) for b in p.blocks]


def _nodes(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, dict) and "@graph" in doc:
        return list(doc["@graph"])
    return [doc]


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in PLACEHOLDERS
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _own(url: str) -> bool:
    return urlparse(url).netloc == OWN_HOST


def _check_required(node: dict[str, Any]) -> list[str]:
    bad: list[str] = []
    for key in ("name", "description", "url", "creator", "distribution", "isBasedOn"):
        if _empty(node.get(key)):
            bad.append(f"{key} missing or empty")
    for key, value in node.items():
        if not key.startswith("@") and _empty(value):
            bad.append(f"{key} rendered as an empty value")
    if len(str(node.get("description", ""))) < 50:
        bad.append("description shorter than 50 characters")
    cov = node.get("temporalCoverage")
    if cov is not None and not INTERVAL.match(str(cov)):
        bad.append("temporalCoverage is not an ISO interval")
    return bad


def _check_hosts(node: dict[str, Any]) -> list[str]:
    bad = [
        f"{key} not on the site's own host"
        for key in ("url", "@id")
        if key in node and not _own(str(node[key]))
    ]
    creator = node.get("creator")
    if isinstance(creator, dict) and not _own(str(creator.get("url", ""))):
        bad.append("creator url not on the site's own host")
    for d in node.get("distribution") or []:
        if d.get("@type") != "DataDownload":
            bad.append("distribution entry is not a DataDownload")
        if not _own(str(d.get("contentUrl", ""))):
            bad.append("contentUrl not on the site's own host")
        if _empty(d.get("encodingFormat")):
            bad.append("distribution entry has no encodingFormat")
    return bad


def _check_source(node: dict[str, Any]) -> list[str]:
    based = node.get("isBasedOn")
    if not isinstance(based, dict):
        return []
    bad: list[str] = []
    if not str(based.get("url", "")).startswith("https://"):
        bad.append("isBasedOn has no https url")
    if not str(based.get("license", "")).startswith("https://"):
        bad.append("isBasedOn has no https terms link")
    if _empty(based.get("creator")):
        bad.append("isBasedOn has no creator")
    return bad


def check_dataset(node: dict[str, Any]) -> list[str]:
    """Return every problem found in one Dataset node."""
    return _check_required(node) + _check_hosts(node) + _check_source(node)


def _all_pages(site_dir: Path) -> list[Path]:
    return sorted(site_dir.rglob("index.html"))


def test_every_page_ld_json_parses_and_has_a_context(built: Path) -> None:
    pages = _all_pages(built)
    assert len(pages) > 10
    with_ld = 0
    for html in pages:
        for doc in _blocks(html):
            with_ld += 1
            assert doc["@context"] == "https://schema.org", html
            for node in _nodes(doc):
                assert node.get("@type"), html
    assert with_ld > 10


def test_every_dataset_node_passes_the_checks(built: Path) -> None:
    seen: list[str] = []
    for html in _all_pages(built):
        for doc in _blocks(html):
            for node in _nodes(doc):
                if node.get("@type") == "Dataset":
                    assert check_dataset(node) == [], (html, node.get("@id"))
                    seen.append(node["@id"])
    assert f"{BASE}/data/#ca" in seen
    assert f"{BASE}/data/#tn" in seen
    assert f"{BASE}/about/#data" in seen


def test_no_license_is_claimed_that_the_site_has_not_chosen(built: Path) -> None:
    for html in _all_pages(built):
        for doc in _blocks(html):
            for node in _nodes(doc):
                if node.get("@type") == "Dataset":
                    assert "license" not in node, html


# ---- negative controls: each sabotage is asserted to apply, then caught


def _good(built: Path) -> dict[str, Any]:
    (doc,) = _blocks(built / "data" / "index.html")
    return copy.deepcopy(_nodes(doc)[0])


def test_control_a_baseline_node_is_clean(built: Path) -> None:
    assert check_dataset(_good(built)) == []


@pytest.mark.parametrize(
    ("sabotage", "expect"),
    [
        (lambda n: n.pop("description"), "description missing"),
        (lambda n: n.update(temporalCoverage="N/A"), "temporalCoverage"),
        (lambda n: n.update(temporalCoverage=""), "empty value"),
        (
            lambda n: n["distribution"][0].update(contentUrl="https://evil.test/x.csv"),
            "own host",
        ),
        (lambda n: n["distribution"][0].pop("encodingFormat"), "encodingFormat"),
        (lambda n: n["isBasedOn"].pop("license"), "terms link"),
        (lambda n: n.update(spatialCoverage=None), "empty value"),
        (lambda n: n.update(dateModified="0"), "empty value"),
    ],
)
def test_control_the_checker_catches_each_sabotage(
    built: Path, sabotage: Any, expect: str
) -> None:
    node = _good(built)
    before = json.dumps(node, sort_keys=True)
    sabotage(node)
    assert json.dumps(node, sort_keys=True) != before, "sabotage did not apply"
    problems = check_dataset(node)
    assert any(expect in p for p in problems), problems
