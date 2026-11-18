// A stand-in for the few DOM calls the site's page scripts make, so a test can
// press a button under node and ask where keyboard focus went
// (tests/test_site_closest_focus.py, tests/test_site_push_focus.py). Elements
// are plain objects; selectors are the attribute and class forms the scripts
// use and nothing else, and an unsupported one throws. Focus follows the
// browser's rule that matters here: an element that becomes hidden or
// disabled cannot keep it, and focus falls back to <body>.
function makeDoc() {
  const doc = { activeElement: null, all: [], body: null };
  function el(tag, attrs, text) {
    const e = {
      tagName: tag.toUpperCase(), attrs: Object.assign({}, attrs || {}), children: [], parent: null,
      listeners: {}, _text: text || "", _disabled: false, focusCount: 0,
      get hidden() { return "hidden" in this.attrs; },
      set hidden(v) { if (v) this.attrs.hidden = ""; else delete this.attrs.hidden; if (v) doc.dropFocusIfGone(); },
      get disabled() { return this._disabled; },
      set disabled(v) { this._disabled = !!v; if (v && doc.activeElement === this) doc.activeElement = doc.body; },
      get id() { return this.attrs.id || ""; },
      get className() { return this.attrs.class || ""; },
      set className(v) { this.attrs.class = v; },
      get firstChild() { return this.children[0] || null; },
      get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); },
      set textContent(v) { this.children = []; this._text = String(v); },
      getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
      setAttribute(k, v) { this.attrs[k] = String(v); },
      removeAttribute(k) { delete this.attrs[k]; },
      hasAttribute(k) { return k in this.attrs; },
      appendChild(c) { c.parent = this; this.children.push(c); return c; },
      removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; },
      addEventListener(type, fn) { this.listeners[type] = fn; },
      contains(o) { for (let n = o; n; n = n.parent) if (n === this) return true; return false; },
      shown() { for (let n = this; n; n = n.parent) if (n.hidden) return false; return true; },
      focusable() { return this.shown() && !this._disabled && (["BUTTON", "A"].includes(this.tagName) || "tabindex" in this.attrs); },
      focus() { this.focusCount += 1; if (this.focusable()) doc.activeElement = this; },
      matches(sel) {
        let m = /^\[([a-z-]+)(?:="([^"]*)")?\]$/.exec(sel);
        if (m) return m[1] in this.attrs && (m[2] === undefined || this.attrs[m[1]] === m[2]);
        m = /^\.([a-z_-]+)$/.exec(sel);
        if (m) return (this.attrs.class || "").split(" ").includes(m[1]);
        if (sel === "tr[data-slug]") return this.tagName === "TR" && "data-slug" in this.attrs;
        throw new Error("selector not supported by the stand-in: " + sel);
      },
      closest(sel) { for (let n = this; n; n = n.parent) if (n.matches(sel)) return n; return null; },
      querySelectorAll(sel) { const out = []; (function walk(n) { n.children.forEach((c) => { if (c.matches(sel)) out.push(c); walk(c); }); })(this); return out; },
      querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
      press() { const ev = { target: this }; for (let n = this; n; n = n.parent) if (n.listeners.click) n.listeners.click(ev); },
    };
    doc.all.push(e);
    return e;
  }
  doc.el = el;
  doc.body = el("body");
  doc.createElement = (tag) => el(tag);
  doc.createTextNode = (t) => el("#text", {}, t);
  doc.getElementById = (id) => doc.all.find((e) => e.attrs.id === id) || null;
  doc.querySelector = (sel) => doc.body.querySelector(sel);
  doc.querySelectorAll = (sel) => doc.body.querySelectorAll(sel);
  doc.dropFocusIfGone = () => { if (doc.activeElement && !doc.activeElement.shown()) doc.activeElement = doc.body; };
  doc.activeElement = doc.body;
  return doc;
}
const tick = () => new Promise((r) => setTimeout(r, 5));
const where = (doc) => { const a = doc.activeElement; return a === doc.body ? "body" : (a.attrs.id || a.attrs["data-push-view"] || a.attrs["data-push-action"] || a.tagName); };
module.exports = { makeDoc: makeDoc, tick: tick, where: where };
