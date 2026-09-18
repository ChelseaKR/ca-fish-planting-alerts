// axe-core over every page of the built site (ACCESSIBILITY-STANDARD §1):
//   A11Y-01  0 violations of impact critical, serious or moderate, against
//            the WCAG 2.0/2.1/2.2 A and AA tags (target-size included).
//   A11Y-09  320 x 256 viewport: the page does not scroll sideways.
//
// Usage: node axe.mjs <base-url> <path> [<path> ...]
//
// Requests to Google Analytics are aborted. The pages carry the production
// GA4 tag (docs/DECISIONS.md 0011), and a gate run must not send page views
// from CI into the real property. The tag has no visible UI.
//
// Exits 1 on any finding, and also when it examined no page or axe reported
// no passing rules on a page, so a scan that ran nothing cannot pass.

import { AxePuppeteer } from "@axe-core/puppeteer";
import puppeteer from "puppeteer";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const BLOCKING = new Set(["critical", "serious", "moderate"]);
const BLOCKED_HOSTS = /(^|\.)(googletagmanager\.com|google-analytics\.com)$/;

const [base, ...paths] = process.argv.slice(2);
if (!base || paths.length === 0) {
  console.error("usage: node axe.mjs <base-url> <path> [<path> ...]");
  process.exit(2);
}

const browser = await puppeteer.launch({ args: ["--no-sandbox"] });
const problems = [];
let examined = 0;
try {
  for (const path of paths) {
    const url = new URL(path, base).href;
    const page = await browser.newPage();
    await page.setBypassCSP(true);
    await page.setRequestInterception(true);
    page.on("request", (req) => {
      const host = new URL(req.url()).hostname;
      if (BLOCKED_HOSTS.test(host)) req.abort();
      else req.continue();
    });

    await page.setViewport({ width: 1280, height: 900 });
    const response = await page.goto(url, { waitUntil: "load" });
    if (!response || !response.ok()) {
      problems.push(`${path}: HTTP ${response ? response.status() : "no response"}`);
      await page.close();
      continue;
    }
    const results = await new AxePuppeteer(page).withTags(TAGS).analyze();
    if (results.passes.length === 0) {
      problems.push(`${path}: axe reported no passing rules, so it did not really run`);
    }
    for (const v of results.violations) {
      if (BLOCKING.has(v.impact ?? "")) {
        const where = v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join("; ");
        problems.push(`${path}: [${v.impact}] ${v.id}: ${v.help} (${where})`);
      }
    }

    await page.setViewport({ width: 320, height: 256 });
    const overflow = await page.evaluate(() => {
      const el = document.documentElement;
      return el.scrollWidth - el.clientWidth;
    });
    if (overflow > 1) {
      problems.push(`${path}: scrolls sideways by ${overflow}px at 320px wide (SC 1.4.10)`);
    }
    examined += 1;
    await page.close();
  }
} finally {
  await browser.close();
}

for (const p of problems) console.error(p);
console.log(`axe: ${examined} page(s) examined, ${problems.length} problem(s)`);
process.exit(examined === 0 || problems.length > 0 ? 1 : 0);
