// The web push service (DECISIONS 0069): one Lambda behind a function URL.
//
//   POST /subscribe    a browser's subscription, for one water (or a renewal
//                      that replaces an older endpoint under the same water)
//   POST /unsubscribe  delete it
//   POST /send         the pipeline's schedule-change messages (bearer token)
//   GET  /counts       the totals (bearer token)
//
// Everything AWS-shaped is injected (index.mjs wires DynamoDB, SSM and the
// web-push library), so handler.test.mjs runs this file against an in-memory
// store and a stand-in sender. The store interface:
//   getSubscription(hash) -> item | null      putSubscription(item)
//   deleteSubscription(hash) -> boolean       listByWater(waterId) -> items
//   touch(hash, fields)                       bump({counter: n, ...})
//   counters() -> object                      countSubscriptions(prefix?) -> number
//
// What is kept per browser: endpoint, its two keys, the water, created_at,
// last_sent_at (absent until a first send), expires_at. No IP address, no
// user agent, no account. Logs carry a route, a status and counts: never an
// endpoint, never a header.
import { createHash, timingSafeEqual } from "node:crypto";
import {
  ValidationError,
  endpointHash,
  isAllowedPushEndpoint,
  validateEvent,
  validateSubscription,
  validateWaterId,
} from "./validate.mjs";

// A browser's call is small; the pipeline's can carry 100 messages.
const MAX_BODY_BYTES = 16 * 1024;
const MAX_SEND_BODY_BYTES = 1024 * 1024;
const MAX_EVENTS = 100;
const APPLE_PUSH_PREFIX = "https://web.push.apple.com/";
const SEND_CHUNK = 10;
// RFC 8030 §5.2: how long a push service holds a message for an offline
// browser. The schedules are weekly, so three days reads right; the same
// value as cfpa.push.TTL_SECONDS.
const TTL_SECONDS = 3 * 24 * 3600;
// A subscription nothing has been sent to for this long is dropped by
// DynamoDB's TTL (the privacy page says "about 13 months").
const EXPIRES_AFTER_DAYS = 400;
const COUNTERS_PK = "COUNTERS";
const SUB_PREFIX = "SUB#";
const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

function reply(status, body) {
  return { statusCode: status, headers: JSON_HEADERS, body: JSON.stringify(body) };
}

function epochSeconds(date, plusDays) {
  return Math.floor(date.getTime() / 1000) + plusDays * 24 * 3600;
}

function readBody(event, maxBytes = MAX_BODY_BYTES) {
  if (event.body === undefined || event.body === null || event.body === "") {
    throw new ValidationError("a JSON body is required");
  }
  const raw = event.isBase64Encoded ? Buffer.from(event.body, "base64").toString("utf8") : event.body;
  if (Buffer.byteLength(raw, "utf8") > maxBytes) {
    throw new ValidationError("body too large", 413);
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new ValidationError("body must be JSON");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new ValidationError("body must be a JSON object");
  }
  return parsed;
}

function bearer(event) {
  const headers = event.headers || {};
  const value = headers.authorization || headers.Authorization || "";
  const m = /^Bearer\s+(\S+)$/i.exec(value.trim());
  return m ? m[1] : "";
}

function sameToken(given, expected) {
  if (!given || !expected || expected.length < 32) return false;
  const a = createHash("sha256").update(given).digest();
  const b = createHash("sha256").update(expected).digest();
  return timingSafeEqual(a, b);
}

export function createHandler({ store, secrets, sender, siteOrigins, now = () => new Date() }) {
  if (!Array.isArray(siteOrigins) || siteOrigins.length === 0) {
    throw new Error("siteOrigins must name at least one https origin");
  }

  async function subscribe(event) {
    const body = readBody(event);
    const sub = validateSubscription(body.subscription);
    const hash = endpointHash(sub.endpoint);
    const at = now();
    const existing = await store.getSubscription(hash);
    let waterId;
    let counter = null;
    let oldHash = null;
    if (body.water_id === undefined && typeof body.replaces === "string") {
      // The worker's renewal (pushsubscriptionchange): it knows the old
      // endpoint, not the water, so the water comes from the old row.
      if (!isAllowedPushEndpoint(body.replaces)) {
        throw new ValidationError("replaces must be an https address of a browser push service");
      }
      oldHash = endpointHash(body.replaces);
      const old = await store.getSubscription(oldHash);
      if (!old) throw new ValidationError("nothing to replace", 404);
      waterId = old.water_id;
      counter = "renewals";
    } else {
      waterId = validateWaterId(body.water_id);
      if (!existing) counter = "subscribes";
      else if (existing.water_id !== waterId) counter = "switches";
    }
    const item = {
      pk: SUB_PREFIX + hash,
      kind: "subscription",
      water_id: waterId,
      endpoint: sub.endpoint,
      p256dh: sub.p256dh,
      auth: sub.auth,
      created_at: existing ? existing.created_at : at.toISOString(),
      expires_at: epochSeconds(at, EXPIRES_AFTER_DAYS),
    };
    if (existing && existing.last_sent_at) item.last_sent_at = existing.last_sent_at;
    await store.putSubscription(item);
    if (oldHash && oldHash !== hash) await store.deleteSubscription(oldHash);
    if (counter) await store.bump({ [counter]: 1 });
    return reply(200, { ok: true, water_id: waterId });
  }

  async function unsubscribe(event) {
    const body = readBody(event);
    if (!isAllowedPushEndpoint(body.endpoint)) {
      throw new ValidationError("endpoint must be an https address of a browser push service");
    }
    const removed = await store.deleteSubscription(endpointHash(body.endpoint));
    if (removed) await store.bump({ unsubscribes: 1 });
    return reply(200, { ok: true, removed });
  }

  async function sendOne(item, payload, vapidDetails, at, totals) {
    const hash = item.pk.slice(SUB_PREFIX.length);
    try {
      await sender.send(
        { endpoint: item.endpoint, keys: { p256dh: item.p256dh, auth: item.auth } },
        payload,
        { TTL: TTL_SECONDS, urgency: "normal", timeout: 5000, vapidDetails }
      );
      totals.sent += 1;
      await store.touch(hash, {
        last_sent_at: at.toISOString(),
        expires_at: epochSeconds(at, EXPIRES_AFTER_DAYS),
      });
    } catch (err) {
      const code = err && typeof err.statusCode === "number" ? err.statusCode : null;
      if (code === 404 || code === 410) {
        // The browser dropped the subscription for good.
        await store.deleteSubscription(hash);
        totals.removed += 1;
      } else {
        totals.failed += 1;
        console.log(JSON.stringify({ route: "send", push_failed: true, status: code }));
      }
    }
  }

  async function send(event, config) {
    const body = readBody(event, MAX_SEND_BODY_BYTES);
    if (!Array.isArray(body.events)) throw new ValidationError("events must be an array");
    if (body.events.length > MAX_EVENTS) {
      throw new ValidationError(`at most ${MAX_EVENTS} events per call`, 413);
    }
    const events = body.events.map((e) => validateEvent(e, siteOrigins));
    const vapidDetails = {
      subject: config.vapidSubject,
      publicKey: config.vapidPublicKey,
      privateKey: config.vapidPrivateKey,
    };
    const totals = { events: events.length, subscribers: 0, sent: 0, failed: 0, removed: 0 };
    const at = now();
    for (const ev of events) {
      const items = await store.listByWater(ev.water_id);
      totals.subscribers += items.length;
      const payload = JSON.stringify({ title: ev.title, body: ev.body, url: ev.url, tag: ev.tag });
      for (let i = 0; i < items.length; i += SEND_CHUNK) {
        await Promise.all(
          items.slice(i, i + SEND_CHUNK).map((item) => sendOne(item, payload, vapidDetails, at, totals))
        );
      }
    }
    if (events.length > 0) {
      await store.bump({
        send_runs: 1,
        sends: totals.sent,
        failures: totals.failed,
        removed_dead: totals.removed,
      });
    }
    console.log(JSON.stringify({ route: "send", ...totals }));
    return reply(200, totals);
  }

  async function counts() {
    return reply(200, {
      counters: await store.counters(),
      live_subscriptions: await store.countSubscriptions(),
      // How many finished the iPhone or iPad path: the number the test exists
      // to learn (DECISIONS 0069). The push service's host says it; nothing
      // else about a browser is kept.
      live_apple: await store.countSubscriptions(APPLE_PUSH_PREFIX),
    });
  }

  return async function handler(event) {
    const method = (event.requestContext?.http?.method || "").toUpperCase();
    const path = (event.rawPath || "/").replace(/\/+$/, "") || "/";
    try {
      if (method === "OPTIONS") return { statusCode: 204, headers: {}, body: "" };
      if (method === "POST" && path === "/subscribe") return await subscribe(event);
      if (method === "POST" && path === "/unsubscribe") return await unsubscribe(event);
      if ((method === "POST" && path === "/send") || (method === "GET" && path === "/counts")) {
        let config;
        try {
          config = await secrets();
        } catch (err) {
          console.log(JSON.stringify({ route: path, not_configured: true, error: err?.name || "Error" }));
          return reply(503, { error: "the service is not configured" });
        }
        if (!sameToken(bearer(event), config.senderToken)) return reply(401, { error: "unauthorized" });
        return path === "/send" ? await send(event, config) : await counts();
      }
      return reply(404, { error: "not found" });
    } catch (err) {
      if (err instanceof ValidationError) return reply(err.status, { error: err.message });
      console.log(JSON.stringify({ route: path, failed: true, error: err?.name || "Error" }));
      return reply(500, { error: "internal error" });
    }
  };
}
