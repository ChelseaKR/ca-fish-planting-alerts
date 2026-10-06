"""The github.io site after the move to a custom domain (DECISIONS 0019).

Once the site has a domain of its own, the github.io project URL keeps
serving two kinds of file, built from the domain build of the same run:

- **Data, byte for byte.** ``snapshot/v1.json`` (the iOS app fetches it from
  the github.io URL, and builds already on phones hard-code that URL) and
  every water's ``feed.ics`` (calendar apps poll the URL they subscribed
  to). These are copies, never redirects, so neither depends on the domain.
- **A redirect page in place of every HTML page.** GitHub Pages cannot send
  a server-side redirect from one path of a site that has no custom domain
  of its own, and giving this repository's site the custom domain would turn
  *every* github.io URL, the snapshot included, into a 301 to that domain.
  So each page becomes a small HTML file with ``rel=canonical`` pointing to
  its new URL and an instant ``<meta http-equiv="refresh" content="0">``,
  which Google Search treats as a permanent redirect. ``404.html`` sends any
  other old path to the same path on the domain with ``location.replace``.

The redirect pages carry no analytics, no stylesheet and no structured data.
The home page's one keeps the Search Console verification tag, so the old
URL-prefix property stays verified while Google follows the move. A
``sitemap.xml`` lists the old URLs, which Google's site-move guide uses to
watch the old URLs drop out of the index.
"""

from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from .site import LEGACY_BASE_URL, SITE_NAME, custom_domain

SNAPSHOT_PATH = Path("snapshot") / "v1.json"


class LegacySiteError(ValueError):
    """The domain build cannot be turned into a safe github.io site."""


def _stub(new_url: str, *, google_site_verification: str | None) -> str:
    url = html.escape(new_url, quote=True)
    verification = (
        f'<meta name="google-site-verification" '
        f'content="{html.escape(google_site_verification, quote=True)}">\n'
        if google_site_verification
        else ""
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{SITE_NAME} has moved</title>\n"
        f'<link rel="canonical" href="{url}">\n'
        f'<meta http-equiv="refresh" content="0; url={url}">\n'
        f"{verification}"
        "</head>\n"
        "<body>\n"
        "<main>\n"
        f"<h1>{SITE_NAME} has moved</h1>\n"
        f'<p>This page is now at <a href="{url}">{url}</a>.</p>\n'
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )


def _not_found(new_base_url: str, legacy_prefix: str) -> str:
    # json.dumps gives JavaScript string literals; "</" cannot appear in
    # either (a URL root and a path prefix), checked by the caller.
    base = json.dumps(new_base_url)
    prefix = json.dumps(legacy_prefix)
    home = html.escape(f"{new_base_url}/", quote=True)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{SITE_NAME} has moved</title>\n"
        '<meta name="robots" content="noindex">\n'
        "<script>\n"
        "(function () {\n"
        f"  var base = {base}, prefix = {prefix}, l = window.location;\n"
        "  var path = l.pathname;\n"
        "  if (path.indexOf(prefix) === 0) path = path.slice(prefix.length);\n"
        '  if (path.charAt(0) !== "/") path = "/" + path;\n'
        "  l.replace(base + path + l.search + l.hash);\n"
        "})();\n"
        "</script>\n"
        "</head>\n"
        "<body>\n"
        "<main>\n"
        f"<h1>{SITE_NAME} has moved</h1>\n"
        f'<p>The site is now at <a href="{home}">{home}</a>.</p>\n'
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )


def build_legacy_site(
    site_dir: Path,
    out_dir: Path,
    *,
    new_base_url: str,
    legacy_base_url: str = LEGACY_BASE_URL,
    google_site_verification: str | None = None,
) -> list[Path]:
    """Write the github.io site for a domain build in ``site_dir``.

    ``site_dir`` is the finished domain build (``build_site`` with
    ``base_url=new_base_url``, plus ``snapshot/v1.json``). Raises
    ``LegacySiteError``, writing nothing, when ``new_base_url`` is not a
    custom domain or the build has no snapshot: a github.io site without the
    snapshot would break every installed app.
    """
    new_base_url = new_base_url.rstrip("/")
    legacy_base_url = legacy_base_url.rstrip("/")
    if custom_domain(new_base_url) is None:
        raise LegacySiteError(
            f"{new_base_url!r} is not a custom domain (https://<host>, no path, "
            "not github.io); the github.io site only moves to one"
        )
    if not (site_dir / SNAPSHOT_PATH).is_file():
        raise LegacySiteError(
            f"{site_dir / SNAPSHOT_PATH} is missing; the github.io URL must keep "
            "serving the snapshot the iOS app fetches"
        )
    legacy_prefix = urlsplit(legacy_base_url).path
    if "<" in new_base_url or "<" in legacy_prefix:
        raise LegacySiteError("a base URL cannot contain '<'")

    pages: list[Path] = []
    data: list[Path] = [SNAPSHOT_PATH]
    for path in sorted(p.relative_to(site_dir) for p in site_dir.rglob("*")):
        if not (site_dir / path).is_file():
            continue
        if path.name == "index.html":
            pages.append(path)
        elif path.suffix == ".ics":
            data.append(path)

    written: list[Path] = []
    for rel in data:
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(site_dir / rel, dest)
        written.append(dest)

    old_urls: list[str] = []
    for rel in pages:
        rel_dir = rel.parent.as_posix()
        suffix = "/" if rel_dir == "." else f"/{rel_dir}/"
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            _stub(
                f"{new_base_url}{suffix}",
                google_site_verification=google_site_verification
                if rel_dir == "."
                else None,
            ),
            encoding="utf-8",
        )
        written.append(dest)
        old_urls.append(f"{legacy_base_url}{suffix}")

    not_found = out_dir / "404.html"
    not_found.parent.mkdir(parents=True, exist_ok=True)
    not_found.write_text(_not_found(new_base_url, legacy_prefix), encoding="utf-8")
    written.append(not_found)

    sitemap = out_dir / "sitemap.xml"
    items = "\n".join(f"  <url><loc>{html.escape(u)}</loc></url>" for u in old_urls)
    sitemap.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}\n"
        "</urlset>\n",
        encoding="utf-8",
    )
    written.append(sitemap)
    return written
