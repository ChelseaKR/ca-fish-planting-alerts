"""The published stylesheet is minified, and minifying changes nothing it means.

``minify_css`` strips comments and redundant whitespace from the stylesheet
the site ships. The checks below compare the meaning, not the bytes: both the
source and the minified text are parsed into (selector, declarations) rules
by a small reader that does not depend on the minifier's whitespace choices.
"""

from __future__ import annotations

from pathlib import Path

from cfpa import site

TEMPLATES = Path(site.TEMPLATES_DIR)


def _strip(css: str) -> str:
    """Drop comments, keeping string literals intact."""
    out, i, quote = [], 0, ""
    while i < len(css):
        c = css[i]
        if quote:
            out.append(c)
            if c == "\\":
                out.append(css[i + 1])
                i += 1
            elif c == quote:
                quote = ""
        elif css.startswith("/*", i):
            i = css.index("*/", i) + 1
        elif c in "\"'":
            quote = c
            out.append(c)
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _squash(text: str) -> str:
    """Whitespace runs to one space outside strings, none after a comma; trim."""
    out, quote, space = [], "", False
    for c in text:
        if quote:
            out.append(c)
            if c == quote:
                quote = ""
        elif c.isspace():
            space = True
        else:
            if space and out and out[-1] != ",":
                out.append(" ")
            space = False
            out.append(c)
            if c in "\"'":
                quote = c
    return "".join(out)


def _push(decls: list[list[str]], buf: str) -> None:
    if buf.strip():
        prop, _, val = buf.partition(":")
        decls[-1].append(f"{_squash(prop)}:{_squash(val)}")


def _rules(css: str) -> list[tuple[str, tuple[str, ...]]]:
    """Flatten into (selector path, sorted-in-order declarations)."""
    rules: list[tuple[str, tuple[str, ...]]] = []
    stack: list[str] = []
    buf, quote = "", ""
    decls: list[list[str]] = []
    for c in _strip(css):
        if quote:
            buf += c
            if c == quote:
                quote = ""
            continue
        if c in "\"'":
            quote = c
            buf += c
        elif c == "{":
            # `(a: b)` and `(a:b)` are the same media feature.
            stack.append(_squash(buf).replace(", ", ",").replace(": ", ":"))
            decls.append([])
            buf = ""
        elif c == ";":
            _push(decls, buf)
            buf = ""
        elif c == "}":
            _push(decls, buf)
            buf = ""
            body = tuple(decls.pop())
            if body:
                rules.append((" | ".join(stack), body))
            stack.pop()
        else:
            buf += c
    assert not stack and not buf.strip()
    return rules


def _sources(*, app_store: bool) -> str:
    css = (TEMPLATES / "style.css").read_text(encoding="utf-8")
    if app_store:
        css += (TEMPLATES / "app-store.css").read_text(encoding="utf-8")
    return css


def test_minified_stylesheet_has_the_same_rules_as_the_source() -> None:
    for app_store in (False, True):
        src = _sources(app_store=app_store)
        mini = site.minify_css(src)
        rules = _rules(src)
        assert len(rules) > 30  # the reader found the stylesheet
        assert _rules(mini) == rules


def test_minified_stylesheet_is_smaller_and_has_no_comments_or_newlines() -> None:
    src = _sources(app_store=False)
    mini = site.minify_css(src)
    assert len(mini.encode()) < 0.8 * len(src.encode())
    assert "/*" not in mini and "\n" not in mini


def test_strings_and_value_spacing_survive() -> None:
    mini = site.minify_css(_sources(app_store=False))
    # The decorative separator's second `content` is `"\203A" / ""`: the
    # spaces around the slash and the empty alt string must be kept.
    assert 'content:"\\203A" / ""' in mini
    # A descendant combinator is not whitespace to drop.
    assert "ul.water-index li{" in mini
    assert ".breadcrumb li + li::before{" in mini


def test_minify_is_idempotent_and_deterministic() -> None:
    src = _sources(app_store=True)
    once = site.minify_css(src)
    assert site.minify_css(once) == once
    assert site.minify_css(src) == once


def test_comment_and_string_edge_cases() -> None:
    assert site.minify_css("a { /* x; y { */ color : red ; }") == "a{color :red}"
    assert (
        site.minify_css('a::before { content: "a  b;{" ; }')
        == 'a::before{content:"a  b;{"}'
    )


def test_negative_control_the_comparison_notices_a_changed_rule() -> None:
    src = _sources(app_store=False)
    mini = site.minify_css(src)
    sabotaged = mini.replace("columns:1}", "columns:2}", 1)
    assert sabotaged != mini  # the sabotage applied
    assert _rules(sabotaged) != _rules(src)


def test_built_site_ships_the_minified_stylesheet(tmp_path: Path) -> None:
    written: list[Path] = []
    site._write_assets(tmp_path, written, app_store_live=False)
    shipped = (tmp_path / "assets" / "style.css").read_text(encoding="utf-8")
    assert shipped == site.minify_css(_sources(app_store=False))
