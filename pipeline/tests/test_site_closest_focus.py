"""Keyboard focus stays on "Sort by closest to me" after it is pressed.

Found by the 2026-11-17 accessibility sweep; axe, pa11y and Lighthouse cannot
see it because none of them presses anything.

The button (closest.js) set ``disabled`` on itself while the browser asked
about location. A disabled button cannot hold focus, so focus fell back to
the top of the document and stayed there after the list was built: measured
on trouttruck.com in Chromium and in WebKit, ``activeElement`` was ``<body>``
from the press on (WCAG 2.2 SC 2.4.3, 2.4.7). A keyboard user saw no focus
ring anywhere, and a screen reader user was put back at the top of the page.
The button now stays focusable and says it is busy with ``aria-disabled``; a
second press while it is busy does nothing.

The script is run here under node against a small stand-in for the page
(tests/fixtures/page_stand_in.js), the way test_site_push.py runs the push
policy: no browser, no network.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from cfpa import site

TEMPLATES = Path(site.TEMPLATES_DIR)
STAND_IN = Path(__file__).parent / "fixtures" / "page_stand_in.js"

_CLOSEST = (
    "const { makeDoc, tick, where } = require(process.argv[2]);\n"
    + r"""
(async () => {
  const [script, mode] = process.argv.slice(3);
  const doc = makeDoc();
  const section = doc.body.appendChild(doc.el("section", { id: "closest", "data-coords": "assets/water-coords.json", hidden: "" }));
  const button = section.appendChild(doc.el("button", { id: "closest-button" }, "Sort by closest to me"));
  const status = section.appendChild(doc.el("p", { id: "closest-status", role: "status" }));
  section.appendChild(doc.el("div", { id: "closest-result" }));
  let asks = 0, answer = null;
  global.window = {
    document: doc,
    navigator: { geolocation: { getCurrentPosition(ok, fail) { asks += 1; answer = { ok, fail }; } } },
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({ waters: {} }) }),
  };
  require(script);
  const seen = [];
  const note = (step) => seen.push({ step, focus: where(doc), disabled: button.disabled, busy: button.getAttribute("aria-disabled"), status: status.textContent, asks });
  button.focus();
  note("focused");
  button.press();
  note("pressed");
  button.press();
  note("pressed again while waiting");
  if (mode === "granted") answer.ok({ coords: { latitude: 38.5, longitude: -121.5 } });
  else answer.fail({ code: 1 });
  await tick(); await tick();
  note("answered");
  button.press();
  note("pressed after the answer");
  process.stdout.write(JSON.stringify(seen));
})();
"""
)


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI")
        pytest.skip("node is not installed")
    return node


def _run(tmp_path: Path, script: Path, arg: str) -> dict[str, dict[str, Any]]:
    runner = tmp_path / "harness.js"
    runner.write_text(_CLOSEST, encoding="utf-8")
    result = subprocess.run(
        [_node(), str(runner), str(STAND_IN), str(script), arg],
        capture_output=True, text=True, check=True, timeout=30,
    )  # fmt: skip
    steps: list[dict[str, Any]] = json.loads(result.stdout)
    return {s["step"]: s for s in steps}


@pytest.mark.parametrize("mode", ["granted", "refused"])
def test_the_closest_button_keeps_focus_while_it_waits_and_after(
    tmp_path: Path, mode: str
) -> None:
    seen = _run(tmp_path, TEMPLATES / "closest.js", mode)
    assert seen["focused"]["focus"] == "closest-button"
    for step in ("pressed", "pressed again while waiting", "answered"):
        assert seen[step]["focus"] == "closest-button", (step, seen[step])
        assert seen[step]["disabled"] is False, (step, seen[step])


def test_the_closest_button_says_it_is_busy_and_ignores_a_second_press(
    tmp_path: Path,
) -> None:
    seen = _run(tmp_path, TEMPLATES / "closest.js", "granted")
    assert seen["focused"]["busy"] is None
    assert seen["pressed"]["busy"] == "true"
    assert seen["pressed"]["status"].startswith("Waiting for your browser")
    # One question to the browser, however many presses while it is open.
    assert seen["pressed"]["asks"] == 1
    assert seen["pressed again while waiting"]["asks"] == 1
    # Finished: no longer busy, and the next press asks again.
    assert seen["answered"]["busy"] == "false"
    assert seen["pressed after the answer"]["asks"] == 2


def test_negative_control_the_old_disabled_button_loses_focus(tmp_path: Path) -> None:
    source = (TEMPLATES / "closest.js").read_text(encoding="utf-8")
    old = source.replace("setBusy(true);", "button.disabled = true;", 1)
    assert old != source
    script = tmp_path / "closest-old.js"
    script.write_text(old, encoding="utf-8")
    seen = _run(tmp_path, script, "granted")
    assert seen["pressed"]["focus"] == "body"


def test_the_busy_closest_button_still_looks_busy() -> None:
    css = (TEMPLATES / "style.css").read_text(encoding="utf-8")
    assert '.closest button[aria-disabled="true"]' in css
