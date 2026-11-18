"""Each link in the footer's row keeps a 24px target (WCAG 2.2 SC 2.5.8).

Found by the 2026-11-17 accessibility sweep; axe, pa11y and Lighthouse pass
it because none of them measures the space between targets.

On a desktop the footer's row of site links is one line, and each 19px-tall
link has room around it. On a phone the row wraps to three or four lines 21px
apart, so each link is under 24px tall with another link directly above or
below it, closer than the 24px spacing the criterion accepts in place of
size. The row is a list of links, not a sentence, so the inline exception
does not cover it. Each link in the row now keeps a 24px-tall box, the way
the header and breadcrumb links do.

The pattern is the repository's own (test_site_narrow_dl.py): read the source
stylesheet, find the rule, and prove with a negative control that the check
notices when the rule is gone.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES = Path(__file__).parents[1] / "src" / "cfpa" / "templates"
STYLE = TEMPLATES / "style.css"
BASE = TEMPLATES / "base.html.jinja"

FOOTER_ROW = ".site-footer__links a"


def _css() -> str:
    return STYLE.read_text(encoding="utf-8")


def _rule(css: str, selector: str) -> str:
    """The declarations of the rule whose selector is exactly ``selector``."""
    plain = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    bodies = [
        body
        for found, body in re.findall(r"([^{}]+)\{([^{}]*)\}", plain)
        if selector in [part.strip() for part in found.split(",")]
    ]
    return " ".join(" ".join(bodies).split())


def _keeps_a_24px_target(css: str) -> bool:
    body = _rule(css, FOOTER_ROW)
    return "display: inline-block;" in body and "min-height: var(--tap-min);" in body


def test_each_link_in_the_footer_row_keeps_a_24px_target() -> None:
    css = _css()
    assert "--tap-min: 24px;" in css
    assert _keeps_a_24px_target(css)


def test_the_footer_row_in_the_template_is_the_row_the_rule_names() -> None:
    base = BASE.read_text(encoding="utf-8")
    row = re.search(r'<p class="site-footer__links">(.*?)</p>', base, re.S)
    assert row, "the footer's link row lost its class"
    # The row is the list of site links, and nothing else in the footer is.
    for href in ("about/", "gear/", "privacy/", "terms/", "support/", "guide/"):
        assert f'href="{{{{ root }}}}{href}"' in row.group(1), href
    assert base.count('class="site-footer__links"') == 1


def test_negative_control_the_check_notices_a_footer_row_left_inline() -> None:
    css = _css()
    start = css.index(FOOTER_ROW)
    sabotaged = css[:start] + css[start:].replace("display: inline-block;", "", 1)
    assert sabotaged != css
    assert not _keeps_a_24px_target(sabotaged)
