"""The move to a custom domain (DECISIONS 0019).

Three promises, each checked against a real fixture build:

1. With no custom domain (SITE_BASE_URL unset), nothing changes: no CNAME,
   no github.io redirect site, and the site is built for the github.io URL.
   (That the bytes are identical to the build before this existed was
   measured by hashing both builds; see the pull request.)
2. With a custom domain, every URL the site states about itself (canonical,
   og:url, structured data, sitemap, robots.txt, calendar feeds) uses the
   domain, CNAME names it, and nothing in the build mentions github.io.
3. The github.io site built beside it keeps the iOS app's snapshot and every
   calendar feed byte for byte, at the same paths, and turns every page into
   a redirect to the same page on the domain.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, legacy, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
DOMAIN = "trouttruck.example"
DOMAIN_URL = f"https://{DOMAIN}"
LEGACY = "https://chelseakr.github.io/ca-fish-planting-alerts"

_URL = re.compile(r"""https?://[^\s"'<>\\)]+""")
_CANONICAL = re.compile(r'<link rel="canonical" href="([^"]+)">')
_OG_URL = re.compile(r'<meta property="og:url" content="([^"]+)">')
_REFRESH = re.compile(r'<meta http-equiv="refresh" content="0; url=([^"]+)">')
_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_LOC = re.compile(r"<loc>([^<]+)</loc>")


def _run(root: Path, *, base_url: str, legacy_out: Path | None = None) -> None:
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=base_url,
        legacy_site_out=legacy_out,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    # The CLI writes the snapshot; cli.run is what writes it here too.
    assert (root / "site" / "snapshot" / "v1.json").is_file()


@pytest.fixture(scope="module")
def domain_build(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("domain")
    _run(root, base_url=DOMAIN_URL, legacy_out=root / "legacy")
    return root / "site", root / "legacy"


def _files(root: Path) -> list[Path]:
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())


def _ld_urls(node: Any) -> list[str]:
    if isinstance(node, dict):
        return [u for v in node.values() for u in _ld_urls(v)]
    if isinstance(node, list):
        return [u for v in node for u in _ld_urls(v)]
    if isinstance(node, str) and node.startswith(("http://", "https://")):
        return [node]
    return []


# ---- custom_domain ---------------------------------------------------------


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://trouttruck.com", "trouttruck.com"),
        ("https://trouttruck.com/", "trouttruck.com"),
        ("https://www.trouttruck.com", "www.trouttruck.com"),
        ("https://TroutTruck.com", "trouttruck.com"),
        (LEGACY, None),
        (LEGACY + "/", None),
        ("https://chelseakr.github.io", None),
        ("https://example.invalid/ca-fish-planting-alerts", None),
        ("http://trouttruck.com", None),
        ("https://trouttruck.com:8443", None),
        ("https://trouttruck.com/?x=1", None),
        ("https://user@trouttruck.com", None),
        ("", None),
    ],
)
def test_custom_domain(base_url: str, expected: str | None) -> None:
    assert site.custom_domain(base_url) == expected


# ---- 1. unset: nothing changes --------------------------------------------


def test_without_a_domain_there_is_no_cname_and_the_site_stays_on_github_io(
    tmp_path: Path,
) -> None:
    _run(tmp_path, base_url=cli.DEFAULT_BASE_URL)
    out = tmp_path / "site"
    assert not (out / "CNAME").exists()
    assert cli.DEFAULT_BASE_URL == site.LEGACY_BASE_URL == LEGACY
    home = (out / "index.html").read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{LEGACY}/">' in home
    assert (
        (out / "robots.txt")
        .read_text(encoding="utf-8")
        .endswith(f"Sitemap: {LEGACY}/sitemap.xml\n")
    )


def test_cname_none_writes_the_same_bytes_as_no_cname_argument(
    tmp_path: Path,
) -> None:
    _run(tmp_path / "a", base_url=cli.DEFAULT_BASE_URL)
    snap = json.loads(
        (tmp_path / "a" / "site" / "snapshot" / "v1.json").read_text(encoding="utf-8")
    )
    site.build_site(snap, tmp_path / "b", base_url=cli.DEFAULT_BASE_URL)
    site.build_site(snap, tmp_path / "c", base_url=cli.DEFAULT_BASE_URL, cname=None)
    files = _files(tmp_path / "b")
    assert files == _files(tmp_path / "c")
    for rel in files:
        assert (tmp_path / "b" / rel).read_bytes() == (
            tmp_path / "c" / rel
        ).read_bytes()


@pytest.mark.parametrize("base_url", [LEGACY, "https://example.invalid/sub"])
def test_a_legacy_site_without_a_custom_domain_is_refused_before_anything_is_written(
    tmp_path: Path, base_url: str
) -> None:
    with pytest.raises(legacy.LegacySiteError):
        _run(tmp_path, base_url=base_url, legacy_out=tmp_path / "legacy")
    assert list(tmp_path.iterdir()) == []


def test_the_cli_refuses_a_legacy_site_without_a_custom_domain(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--fixture", str(FRESH), "--run-today", "2026-09-13",
            "--history", str(tmp_path / "h.json"), "--aliases", str(tmp_path / "a.json"),
            "--site-out", str(tmp_path / "site"),
            "--legacy-site-out", str(tmp_path / "legacy")]  # fmt: skip
    assert cli.main(argv) == 1
    assert "run refused" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_an_empty_legacy_site_out_is_unset(tmp_path: Path) -> None:
    # publish.yml passes "" when SITE_BASE_URL is unset.
    argv = ["--fixture", str(FRESH), "--fixture-fetched-at", "2026-09-13T12:00:00Z",
            "--run-today", "2026-09-13",
            "--history", str(tmp_path / "h.json"), "--aliases", str(tmp_path / "a.json"),
            "--site-out", str(tmp_path / "site"), "--base-url", "",
            "--legacy-site-out", ""]  # fmt: skip
    assert cli.main(argv) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.json", "h.json", "site"]
    assert not (tmp_path / "site" / "CNAME").exists()


# ---- 2. the domain build ---------------------------------------------------


def test_cname_names_the_domain(domain_build: tuple[Path, Path]) -> None:
    out, _ = domain_build
    assert (out / "CNAME").read_text(encoding="utf-8") == f"{DOMAIN}\n"


def test_nothing_in_the_domain_build_mentions_github_io(
    domain_build: tuple[Path, Path],
) -> None:
    out, _ = domain_build
    files = _files(out)
    assert len(files) > 50
    for rel in files:
        text = (out / rel).read_text(encoding="utf-8")
        assert "chelseakr.github.io" not in text, rel
        # No link keeps the github.io path prefix (the .ics PRODID names the
        # project, which is not a link, and stays as it is).
        assert '="/ca-fish-planting-alerts' not in text, rel


def test_every_url_the_site_states_about_itself_is_on_the_domain(
    domain_build: tuple[Path, Path],
) -> None:
    out, _ = domain_build
    own: list[str] = []
    pages = [p for p in _files(out) if p.suffix == ".html"]
    for rel in pages:
        text = (out / rel).read_text(encoding="utf-8")
        canonical = _CANONICAL.findall(text)
        og = _OG_URL.findall(text)
        if rel.name == "index.html":
            assert len(canonical) == len(og) == 1, rel
            prefix = "" if rel.parent == Path(".") else f"{rel.parent.as_posix()}/"
            assert canonical[0] == f"{DOMAIN_URL}/{prefix}", rel
        own += canonical + og
        for block in _LD.findall(text):
            own += [
                u
                for u in _ld_urls(json.loads(block))
                if not u.startswith("https://schema.org")
                and "wildlife.ca.gov" not in u
                and "data.ca.gov" not in u
                and "dfg.ca.gov" not in u
            ]
    own += _LOC.findall((out / "sitemap.xml").read_text(encoding="utf-8"))
    robots = (out / "robots.txt").read_text(encoding="utf-8")
    own += _URL.findall(robots)
    for rel in _files(out):
        if rel.suffix == ".ics":
            own += [
                u
                for u in _URL.findall((out / rel).read_text(encoding="utf-8"))
                if "dfg.ca.gov" not in u and "wildlife.ca.gov" not in u
            ]
    assert len(own) > 100
    for url in own:
        assert url.startswith(f"{DOMAIN_URL}/"), url
    assert f"Sitemap: {DOMAIN_URL}/sitemap.xml" in robots


def test_the_404_page_links_from_the_host_root(domain_build: tuple[Path, Path]) -> None:
    out, _ = domain_build
    text = (out / "404.html").read_text(encoding="utf-8")
    assert 'href="/assets/style.css"' in text


# ---- 3. the github.io site beside it --------------------------------------


def test_the_snapshot_stays_at_the_github_io_path_byte_for_byte(
    domain_build: tuple[Path, Path],
) -> None:
    out, old = domain_build
    rel = Path("snapshot") / "v1.json"
    assert (old / rel).read_bytes() == (out / rel).read_bytes()
    # The exact path the iOS app fetches, under the github.io site's root.
    app_url = "https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json"
    assert old / app_url.removeprefix(LEGACY + "/") == old / rel


def test_every_calendar_feed_stays_at_its_github_io_path_byte_for_byte(
    domain_build: tuple[Path, Path],
) -> None:
    out, old = domain_build
    feeds = [p for p in _files(out) if p.suffix == ".ics"]
    assert feeds
    assert feeds == [p for p in _files(old) if p.suffix == ".ics"]
    for rel in feeds:
        assert (old / rel).read_bytes() == (out / rel).read_bytes(), rel


def test_every_page_redirects_to_the_same_page_on_the_domain(
    domain_build: tuple[Path, Path],
) -> None:
    out, old = domain_build
    pages = [p for p in _files(out) if p.name == "index.html"]
    assert pages == [p for p in _files(old) if p.name == "index.html"]
    for rel in pages:
        text = (old / rel).read_text(encoding="utf-8")
        prefix = "" if rel.parent == Path(".") else f"{rel.parent.as_posix()}/"
        target = f"{DOMAIN_URL}/{prefix}"
        assert _CANONICAL.findall(text) == [target], rel
        assert _REFRESH.findall(text) == [target], rel
        assert "<script" not in text, rel
        assert "stylesheet" not in text, rel
        # The target is a real page of the domain build.
        assert (out / rel).is_file()


def test_the_app_s_water_links_land_on_a_redirect(
    domain_build: tuple[Path, Path],
) -> None:
    out, old = domain_build
    snap = json.loads((out / "snapshot" / "v1.json").read_text(encoding="utf-8"))
    for w in snap["waters"]:
        # SnapshotEndpoint.siteWaterURL: /ca-fish-planting-alerts/water/<slug>/
        page = old / "water" / w["slug"] / "index.html"
        assert f"{DOMAIN_URL}/water/{w['slug']}/" in page.read_text(encoding="utf-8")


def test_the_github_io_site_holds_only_data_redirects_404_and_sitemap(
    domain_build: tuple[Path, Path],
) -> None:
    _, old = domain_build
    for rel in _files(old):
        assert (
            rel.name == "index.html"
            or rel.suffix == ".ics"
            or rel.as_posix() in {"snapshot/v1.json", "404.html", "sitemap.xml"}
        ), rel
    assert not (old / "CNAME").exists()
    assert not (old / "robots.txt").exists()
    for rel in _files(old):
        if rel.suffix == ".html":
            assert "googletagmanager" not in (old / rel).read_text(encoding="utf-8")


def test_the_github_io_404_sends_any_other_path_to_the_domain(
    domain_build: tuple[Path, Path],
) -> None:
    _, old = domain_build
    text = (old / "404.html").read_text(encoding="utf-8")
    assert f'var base = "{DOMAIN_URL}", prefix = "/ca-fish-planting-alerts"' in text
    assert "l.replace(base + path + l.search + l.hash)" in text
    assert '<meta name="robots" content="noindex">' in text


def test_the_github_io_sitemap_lists_the_old_url_of_every_redirect(
    domain_build: tuple[Path, Path],
) -> None:
    _, old = domain_build
    locs = _LOC.findall((old / "sitemap.xml").read_text(encoding="utf-8"))
    pages = [p for p in _files(old) if p.name == "index.html"]
    assert len(locs) == len(pages)
    assert f"{LEGACY}/" in locs
    assert all(u.startswith(f"{LEGACY}/") for u in locs)


def test_the_verification_tag_stays_on_the_old_home_page_only(
    tmp_path: Path, domain_build: tuple[Path, Path]
) -> None:
    out, _ = domain_build
    verification = "abcDEF123_-xyz0987654321ABCdef-_ghiJKL0987"
    legacy.build_legacy_site(
        out, tmp_path, new_base_url=DOMAIN_URL, google_site_verification=verification
    )
    tag = f'<meta name="google-site-verification" content="{verification}">'
    assert tag in (tmp_path / "index.html").read_text(encoding="utf-8")
    for rel in _files(tmp_path):
        if rel.suffix == ".html" and rel != Path("index.html"):
            assert tag not in (tmp_path / rel).read_text(encoding="utf-8"), rel


def test_a_domain_build_without_a_snapshot_is_refused(tmp_path: Path) -> None:
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text("x", encoding="utf-8")
    with pytest.raises(legacy.LegacySiteError, match="snapshot"):
        legacy.build_legacy_site(
            tmp_path / "site", tmp_path / "legacy", new_base_url=DOMAIN_URL
        )
    assert not (tmp_path / "legacy").exists()
