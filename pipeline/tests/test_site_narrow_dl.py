"""A definition list must stack on a narrow screen (WCAG 1.4.10 reflow).

The status block on a water page is a <dl> whose labels are long ("This week,
the week of 2026-10-18"). In the two-column grid the label column took its
full text width and left the answer column about 15px at 320px, so the page
scrolled sideways. The stylesheet stacks the list under 30rem.
"""

from __future__ import annotations

from pathlib import Path

import pytest

STYLE = Path(__file__).parents[1] / "src" / "cfpa" / "templates" / "style.css"
NARROW = "@media (max-width: 30rem) {"


def _narrow_block(css: str) -> str:
    start = css.index(NARROW) + len(NARROW)
    depth, i = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(css[i], 0)
        i += 1
    return css[start : i - 1]


def _stacks(css: str) -> bool:
    block = " ".join(_narrow_block(css).split())
    return "dl { grid-template-columns: 1fr; }" in block


def test_two_column_list_stacks_on_a_narrow_screen() -> None:
    css = STYLE.read_text(encoding="utf-8")
    assert "dl { display: grid; grid-template-columns: max-content 1fr;" in css
    assert _stacks(css)


def test_negative_control_the_check_notices_a_missing_rule() -> None:
    css = STYLE.read_text(encoding="utf-8")
    sabotaged = css.replace("dl { grid-template-columns: 1fr; }", "")
    assert sabotaged != css  # the sabotage applied
    assert not _stacks(sabotaged)


def test_negative_control_the_rule_must_be_inside_the_narrow_query() -> None:
    css = STYLE.read_text(encoding="utf-8")
    outside = css.replace("dl { grid-template-columns: 1fr; }", "") + (
        "\ndl { grid-template-columns: 1fr; }\n"
    )
    assert outside != css
    assert not _stacks(outside)


@pytest.mark.parametrize("needle", ["dl {", "dd {"])
def test_the_narrow_block_is_balanced(needle: str) -> None:
    assert needle in _narrow_block(STYLE.read_text(encoding="utf-8"))
