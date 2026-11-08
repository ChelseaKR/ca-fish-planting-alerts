// node --test: the handler against an in-memory store and a stand-in sender.
// No npm install, no AWS. Every negative control first shows its sabotage
// changed the input, then that the handler refused it.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createHandler } from "./handler.mjs";
import { endpointHash } from "./validate.mjs";

const ORIGIN = "https://trouttruck.com";
const TOKEN = "t".repeat(48);
const SECRETS = {
  vapidPublicKey: "B" + "A".repeat(86),
  vapidPrivateKey: "p".repeat(43),
  vapidSubject: "mailto:test@example.invalid",
  senderToken: TOKEN,
};
const P256DH = Buffer.concat([Buffer.from([4]), Buffer.alloc(64, 7)]).toString("base64url");
const AUTH = Buffer.alloc(16, 9).toString("base64url");

function endpoint(n) {
  return `https://web.push.apple.com/QAbc${n}`;
}
function subscription(n) {
  return { endpoint: endpoint(n), keys: { p256dh: P256DH, auth: AUTH } };
}

function memoryStore() {
  const rows = new Map();
  let counters = {};
  return {
    rows,
    get counters_() {
      return counters;
    },
    async getSubscription(hash) {
      return rows.get(`SUB#${hash}`) || null;
    },
    async putSubscription(item) {
      rows.set(item.pk, { ...item });
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

function make({ store = memoryStore(), sender = fakeSender(), secrets = async () => SECRETS } = {}) {
  const handler = createHandler({
    store,
    secrets,
    sender,
    siteOrigins: [ORIGIN],
    now: () => new Date("2026-11-08T12:00:00Z"),
  });
  return { handler, store, sender };
}

function request(method, path, body, headers = {}) {
  return {
    requestContext: { http: { method } },
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
  assert.deepEqual(json(res), { events: 1, subscribers: 2, sent: 2, failed: 0, removed: 0 });
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
  assert.deepEqual(json(res), { events: 1, subscribers: 3, sent: 1, failed: 1, removed: 1 });
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
  assert.deepEqual(json(res), { events: 0, subscribers: 0, sent: 0, failed: 0, removed: 0 });
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

test("an unconfigured service answers 503 on the token routes and still takes subscriptions", async () => {
  const { handler, store } = make({ secrets: async () => { throw new Error("missing SSM parameters"); } });
  const sub = await handler(request("POST", "/subscribe", { water_id: water, subscription: subscription(1) }));
  assert.equal(sub.statusCode, 200);
  assert.equal(store.rows.size, 1);
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
