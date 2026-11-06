"""The "raceway" visual identity (2026-11-05) keeps its promises.

- Every text color pair the stylesheet names is WCAG AA (4.5:1) in the light
  and the dark scheme, read from the tokens themselves, so a later palette
  edit cannot quietly drop below it. ``_contrast_problems`` is the checker.
- The mark and the tab icon cost no request: the mark is a stylesheet
  background on the site name, the icon a data: URI, and neither adds words
  to the page. The site name link still says only the site name.
- The water page's answer line and calendar subscribe action (DECISIONS
  0054) are never hidden, shrunk or moved out of flow by this stylesheet.
  ``_answer_problems`` is the checker.

Each negative control sabotages the input, asserts the sabotage changed it,
and asserts the checker notices.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
STYLE = (Path(site.TEMPLATES_DIR) / "style.css").read_text(encoding="utf-8")

# (text token, ground token): every pair the stylesheet draws text with.
TEXT_PAIRS = (
    ("--fg", "--bg"),
    ("--muted", "--bg"),
    ("--link", "--bg"),
    ("--link-visited", "--bg"),
    ("--fg", "--surface-card"),
    ("--muted", "--surface-card"),
    ("--link", "--surface-card"),
    ("--muted", "--header-bg"),
    ("--link", "--header-bg"),
    ("--fg", "--row-alt"),
    ("--link", "--row-alt"),
    ("--fg", "--thead-bg"),
    ("--masthead-fg", "--masthead-bg"),
    ("--masthead-link", "--masthead-bg"),
    ("--trout-gold", "--masthead-bg"),
    ("--on-gold", "--trout-gold"),
    ("--status-now-fg", "--status-now-bg"),
    ("--status-next-fg", "--status-next-bg"),
)
# Non-text pairs (focus rings, the badge outline): WCAG 1.4.11, 3:1.
UI_PAIRS = (
    ("--focus", "--bg"),
    ("--focus", "--surface-card"),
    ("--border-strong", "--bg"),
    ("--trout-gold", "--masthead-bg"),
)


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _tokens(css: str) -> tuple[dict[str, str], dict[str, str]]:
    """Light tokens from the first :root, dark ones from the dark-scheme block."""
    css = _strip_comments(css)
    light_body = re.search(r":root\s*\{(.*?)\}", css, re.S)
    dark_body = re.search(
        r"@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{(.*?)\}", css, re.S
    )
    assert light_body and dark_body
    decl = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
    light = {k: v.strip() for k, v in decl.findall(light_body.group(1))}
    dark = {**light, **{k: v.strip() for k, v in decl.findall(dark_body.group(1))}}
    return light, dark


def _resolve(tokens: dict[str, str], name: str) -> str:
    value = tokens[name]
    while value.startswith("var("):
        value = tokens[value[4:-1].strip()]
    return value


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    assert len(h) == 6, hex_color
    channels = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _contrast_problems(css: str) -> list[str]:
    problems = []
    for scheme, tokens in zip(("light", "dark"), _tokens(css), strict=True):
        for pairs, floor in ((TEXT_PAIRS, 4.5), (UI_PAIRS, 3.0)):
            for fg, bg in pairs:
                ratio = contrast(_resolve(tokens, fg), _resolve(tokens, bg))
                if ratio < floor:
                    problems.append(
                        f"{scheme}: {fg} on {bg} is {ratio:.2f}:1 < {floor}"
                    )
    return problems


def test_contrast_ratio_matches_wcag_examples() -> None:
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)


def test_every_token_pair_is_aa_in_both_schemes() -> None:
    assert _contrast_problems(STYLE) == []


def test_identity_is_off_the_family_greenhouse_palette() -> None:
    light, _ = _tokens(STYLE)
    # The raceway teal and river-stone ground, not leaf green on cream.
    assert _resolve(light, "--masthead-bg") == "#0c3a36"
    assert _resolve(light, "--bg") == "#f5f7f6"
    assert "--redband" in light


def test_negative_control_a_faded_link_is_caught() -> None:
    sabotaged = STYLE.replace("--link: #0a5a50;", "--link: #7fa9a3;", 1)
    assert sabotaged != STYLE
    problems = _contrast_problems(sabotaged)
    assert any(p.startswith("light: --link on --bg") for p in problems)


def test_negative_control_a_dark_scheme_regression_is_caught() -> None:
    sabotaged = STYLE.replace("--muted: #b3c4bf;", "--muted: #44524f;", 1)
    assert sabotaged != STYLE
    assert any(p.startswith("dark: --muted") for p in _contrast_problems(sabotaged))


ANSWER_SELECTOR = re.compile(r"(^|[\s,>])\.water-(answer|subscribe)\b")
HIDING = re.compile(
    r"\b(display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(\.\d+)?\s*(;|$)"
    r"|position\s*:\s*(absolute|fixed)|clip\s*:|font-size\s*:\s*0?\.\d+rem)"
)


def _answer_problems(css: str) -> list[str]:
    """Rules aimed at the answer or subscribe block that would hide or shrink it."""
    problems = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", _strip_comments(css)):
        if ANSWER_SELECTOR.search(selector) and HIDING.search(body):
            problems.append(f"{selector.strip()} {{{body.strip()}}}")
    return problems


def test_answer_and_subscribe_are_never_hidden_or_shrunk() -> None:
    assert "main .water-subscribe" in STYLE  # the checker has something to read
    assert _answer_problems(STYLE) == []


def test_negative_control_a_shrunk_answer_is_caught() -> None:
    sabotaged = STYLE + "\n.water-answer { font-size: 0.8rem; }\n"
    assert _answer_problems(sabotaged)
    hidden = STYLE + "\nmain .water-subscribe { display: none; }\n"
    assert _answer_problems(hidden)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("identity")
    out = root / "site"
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    return out


def test_mark_and_icon_make_no_request_and_add_no_words(built: Path) -> None:
    css = (built / "assets" / "style.css").read_text(encoding="utf-8")
    mark = re.search(r'\.site-name a::before\{[^}]*url\("([^"]+)"\)', css)
    assert mark and mark.group(1).startswith("data:image/svg+xml,")
    pages = sorted(built.rglob("*.html"))
    assert len(pages) > 20
    for page in pages:
        html = page.read_text(encoding="utf-8")
        icons = re.findall(r'<link rel="icon"[^>]*href="([^"]+)"', html)
        assert len(icons) == 1, page
        assert icons[0].startswith("data:image/svg+xml,"), page
        name = re.search(r'<p class="site-name"><a href="[^"]*">([^<]*)</a>', html)
        assert name and name.group(1) == "Trout Truck", page
