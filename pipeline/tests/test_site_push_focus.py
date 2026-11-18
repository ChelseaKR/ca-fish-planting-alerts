"""After "Alert me about this water" is pressed, focus and speech follow it.

Found by the 2026-11-17 accessibility sweep; axe, pa11y and Lighthouse cannot
see it because none of them presses anything. The control is off in the live
build as of that date, so this was read in the script and measured on a local
build, not on trouttruck.com.

The control (push.js) hid the view holding the pressed button ("idle" ->
"busy" -> "on"), which drops keyboard focus to the top of the page (WCAG 2.2
SC 2.4.3), and it said nothing a screen reader hears when the alert was set:
the confirmation was a paragraph that appeared, and the status line stayed
empty (SC 4.1.3). Now focus follows the press: to the "Setting it up" words
while the browser works, then to what answers it, which is the button again
when it can be pressed again and otherwise the paragraph that says what
happened. A screen reader reads what focus lands on. Focus is never taken on
load, and never pulled back from somewhere else on the page.

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

_PUSH = (
    "const { makeDoc, tick, where } = require(process.argv[2]);\n"
    + r"""
(async () => {
  const [script, permission] = process.argv.slice(3);
  const doc = makeDoc();
  const box = doc.body.appendChild(doc.el("div", {
    class: "push-subscribe", "data-push-api": "https://push.example.invalid", "data-push-public": "BAcH",
    "data-push-water": "cdfw-1", "data-push-water-name": "Test Lake", "data-push-worker": "/push-worker.js", "data-push-scope": "/", hidden: "",
  }));
  const idle = box.appendChild(doc.el("div", { "data-push-view": "idle", hidden: "" }));
  const other = idle.appendChild(doc.el("p", { "data-push-other": "", hidden: "" }));
  other.appendChild(doc.el("span", { "data-push-other-name": "" }));
  const subscribe = idle.appendChild(doc.el("button", { "data-push-action": "subscribe" }, "Alert me about this water"));
  box.appendChild(doc.el("p", { "data-push-view": "busy", hidden: "" }, "\n    Setting it up…\n  "));
  const on = box.appendChild(doc.el("p", { "data-push-view": "on", hidden: "" }, "This browser gets a notification."));
  on.appendChild(doc.el("button", { "data-push-action": "unsubscribe" }, "Stop these notifications"));
  box.appendChild(doc.el("p", { "data-push-view": "ios", hidden: "" }));
  box.appendChild(doc.el("p", { "data-push-view": "blocked", hidden: "" }, "Notifications for this site are blocked."));
  box.appendChild(doc.el("p", { "data-push-view": "unsupported", hidden: "" }));
  const status = box.appendChild(doc.el("p", { "data-push-status": "", role: "status" }));
  const elsewhere = doc.body.appendChild(doc.el("a", { id: "elsewhere" }, "another link"));
  let current = "default", release = null, stored = null;
  const sub = { endpoint: "https://push.example.invalid/e", toJSON: () => ({ keys: {} }), unsubscribe: () => Promise.resolve(true) };
  const reg = { active: {}, pushManager: { getSubscription: () => Promise.resolve(stored ? sub : null), subscribe: () => Promise.resolve(sub) } };
  const notification = { get permission() { return current; }, requestPermission: () => new Promise((r) => { release = () => { current = permission; r(permission); }; }) };
  const nav = { userAgent: "Mozilla/5.0 (X11; Linux x86_64) Chrome/130", platform: "Linux x86_64", maxTouchPoints: 0,
    serviceWorker: { register: () => Promise.resolve(reg), getRegistration: () => Promise.resolve(reg) } };
  const store = {};
  const win = { isSecureContext: true, PushManager: function () {}, Notification: notification,
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; stored = true; }, removeItem: (k) => { delete store[k]; stored = null; } },
    matchMedia: () => ({ matches: false }), fetch: () => Promise.resolve({ ok: true, status: 200 }), atob: (s) => Buffer.from(s, "base64").toString("binary") };
  // push.js exports its policy and stops when `module.exports` exists; a page
  // has no `module`, and neither does a function body.
  const src = require("fs").readFileSync(script, "utf8");
  new Function("window", "document", "navigator", "Notification", src)(win, doc, nav, notification);
  await tick(); await tick();
  const seen = [];
  const views = () => box.querySelectorAll("[data-push-view]").filter((v) => !v.hidden).map((v) => v.attrs["data-push-view"]);
  const note = (step) => seen.push({ step, focus: where(doc), views: views(), status: status.textContent.replace(/\s+/g, " ").trim(), tabindex: (doc.activeElement.attrs || {}).tabindex || null });
  note("loaded");
  subscribe.focus();
  note("focused");
  subscribe.press();
  await tick();
  note("pressed");
  if (permission === "tabbed-away") elsewhere.focus();
  release();
  await tick(); await tick(); await tick();
  note("answered");
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
    runner.write_text(_PUSH, encoding="utf-8")
    result = subprocess.run(
        [_node(), str(runner), str(STAND_IN), str(script), arg],
        capture_output=True, text=True, check=True, timeout=30,
    )  # fmt: skip
    steps: list[dict[str, Any]] = json.loads(result.stdout)
    return {s["step"]: s for s in steps}


def test_while_it_is_setting_up_focus_is_on_the_words_that_say_so(
    tmp_path: Path,
) -> None:
    seen = _run(tmp_path, TEMPLATES / "push.js", "granted")
    assert seen["loaded"]["views"] == ["idle"]
    assert seen["loaded"]["focus"] == "body"  # nothing takes focus on load
    assert seen["pressed"]["views"] == ["busy"]
    assert seen["pressed"]["focus"] == "busy"
    assert seen["pressed"]["tabindex"] == "-1"


def test_when_the_alert_is_set_focus_goes_to_the_words_that_say_so(
    tmp_path: Path,
) -> None:
    seen = _run(tmp_path, TEMPLATES / "push.js", "granted")
    assert seen["answered"]["views"] == ["on"]
    assert seen["answered"]["focus"] == "on"
    # A paragraph takes focus from script only, never from the Tab key.
    assert seen["answered"]["tabindex"] == "-1"
    assert seen["answered"]["status"] == ""


def test_when_the_browser_blocks_it_focus_goes_to_the_words_that_say_so(
    tmp_path: Path,
) -> None:
    seen = _run(tmp_path, TEMPLATES / "push.js", "denied")
    assert seen["answered"]["views"] == ["blocked"]
    assert seen["answered"]["focus"] == "blocked"


def test_when_nothing_was_set_up_focus_returns_to_the_button(tmp_path: Path) -> None:
    seen = _run(tmp_path, TEMPLATES / "push.js", "default")
    assert seen["answered"]["views"] == ["idle"]
    assert seen["answered"]["focus"] == "subscribe"
    assert seen["answered"]["status"].startswith("No notification was set up.")


def test_focus_is_not_pulled_back_from_somewhere_else_on_the_page(
    tmp_path: Path,
) -> None:
    seen = _run(tmp_path, TEMPLATES / "push.js", "tabbed-away")
    assert seen["answered"]["focus"] == "elsewhere"


def test_the_status_line_stays_in_the_page_while_it_is_empty() -> None:
    """A live region that is ``display: none`` until it has words is one many
    screen readers never hear: the region has to exist before its text does."""
    css = (TEMPLATES / "style.css").read_text(encoding="utf-8")
    rule = css[css.index(".push-subscribe__status:empty") :].split("}", 1)[0]
    assert "display: none" not in rule
    assert "margin: 0" in rule
