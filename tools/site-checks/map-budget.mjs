// The map's own download budget (DECISIONS 0026, perf/README.md).
//
// Lighthouse loads a page and never presses "Show map", so it cannot see
// what the map costs. This does: on the home page and on one water page
// with a location, it presses the button, waits for the map to say it has
// loaded and for the network to go quiet, and adds up the bytes
// transferred after the press (library, style, fonts, sprites, waters.json,
// the first tiles). Each total must stay within perf/map-budget.json.
//
//   node map-budget.mjs BASE_URL BUDGET_JSON            check
//   node map-budget.mjs BASE_URL BUDGET_JSON --measure  print the totals
//
// Fixed viewport and pixel ratio, so the tiles requested are the same on
// every run. The site is served uncompressed by the test server, so these
// are raw sizes; GitHub Pages sends the text files compressed.
import { readFileSync } from "node:fs";
import puppeteer from "puppeteer";

const [, , base, budgetPath, mode] = process.argv;
if (!base || !budgetPath) {
  console.error("usage: node map-budget.mjs BASE_URL BUDGET_JSON [--measure]");
  process.exit(2);
}

const QUIET_MS = 3000;

async function measure(browser, url) {
  // A fresh context and no cache: each page is measured as a first visit.
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setCacheEnabled(false);
  await page.setViewport({ width: 1280, height: 900, deviceScaleFactor: 1 });
  const client = await page.createCDPSession();
  await client.send("Network.enable");
  let counting = false;
  let bytes = 0;
  let requests = 0;
  let last = Date.now();
  const mine = new Set();
  const hosts = new Set();
  client.on("Network.requestWillBeSent", (e) => {
    last = Date.now();
    if (!counting) return;
    const u = new URL(e.request.url);
    // blob: and data: URLs (the map's worker) are not network requests.
    if (u.protocol !== "http:" && u.protocol !== "https:") return;
    mine.add(e.requestId);
    hosts.add(u.host);
  });
  client.on("Network.loadingFinished", (e) => {
    last = Date.now();
    if (mine.has(e.requestId)) {
      bytes += e.encodedDataLength;
      requests += 1;
    }
  });
  await page.goto(url, { waitUntil: "networkidle0" });
  const button = await page.$("[data-map-show]");
  if (!button) throw new Error(`no "Show map" button on ${url}`);
  counting = true;
  await button.click();
  await page.waitForFunction(
    () => /Map loaded|could not load/.test(document.querySelector("[data-map-status]").textContent),
    { timeout: 60000 },
  );
  const status = await page.$eval("[data-map-status]", (e) => e.textContent);
  if (!/Map loaded/.test(status)) throw new Error(`the map did not load on ${url}: ${status}`);
  while (Date.now() - last < QUIET_MS) await new Promise((r) => setTimeout(r, 250));
  await context.close();
  return { url, bytes, requests, hosts: [...hosts] };
}

const browser = await puppeteer.launch({
  headless: "new",
  args: ["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
let failed = false;
try {
  const waters = await (await fetch(new URL("map/waters.json", base))).json();
  const lake = waters.features.find((f) => f.properties.kind === "waterbody");
  if (!lake) throw new Error("map/waters.json has no lake to measure a water page with");
  const results = {
    home: await measure(browser, base),
    water: await measure(browser, new URL(lake.properties.url, base).href),
  };
  const own = new URL(base).host;
  for (const [name, r] of Object.entries(results)) {
    if (r.hosts.some((h) => h !== own)) {
      console.log(`map-budget: ${name} contacted another host: ${r.hosts.join(", ")}`);
      failed = true;
    }
  }
  if (mode === "--measure") {
    console.log(JSON.stringify({ home: results.home.bytes, water: results.water.bytes }, null, 2));
  } else {
    const budget = JSON.parse(readFileSync(budgetPath, "utf8")).budget_bytes;
    for (const [name, r] of Object.entries(results)) {
      const limit = budget[name];
      const verdict = r.bytes <= limit ? "ok" : "OVER";
      console.log(`map-budget: ${name} ${r.bytes} B in ${r.requests} requests (budget ${limit} B) ${verdict}`);
      if (r.bytes > limit) failed = true;
    }
  }
} catch (err) {
  console.log(`map-budget: ${err.message}`);
  failed = true;
} finally {
  await browser.close();
}
process.exit(failed ? 1 : 0);
