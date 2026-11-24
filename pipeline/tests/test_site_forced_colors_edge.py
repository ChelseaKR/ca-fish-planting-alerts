"""A filled button keeps its edge when colors are forced (Windows High Contrast).

Found by the 2026-11-17 accessibility sweep; axe, pa11y and Lighthouse do not
run with forced colors.

The two calendar buttons on a water page are drawn as a filled block with no
border. Forced colors removes author backgrounds, so the block vanished and
the two "buttons" became bold link text with no underline: nothing but the
system link color said they could be pressed. A transparent border costs
nothing in the normal scheme and is drawn in the system's text color when
colors are forced, so the button keeps its edge. The push button set
``border: none`` and gets the same.

The pattern is the repository's own (test_site_narrow_dl.py): read the source
stylesheet, find the rule, and prove with a negative control that the check
notices when the rule is gone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STYLE = Path(__file__).parents[1] / "src" / "cfpa" / "templates" / "style.css"


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


def _has_an_edge(css: str, selector: str) -> bool:
    body = _rule(css, selector)
    borders = re.findall(r"border: ([^;]+);", body)
    return bool(borders) and borders[-1] == "1px solid transparent"


@pytest.mark.parametrize(
    "selector", [".calendar-subscribe__button", ".push-subscribe__button"]
)
def test_a_filled_button_keeps_an_edge_when_colors_are_forced(selector: str) -> None:
    assert _has_an_edge(_css(), selector)


def test_negative_control_the_check_notices_a_button_with_no_border() -> None:
    css = _css()
    for selector in (".calendar-subscribe__button", ".push-subscribe__button"):
        sabotaged = css.replace("border: 1px solid transparent;", "border: none;")
        assert sabotaged != css
        assert not _has_an_edge(sabotaged, selector)
