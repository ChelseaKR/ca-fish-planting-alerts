// node --test: the handler against an in-memory store and a stand-in sender.
// No npm install, no AWS. Every negative control first shows its sabotage
// changed the input, then that the handler refused it.
import assert from "node:assert/strict";
import { createECDH } from "node:crypto";
import { test } from "node:test";
import { LIMITS, createHandler } from "./handler.mjs";
import { endpointHash } from "./validate.mjs";

const ORIGIN = "https://trouttruck.com";
const TOKEN = "t".repeat(48);
const SECRETS = {
  vapidPublicKey: "B" + "A".repeat(86),
  vapidPrivateKey: "p".repeat(43),
  vapidSubject: "mailto:test@example.invalid",
  senderToken: TOKEN,
};
// A real point on the curve: the service refuses any other (DECISIONS 0074).
function p256Point() {
  const ecdh = createECDH("prime256v1");
  ecdh.generateKeys();
  return ecdh.getPublicKey().toString("base64url");
}
const P256DH = p256Point();
const AUTH = Buffer.alloc(16, 9).toString("base64url");

function endpoint(n) {
  return `https://web.push.apple.com/QAbc${n}`;
}
function subscription(n) {
  return { endpoint: endpoint(n), keys: { p256dh: P256DH, auth: AUTH } };
}

function memoryStore() {
  const rows = new Map();
  const caps = new Map();
  const writes = { put: 0, take: 0 };
  let counters = {};
  return {
    rows,
    caps,
    writes,
    get counters_() {
      return counters;
    },
    async getSubscription(hash) {
      return rows.get(`SUB#${hash}`) || null;
    },
    async putSubscription(item) {
      writes.put += 1;
      rows.set(item.pk, { ...item });
    },
    async countByWater(waterId) {
      return [...rows.values()].filter((r) => r.water_id === waterId).length;
    },
    async take(key, max, expiresAt) {
      writes.take += 1;
      const row = caps.get(key) || { n: 0 };
      if (row.n >= max) return false;
      caps.set(key, { n: row.n + 1, expires_at: expiresAt });
      return true;
    },
    async strike(hash) {
      const row = rows.get(`SUB#${hash}`);
      if (!row) return 0;
      row.refusals = (row.refusals || 0) + 1;
      return row.refusals;
    },
    async deleteSubscription(hash) {
      return rows.delete(`SUB#${hash}`);
    },
    async listByWater(waterId) {
      return [...rows.values()].filter((r) => r.water_id === waterId);
    },
    async touch(hash, fields) {
      const row = rows.get(`SUB#${hash}`);
      if (row) Object.assign(row, fields);
    },
    async bump(counts) {
      for (const [k, v] of Object.entries(counts)) {
        if (v) counters[k] = (counters[k] || 0) + v;
      }
    },
    async counters() {
      return { ...counters };
    },
    async countSubscriptions(prefix) {
      return [...rows.values()].filter((r) => !prefix || r.endpoint.startsWith(prefix)).length;
    },
  };
}

function fakeSender(failWith = {}) {
  const calls = [];
  return {
    calls,
    async send(sub, payload, options) {
      calls.push({ endpoint: sub.endpoint, keys: sub.keys, payload: JSON.parse(payload), options });
      const code = failWith[sub.endpoint];
      if (code) {
        const err = new Error(`push service answered ${code}`);
        err.statusCode = code;
        throw err;
      }
    },
  };
}

function make({
  store = memoryStore(),
  sender = fakeSender(),
  secrets = async () => SECRETS,
  limits = LIMITS,
  clock,
} = {}) {
  const time = { at: new Date("2026-11-08T12:00:00Z") };
  const handler = createHandler({
    store,
    secrets,
    sender,
    siteOrigins: [ORIGIN],
    now: () => time.at,
    limits,
    ...(clock ? { clock } : {}),
  });
  return { handler, store, sender, time };
}

// A documentation address (RFC 5737): the caller's network in these tests.
const CLIENT = "203.0.113.7";

function request(method, path, body, headers = {}, sourceIp = CLIENT) {
  return {
    requestContext: { http: { method, sourceIp } },
    rawPath: path,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    isBase64Encoded: false,
  };
}

function json(res) {
  return JSON.parse(res.body);
}

const auth = { authorization: `Bearer ${TOKEN}` };
const water = "cdfw-123";
const event = (over = {}) => ({
  water_id: water,
  title: "Shadow Cliff Lake: scheduled, week of Nov 16",
  body: "CDFW lists Shadow Cliff Lake for planting the week of Sunday, November 16, 2026. Scheduled, not confirmed: CDFW's plans can change.",
  url: `${ORIGIN}/water/shadow-cliff-lake/?utm_source=web-push&utm_medium=push`,
  tag: water,
  ...over,
});

test("subscribe stores one row per endpoint, keyed by its hash, and counts it", async () => {
  const { handler, store } = make();
  const res = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  assert.equal(res.statusCode, 200);
  assert.deepEqual(json(res), { ok: true, water_id: water });
  const row = store.rows.get(`SUB#${endpointHash(endpoint(1))}`);
  assert.equal(row.water_id, water);
  assert.equal(row.endpoint, endpoint(1));
  assert.equal(row.p256dh, P256DH);
  assert.equal(row.auth, AUTH);
  assert.equal(row.created_at, "2026-11-08T12:00:00.000Z");
  assert.equal(row.last_sent_at, undefined, "nothing sent yet, so no last_sent_at");
  assert.ok(row.expires_at > Date.parse("2027-11-08") / 1000, "expires about 13 months out");
  assert.deepEqual(await store.counters(), { subscribes: 1 });
  // The row never holds a request detail.
  assert.deepEqual(Object.keys(row).sort(), [
    "auth", "created_at", "endpoint", "expires_at", "kind", "p256dh", "pk", "water_id",
  ]);
});

test("the same browser subscribing again for the same water changes nothing", async () => {
  const { handler, store } = make();
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  assert.equal(store.rows.size, 1);
  assert.deepEqual(await store.counters(), { subscribes: 1 });
});

test("one water per browser: a second water replaces the first and counts a switch", async () => {
  const { handler, store } = make();
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  const res = await handler(request("POST", "/subscribe", { water_id: "tn-carter-doe-river", subscription: subscription(1) }));
  assert.equal(res.statusCode, 200);
  assert.equal(store.rows.size, 1);
  assert.equal([...store.rows.values()][0].water_id, "tn-carter-doe-river");
  assert.deepEqual(await store.counters(), { subscribes: 1, switches: 1 });
});

test("a subscription on a host that is not a browser push service is refused and not stored", async () => {
  const { handler, store } = make();
  const bad = subscription(1);
  bad.endpoint = "https://attacker.invalid/collect";
  assert.notEqual(bad.endpoint, subscription(1).endpoint); // the sabotage applied
  const res = await handler(request("POST", "/subscribe", { water_id: water, subscription: bad }));
  assert.equal(res.statusCode, 400);
  assert.equal(store.rows.size, 0);
  assert.deepEqual(await store.counters(), {});
});

test("a water id that is not a snapshot id, or bad keys, are refused", async () => {
  const { handler, store } = make();
  for (const body of [
    { water_id: "DROP TABLE", subscription: subscription(1) },
    { water_id: water, subscription: { ...subscription(1), keys: { p256dh: "short", auth: AUTH } } },
    { water_id: water, subscription: { ...subscription(1), keys: { p256dh: P256DH, auth: "x" } } },
    { water_id: water },
    {},
  ]) {
    const res = await handler(request("POST", "/subscribe", body));
    assert.equal(res.statusCode, 400, JSON.stringify(body));
  }
  assert.equal(store.rows.size, 0);
});

test("unsubscribe deletes the row and counts once; a second call is a no-op", async () => {
  const { handler, store } = make();
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  const first = await handler(request("POST", "/unsubscribe", { endpoint: endpoint(1) }));
  assert.deepEqual(json(first), { ok: true, removed: true });
  const second = await handler(request("POST", "/unsubscribe", { endpoint: endpoint(1) }));
  assert.deepEqual(json(second), { ok: true, removed: false });
  assert.equal(store.rows.size, 0);
  assert.deepEqual(await store.counters(), { subscribes: 1, unsubscribes: 1 });
});

test("send and counts need the bearer token; without it nothing is sent", async () => {
  const { handler, sender } = make();
  for (const headers of [{}, { authorization: "Bearer wrong" }, { authorization: `Basic ${TOKEN}` }]) {
    const res = await handler(request("POST", "/send", { events: [event()] }, headers));
    assert.equal(res.statusCode, 401);
    const c = await handler(request("GET", "/counts", undefined, headers));
    assert.equal(c.statusCode, 401);
  }
  assert.equal(sender.calls.length, 0);
});

test("send fans a message out to that water's subscribers and no one else", async () => {
  const { handler, store, sender } = make();
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(2) }));
  await handler(request("POST", "/subscribe", { water_id: "cdfw-999", subscription: subscription(3) }));
  const res = await handler(request("POST", "/send", { events: [event()] }, auth));
  assert.equal(res.statusCode, 200);
  assert.deepEqual(json(res), { events: 1, subscribers: 2, sent: 2, failed: 0, removed: 0, skipped: 0 });
  assert.deepEqual(sender.calls.map((c) => c.endpoint).sort(), [endpoint(1), endpoint(2)]);
  const call = sender.calls[0];
  assert.deepEqual(call.payload, {
    title: event().title,
    body: event().body,
    url: event().url,
    tag: water,
  });
  assert.equal(call.options.TTL, 3 * 24 * 3600);
  assert.equal(call.options.urgency, "normal");
  assert.deepEqual(call.options.vapidDetails, {
    subject: SECRETS.vapidSubject,
    publicKey: SECRETS.vapidPublicKey,
    privateKey: SECRETS.vapidPrivateKey,
  });
  const row = store.rows.get(`SUB#${endpointHash(endpoint(1))}`);
  assert.equal(row.last_sent_at, "2026-11-08T12:00:00.000Z");
  const untouched = store.rows.get(`SUB#${endpointHash(endpoint(3))}`);
  assert.equal(untouched.last_sent_at, undefined);
  assert.deepEqual(await store.counters(), { subscribes: 3, send_runs: 1, sends: 2 });
});

test("a 410 or 404 from the push service deletes the dead row; a 500 keeps it and counts a failure", async () => {
  const sender = fakeSender({ [endpoint(1)]: 410, [endpoint(2)]: 500 });
  const { handler, store } = make({ sender });
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(2) }));
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(3) }));
  const res = await handler(request("POST", "/send", { events: [event()] }, auth));
  assert.deepEqual(json(res), { events: 1, subscribers: 3, sent: 1, failed: 1, removed: 1, skipped: 0 });
  assert.equal(store.rows.has(`SUB#${endpointHash(endpoint(1))}`), false, "410: gone");
  assert.equal(store.rows.has(`SUB#${endpointHash(endpoint(2))}`), true, "500: kept");
  assert.deepEqual(await store.counters(), {
    subscribes: 3, send_runs: 1, sends: 1, failures: 1, removed_dead: 1,
  });
});

test("send refuses a message whose link is off this site, and sends nothing of that call", async () => {
  const { handler, sender } = make();
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  const bad = event({ url: "https://evil.invalid/water/x/" });
  assert.notEqual(bad.url, event().url);
  const res = await handler(request("POST", "/send", { events: [event(), bad] }, auth));
  assert.equal(res.statusCode, 400);
  assert.equal(sender.calls.length, 0);
});

test("a full batch of 100 messages fits the send route; 101 is refused whole", async () => {
  const { handler, sender } = make();
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  const hundred = Array.from({ length: 100 }, () => event());
  assert.ok(Buffer.byteLength(JSON.stringify({ events: hundred })) > 16 * 1024, "larger than a browser's limit");
  const ok = await handler(request("POST", "/send", { events: hundred }, auth));
  assert.equal(ok.statusCode, 200);
  assert.equal(sender.calls.length, 100);
  const over = await handler(request("POST", "/send", { events: [...hundred, event()] }, auth));
  assert.equal(over.statusCode, 413);
  assert.equal(sender.calls.length, 100);
});

test("a run with no schedule change sends nothing and bumps nothing", async () => {
  const { handler, store, sender } = make();
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  const res = await handler(request("POST", "/send", { events: [] }, auth));
  assert.deepEqual(json(res), { events: 0, subscribers: 0, sent: 0, failed: 0, removed: 0, skipped: 0 });
  assert.equal(sender.calls.length, 0);
  assert.deepEqual(await store.counters(), { subscribes: 1 });
});

test("a renewal moves the water from the old endpoint to the new one", async () => {
  const { handler, store } = make();
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  const res = await handler(request("POST", "/subscribe", { replaces: endpoint(1), subscription: subscription(2) }));
  assert.equal(res.statusCode, 200);
  assert.deepEqual(json(res), { ok: true, water_id: water });
  assert.equal(store.rows.has(`SUB#${endpointHash(endpoint(1))}`), false);
  assert.equal(store.rows.get(`SUB#${endpointHash(endpoint(2))}`).water_id, water);
  assert.deepEqual(await store.counters(), { subscribes: 1, renewals: 1 });
  const unknown = await handler(request("POST", "/subscribe", { replaces: endpoint(7), subscription: subscription(8) }));
  assert.equal(unknown.statusCode, 404);
});

test("counts returns the totals and the live subscription count", async () => {
  const { handler } = make();
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(2) }));
  await handler(request("POST", "/unsubscribe", { endpoint: endpoint(2) }));
  const res = await handler(request("GET", "/counts", undefined, auth));
  assert.equal(res.statusCode, 200);
  assert.deepEqual(json(res), {
    counters: { subscribes: 2, unsubscribes: 1 },
    live_subscriptions: 1,
    live_apple: 1,
  });
});

test("an unconfigured service answers 503 on every route and stores nothing", async () => {
  // The per-client limit is counted under a code keyed by the service's own
  // secret (DECISIONS 0074), so without it no subscription is taken.
  const { handler, store } = make({ secrets: async () => { throw new Error("missing SSM parameters"); } });
  const sub = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  assert.equal(sub.statusCode, 503);
  assert.equal(store.rows.size, 0);
  assert.equal(store.caps.size, 0);
  const res = await handler(request("POST", "/send", { events: [event()] }, auth));
  assert.equal(res.statusCode, 503);
});

test("unknown routes, non-JSON bodies and oversized bodies are refused", async () => {
  const { handler } = make();
  assert.equal((await handler(request("GET", "/"))).statusCode, 404);
  assert.equal((await handler(request("POST", "/nope", {}))).statusCode, 404);
  assert.equal((await handler(request("DELETE", "/subscribe", {}))).statusCode, 404);
  const broken = request("POST", "/subscribe");
  broken.body = "{not json";
  assert.equal((await handler(broken)).statusCode, 400);
  const huge = request("POST", "/subscribe", { water_id: water, pad: "x".repeat(20000) });
  assert.equal((await handler(huge)).statusCode, 413);
});

// ---- the limits on the two open routes (DECISIONS 0074) ----------------------

const small = (over) => ({ ...LIMITS, ...over });
const ip = (n) => `198.51.100.${n}`;

test("a browser's call over 4 KB is refused before it is read", async () => {
  const { handler, store } = make();
  const body = { water_id: water, subscription: subscription(1), replaces: "x".repeat(4096) };
  const res = await handler(request("POST", "/subscribe", body));
  assert.equal(res.statusCode, 413);
  const packed = request("POST", "/subscribe");
  packed.body = Buffer.from(JSON.stringify(body)).toString("base64");
  packed.isBase64Encoded = true;
  assert.equal((await handler(packed)).statusCode, 413);
  assert.equal(store.rows.size, 0);
  assert.equal(store.writes.take, 0, "a refused body is not counted against anyone");
});

test("a field the service does not take is refused, in the body, the subscription and its keys", async () => {
  const { handler, store } = make();
  const good = { water_id: water, subscription: subscription(1) };
  for (const body of [
    { ...good, note: "x" },
    { ...good, subscription: { ...subscription(1), extra: 1 } },
    { ...good, subscription: { ...subscription(1), keys: { p256dh: P256DH, auth: AUTH, more: "x" } } },
    { ...good, subscription: { ...subscription(1), expirationTime: "soon" } },
    { ...good, subscription: [subscription(1)] },
  ]) {
    assert.notDeepEqual(body, good); // the sabotage applied
    const res = await handler(request("POST", "/subscribe", body));
    assert.equal(res.statusCode, 400, JSON.stringify(body));
  }
  const bad = await handler(request("POST", "/unsubscribe", { endpoint: endpoint(1), also: 1 }));
  assert.equal(bad.statusCode, 400);
  assert.equal(store.rows.size, 0);
  // What a browser's toJSON() gives, expirationTime and all, is taken.
  const full = { ...good, subscription: { ...subscription(1), expirationTime: null } };
  assert.equal((await handler(request("POST", "/subscribe", full))).statusCode, 200);
});

test("a key that is not a point on the curve is refused", async () => {
  const { handler, store } = make();
  const offCurve = Buffer.concat([Buffer.from([4]), Buffer.alloc(64, 7)]).toString("base64url");
  assert.equal(offCurve.length, P256DH.length); // the right shape, the wrong point
  const res = await handler(
    request("POST", "/subscribe", { water_id: water, subscription: { endpoint: endpoint(1), keys: { p256dh: offCurve, auth: AUTH } } })
  );
  assert.equal(res.statusCode, 400);
  assert.equal(store.rows.size, 0);
});

test("one address spelled two ways is one row, and either spelling stops it", async () => {
  const { handler, store } = make();
  const plain = "https://web.push.apple.com/QAbc1";
  const other = "https://WEB.PUSH.APPLE.COM:443/QAbc1";
  assert.notEqual(plain, other);
  for (const spelled of [plain, other]) {
    const res = await handler(
      request("POST", "/subscribe", { water_id: water, subscription: { endpoint: spelled, keys: { p256dh: P256DH, auth: AUTH } } })
    );
    assert.equal(res.statusCode, 200, spelled);
  }
  assert.equal(store.rows.size, 1);
  assert.equal([...store.rows.values()][0].endpoint, plain);
  assert.deepEqual(await store.counters(), { subscribes: 1 });
  const stop = await handler(request("POST", "/unsubscribe", { endpoint: other }));
  assert.deepEqual(json(stop), { ok: true, removed: true });
  assert.equal(store.rows.size, 0);
});

test("the same subscription sent again the same day writes nothing; a day later it renews the expiry", async () => {
  const { handler, store, time } = make();
  const body = { water_id: water, subscription: subscription(1) };
  await handler(request("POST", "/subscribe", body));
  assert.equal(store.writes.put, 1);
  const first = [...store.rows.values()][0].expires_at;
  for (let i = 0; i < 3; i++) {
    assert.equal((await handler(request("POST", "/subscribe", body))).statusCode, 200);
  }
  assert.equal(store.writes.put, 1, "no second write");
  time.at = new Date("2026-11-10T12:00:00Z");
  assert.equal((await handler(request("POST", "/subscribe", body))).statusCode, 200);
  assert.equal(store.writes.put, 2);
  assert.ok([...store.rows.values()][0].expires_at > first);
  assert.deepEqual(await store.counters(), { subscribes: 1 });
});

test("one network gets 20 calls a day across both open routes; the next is 429 until the day turns", async () => {
  const { handler, store, time } = make();
  for (let i = 0; i < LIMITS.clientRequestsPerDay; i++) {
    const path = i % 2 ? "/unsubscribe" : "/subscribe";
    const body = i % 2 ? { endpoint: endpoint(1) } : { water_id: water, subscription: subscription(1) };
    assert.equal((await handler(request("POST", path, body))).statusCode, 200, `call ${i + 1}`);
  }
  const rowsBefore = store.rows.size;
  const takesBefore = store.writes.take;
  for (const path of ["/subscribe", "/unsubscribe"]) {
    const body = path === "/subscribe" ? { water_id: water, subscription: subscription(2) } : { endpoint: endpoint(1) };
    const res = await handler(request("POST", path, body));
    assert.equal(res.statusCode, 429, path);
    assert.equal(res.headers["retry-after"], String(12 * 3600), "until the UTC day ends");
  }
  assert.equal(store.rows.size, rowsBefore, "nothing stored or removed once limited");
  assert.equal(store.writes.take, takesBefore + 1, "a repeat after the first refusal costs no table write");
  // Another network is not affected.
  const other = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(3) }, {}, ip(1)));
  assert.equal(other.statusCode, 200);
  // The next UTC day starts a new count.
  time.at = new Date("2026-11-09T00:00:01Z");
  const next = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(2) }));
  assert.equal(next.statusCode, 200);
});

test("an IPv6 caller is counted by its /64, and a request that fails validation is not counted", async () => {
  const { handler, store } = make({ limits: small({ clientRequestsPerDay: 2 }) });
  const bad = await handler(request("POST", "/subscribe", { water_id: "NOT AN ID", subscription: subscription(1) }, {}, "2001:db8:1:2::1"));
  assert.equal(bad.statusCode, 400);
  assert.equal(store.writes.take, 0);
  const codes = [];
  for (const [n, from] of [[1, "2001:db8:1:2::1"], [2, "2001:db8:1:2:aaaa:bbbb:cccc:dddd"], [3, "2001:db8:1:2::9"]]) {
    const res = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(n) }, {}, from));
    codes.push(res.statusCode);
  }
  assert.deepEqual(codes, [200, 200, 429], "three addresses in one /64 are one caller");
  const elsewhere = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(4) }, {}, "2001:db8:1:3::1"));
  assert.equal(elsewhere.statusCode, 200);
});

test("the caller's address is never stored: the limit row is a keyed code that changes with the day", async () => {
  const { handler, store, time } = make();
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  time.at = new Date("2026-11-09T12:00:00Z");
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(2) }));
  const kept = JSON.stringify([[...store.rows.entries()], [...store.caps.entries()], await store.counters()]);
  assert.equal(kept.includes(CLIENT), false);
  assert.equal(kept.includes("203.0.113"), false);
  const clientKeys = [...store.caps.keys()].filter((k) => k.startsWith("CAP#CLIENT#"));
  assert.equal(clientKeys.length, 2);
  const [a, b] = clientKeys.map((k) => k.split("#").pop());
  assert.match(a, /^[0-9a-f]{32}$/);
  assert.notEqual(a, b, "the same network has a different code the next day");
  // Each limit row expires on its own a day later.
  const day1 = store.caps.get(clientKeys.find((k) => k.includes("2026-11-08")));
  assert.equal(day1.expires_at, Date.parse("2026-11-09T12:00:00Z") / 1000);
});

test("new subscriptions stop at the day's total, from any number of networks; a switch still works", async () => {
  const { handler, store, time } = make({ limits: small({ newSubscriptionsPerDay: 3 }) });
  for (let n = 1; n <= 3; n++) {
    const res = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(n) }, {}, ip(n)));
    assert.equal(res.statusCode, 200);
  }
  const over = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(4) }, {}, ip(4)));
  assert.equal(over.statusCode, 429);
  assert.equal(store.rows.size, 3);
  const moved = await handler(request("POST", "/subscribe", { water_id: "cdfw-999", subscription: subscription(1) }, {}, ip(1)));
  assert.equal(moved.statusCode, 200, "a stored browser changing its water is not a new subscription");
  const stop = await handler(request("POST", "/unsubscribe", { endpoint: endpoint(2) }, {}, ip(2)));
  assert.equal(stop.statusCode, 200, "stopping always works under the day's total");
  time.at = new Date("2026-11-09T12:00:00Z");
  const next = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(4) }, {}, ip(4)));
  assert.equal(next.statusCode, 200);
});

test("a water takes a fixed number of subscriptions, by a new sign-up or by a switch", async () => {
  const { handler, store } = make({ limits: small({ subscriptionsPerWater: 2 }) });
  for (let n = 1; n <= 2; n++) {
    await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(n) }, {}, ip(n)));
  }
  await handler(request("POST", "/subscribe", { water_id: "cdfw-999", subscription: subscription(3) }, {}, ip(3)));
  const full = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(4) }, {}, ip(4)));
  assert.equal(full.statusCode, 429);
  const switched = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(3) }, {}, ip(3)));
  assert.equal(switched.statusCode, 429);
  assert.equal((await store.listByWater(water)).length, 2);
  assert.equal(store.rows.get(`SUB#${endpointHash(endpoint(3))}`).water_id, "cdfw-999", "the refused switch changed nothing");
  const elsewhere = await handler(request("POST", "/subscribe", { water_id: "cdfw-555", subscription: subscription(4) }, {}, ip(4)));
  assert.equal(elsewhere.statusCode, 200);
});

test("the table takes a fixed number of live subscriptions; a renewal needs no new room", async () => {
  const { handler, store } = make({ limits: small({ liveSubscriptions: 2 }) });
  for (let n = 1; n <= 2; n++) {
    await handler(request("POST", "/subscribe", { water_id: `cdfw-${n}`, subscription: subscription(n) }, {}, ip(n)));
  }
  const full = await handler(request("POST", "/subscribe", { water_id: "cdfw-3", subscription: subscription(3) }, {}, ip(3)));
  assert.equal(full.statusCode, 429);
  assert.equal(store.rows.size, 2);
  const renewed = await handler(request("POST", "/subscribe", { replaces: endpoint(1), subscription: subscription(9) }, {}, ip(1)));
  assert.equal(renewed.statusCode, 200);
  assert.equal(store.rows.size, 2);
  await handler(request("POST", "/unsubscribe", { endpoint: endpoint(2) }, {}, ip(2)));
  const room = await handler(request("POST", "/subscribe", { water_id: "cdfw-3", subscription: subscription(3) }, {}, ip(3)));
  assert.equal(room.statusCode, 200);
});

test("two renewals of one row at once leave one row, not two", async () => {
  // The second call read the old row before the first deleted it: its
  // delete finds nothing, and the row it added is taken back.
  const store = memoryStore();
  const { handler } = make({ store });
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  const realDelete = store.deleteSubscription;
  const oldHash = endpointHash(endpoint(1));
  let raced = 0;
  store.deleteSubscription = async (hash) => {
    if (hash === oldHash) {
      raced += 1;
      return false; // already replaced by the other call
    }
    return realDelete(hash);
  };
  const res = await handler(request("POST", "/subscribe", { replaces: endpoint(1), subscription: subscription(2) }));
  assert.equal(raced, 1, "the sabotage applied");
  assert.equal(res.statusCode, 404);
  assert.equal(store.rows.has(`SUB#${endpointHash(endpoint(2))}`), false, "the added row was taken back");
  assert.equal(store.rows.size, 1);
  assert.deepEqual(await store.counters(), { subscribes: 1 });
});

test("a subscription the push service refuses three sends running is removed, when that service took another delivery", async () => {
  const sender = fakeSender({ [endpoint(1)]: 403 });
  const { handler, store } = make({ sender });
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }, {}, ip(1)));
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(2) }, {}, ip(2)));
  const key = `SUB#${endpointHash(endpoint(1))}`;
  for (const run of [1, 2]) {
    const res = await handler(request("POST", "/send", { events: [event()] }, auth));
    assert.deepEqual(json(res), { events: 1, subscribers: 2, sent: 1, failed: 1, removed: 0, skipped: 0 });
    assert.equal(store.rows.get(key).refusals, run);
  }
  const third = await handler(request("POST", "/send", { events: [event()] }, auth));
  assert.deepEqual(json(third), { events: 1, subscribers: 2, sent: 1, failed: 1, removed: 1, skipped: 0 });
  assert.equal(store.rows.has(key), false);
  assert.equal(store.rows.size, 1, "the working subscription stays");
  assert.equal((await store.counters()).removed_dead, 1);
});

test("refusals with no delivery to the same push service in the run count against no one", async () => {
  // Every subscription refused looks like this service's own credentials
  // being wrong, and must never empty the table.
  const sender = fakeSender({ [endpoint(1)]: 403, [endpoint(2)]: 401 });
  const { handler, store } = make({ sender });
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }, {}, ip(1)));
  await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(2) }, {}, ip(2)));
  // A delivery on another push service does not vouch for this one.
  const other = { endpoint: "https://fcm.googleapis.com/fcm/send/abc", keys: { p256dh: P256DH, auth: AUTH } };
  await handler(request("POST", "/subscribe", { water_id: water, subscription: other }, {}, ip(3)));
  for (let run = 0; run < 5; run++) {
    const res = await handler(request("POST", "/send", { events: [event()] }, auth));
    assert.deepEqual(json(res), { events: 1, subscribers: 3, sent: 1, failed: 2, removed: 0, skipped: 0 });
  }
  assert.equal(store.rows.size, 3);
  assert.equal(store.rows.get(`SUB#${endpointHash(endpoint(1))}`).refusals, undefined);
});

test("a delivery ends a run of refusals, and a 500 or a timeout is never a refusal", async () => {
  const failWith = { [endpoint(1)]: 400, [endpoint(3)]: 500 };
  const sender = fakeSender(failWith);
  const { handler, store } = make({ sender });
  for (let n = 1; n <= 3; n++) {
    await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(n) }, {}, ip(n)));
  }
  const key = `SUB#${endpointHash(endpoint(1))}`;
  await handler(request("POST", "/send", { events: [event()] }, auth));
  await handler(request("POST", "/send", { events: [event()] }, auth));
  assert.equal(store.rows.get(key).refusals, 2);
  delete failWith[endpoint(1)];
  await handler(request("POST", "/send", { events: [event()] }, auth));
  assert.equal(store.rows.get(key).refusals, 0, "delivered: the count starts over");
  failWith[endpoint(1)] = 400;
  await handler(request("POST", "/send", { events: [event()] }, auth));
  assert.equal(store.rows.has(key), true, "one refusal after a delivery removes nothing");
  assert.equal(store.rows.get(`SUB#${endpointHash(endpoint(3))}`).refusals, undefined, "a 500 is not a refusal");
  assert.equal(store.rows.size, 3);
});

test("a send call stops starting deliveries when its time is spent and says how many it skipped", async () => {
  let ms = 0;
  const sender = fakeSender();
  const slow = { calls: sender.calls, send: async (...args) => { ms += 4000; return sender.send(...args); } };
  const { handler, store } = make({ sender: slow, clock: () => ms, limits: small({ sendBudgetMs: 60_000 }) });
  for (let n = 1; n <= 40; n++) {
    await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(n) }, {}, ip(n)));
  }
  const res = await handler(request("POST", "/send", { events: [event(), event({ water_id: "cdfw-999" })] }, auth));
  assert.equal(res.statusCode, 200);
  // Ten at a time, 40 seconds a batch on this clock: the second batch ends
  // past the 60 seconds, so the last two batches are never started.
  assert.deepEqual(json(res), { events: 2, subscribers: 40, sent: 20, failed: 0, removed: 0, skipped: 20 });
  assert.equal(sender.calls.length, 20);
  assert.equal((await store.counters()).skipped, 20);
});
