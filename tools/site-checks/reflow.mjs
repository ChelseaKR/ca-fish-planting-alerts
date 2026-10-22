// WCAG 1.4.10 reflow gate (ACCESSIBILITY-STANDARD A11Y-09): at 320 CSS px
// wide, no page scrolls sideways (document scrollWidth <= clientWidth).
//
// Usage: node reflow.mjs <base-url> <path> [<path> ...]
//        node reflow.mjs --self-test <base-url> <path> [<path> ...]
//
// Why this is its own script, and not the check that axe.mjs also runs:
//
//   * Fonts. Whether a line fits in 320px depends on glyph widths, and the
//     stylesheet starts with -apple-system, so a Mac measures San Francisco
//     and the ubuntu CI runner measures a narrower fallback (Liberation
//     Sans or similar). The water-page status list overflowed by 7px on a
//     Mac and by 0px on CI, so CI passed a page that real readers on
//     phones saw scroll sideways. This script measures every page twice:
//     with the site's own fonts, and again with every font replaced by a
//     deliberately wide face (Verdana, else DejaVu Sans), so the result no
//     longer depends on which fonts the runner has installed.
//   * The viewport is 320px wide from the first byte (set before goto), not
//     resized after load, so media queries and layout run once at that
//     width.
//   * Every page is measured, not a sample. 37 of 206 pages overflowed
//     before #83, and a sample can miss them. The script still fails if
//     any of the page types the standard names is absent from the run
//     (home, county, region, species, water, tn water, privacy), so a
//     build that dropped one cannot pass by not having it.
//
// --self-test is the negative control: it re-creates the pre-#83 rule
// (dl as two columns at every width) on a water page and requires this
// script's own measurement to report the overflow. If it does not, the
// check cannot fail and the script exits 1.
//
// Google Analytics requests are aborted, as in axe.mjs.

import puppeteer from "puppeteer";

const BLOCKED_HOSTS = /(^|\.)(googletagmanager\.com|google-analytics\.com)$/;
const WIDE_FONT = '*, *::before, *::after { font-family: Verdana, "DejaVu Sans", sans-serif !important; }';
const OLD_DL = "dl { grid-template-columns: max-content 1fr !important; }";
const TYPES = [
  ["home", (p) => p === "./" || p === ""],
  ["county", (p) => /^county\/[^/]+\/$/.test(p)],
  ["region", (p) => /^region\/[^/]+\/$/.test(p)],
  ["species", (p) => /^species\/[^/]+\/$/.test(p)],
  ["water", (p) => /^water\/[^/]+\/$/.test(p)],
  ["tn water", (p) => /^tn\/water\/[^/]+\/$/.test(p)],
  ["privacy", (p) => p === "privacy/"],
];

const args = process.argv.slice(2);
const selfTest = args[0] === "--self-test";
const [base, ...paths] = selfTest ? args.slice(1) : args;
if (!base || paths.length === 0) {
  console.error("usage: node reflow.mjs [--self-test] <base-url> <path> [<path> ...]");
  process.exit(2);
}

const browser = await puppeteer.launch({ args: ["--no-sandbox"] });

async function measure(page, path, css) {
  const response = await page.goto(new URL(path, base).href, { waitUntil: "load" });
  if (!response || !response.ok()) return { error: `HTTP ${response ? response.status() : "no response"}` };
  for (const c of css) await page.addStyleTag({ content: c });
  return page.evaluate(() => {
    const el = document.documentElement;
    const width = el.clientWidth;
    let widest = "";
    let max = 0;
    for (const n of document.body.querySelectorAll("*")) {
      const r = n.getBoundingClientRect();
      if (r.right > max) {
        max = r.right;
        widest = n.tagName.toLowerCase() + (n.id ? "#" + n.id : "") + (n.className && typeof n.className === "string" ? "." + n.className.trim().split(/\s+/)[0] : "");
      }
    }
    return { overflow: el.scrollWidth - width, width, widest };
  });
}

async function newPage() {
  const page = await browser.newPage();
  await page.setBypassCSP(true);
  await page.setRequestInterception(true);
  page.on("request", (req) => {
    if (BLOCKED_HOSTS.test(new URL(req.url()).hostname)) req.abort();
    else req.continue();
  });
  await page.setViewport({ width: 320, height: 256 });
  return page;
}

let code = 0;
let page;
try {
  page = await newPage();
  if (selfTest) {
    const water = paths.find((p) => /^water\/[^/]+\/$/.test(p));
    if (!water) {
      console.error("reflow self-test: no water page in the list");
      process.exit(1);
    }
    const clean = await measure(page, water, [WIDE_FONT]);
    const broken = await measure(page, water, [WIDE_FONT, OLD_DL]);
    if (clean.error || broken.error) {
      console.error(`reflow self-test: ${clean.error ?? broken.error}`);
      code = 1;
    } else if (clean.overflow > 1) {
      console.error(`reflow self-test: ${water} already overflows by ${clean.overflow}px before the sabotage, so the control proves nothing`);
      code = 1;
    } else if (broken.overflow <= 1) {
      console.error(`reflow self-test FAILED: the pre-#83 dl rule on ${water} overflowed by ${broken.overflow}px, so this check cannot notice that bug`);
      code = 1;
    } else {
      console.log(`reflow self-test: ok (${water}: 0px with the fix, ${broken.overflow}px with the pre-#83 rule)`);
    }
  } else {
    const missing = TYPES.filter(([, test]) => !paths.some(test)).map(([name]) => name);
    const problems = missing.map((m) => `no ${m} page in the run, so that page type was not checked`);
    let examined = 0;
    for (const path of paths) {
      for (const [label, css] of [["site fonts", []], ["wide font", [WIDE_FONT]]]) {
        const r = await measure(page, path, css);
        if (r.error) {
          problems.push(`${path}: ${r.error}`);
          break;
        }
        if (r.overflow > 1) {
          problems.push(`${path}: scrolls sideways by ${r.overflow}px at 320px wide, ${label}; widest element ${r.widest} (SC 1.4.10)`);
        }
      }
      examined += 1;
    }
    for (const p of problems) console.error(p);
    console.log(`reflow: ${examined} page(s) at 320px, 2 font passes, ${problems.length} problem(s)`);
    if (examined === 0 || problems.length > 0) code = 1;
  }
} finally {
  if (page) await page.close();
  await Promise.race([browser.close(), new Promise((r) => setTimeout(r, 3000))]);
  browser.process()?.kill();
}
process.exit(code);
