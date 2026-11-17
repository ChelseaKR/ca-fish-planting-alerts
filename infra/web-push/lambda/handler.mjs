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
//   countByWater(waterId) -> number           strike(hash) -> failures so far
//   take(key, max, expiresAt) -> boolean      (one more under `max`, or false)
//
// What is kept per browser: endpoint, its two keys, the water, created_at,
// last_sent_at (absent until a first send), expires_at, and a count of
// refused deliveries. No IP address, no user agent, no account. Logs carry a
// route, a status and counts: never an endpoint, never a header.
//
// The limits on the two open routes (DECISIONS 0074) are LIMITS below. The
// per-client one counts under a keyed code of the caller's network and the
// day (validate.mjs clientCode), in a row that expires a day later.
import { createHash, timingSafeEqual } from "node:crypto";
import {
  ValidationError,
  canonicalPushEndpoint,
  clientCode,
  endpointHash,
  validateEvent,
  validateSubscription,
  validateWaterId,
} from "./validate.mjs";

// What the two open routes will take. The 60-day test passes at 25 live
// subscriptions (DECISIONS 0069), so each figure is far above real use and
// far below what would cost money or slow a send.
export const LIMITS = Object.freeze({
  // /subscribe and /unsubscribe calls from one network in one UTC day.
  clientRequestsPerDay: 20,
  // New subscriptions, from everyone, in one UTC day.
  newSubscriptionsPerDay: 100,
  // Live subscriptions on one water: bounds one message's fan-out.
  subscriptionsPerWater: 100,
  // Live subscriptions in all.
  liveSubscriptions: 2000,
  // A push service refusing a subscription this many sends in a row (400,
  // 401 or 403, with another delivery to the same service succeeding in the
  // same run) means the subscription is dead.
  refusalsBeforeRemoval: 3,
  // How long one /send call keeps starting deliveries. The function's own
  // timeout is 120 seconds (main.tf).
  sendBudgetMs: 90_000,
});

// A browser's call is a subscription and a water id; the pipeline's can
// carry 100 messages.
const MAX_BODY_BYTES = 4 * 1024;
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
const SUB_PREFIX = "SUB#";
const CLIENT_CAP_PREFIX = "CAP#CLIENT#";
const NEW_CAP_PREFIX = "CAP#NEW#";
const DAY_SECONDS = 24 * 3600;
// Codes this container has already seen refused today: a repeat costs no
// table write. Bounded, and gone with the container.
const MAX_REFUSED_NOTED = 2000;
const SUBSCRIBE_FIELDS = ["water_id", "subscription", "replaces"];
const UNSUBSCRIBE_FIELDS = ["endpoint"];
const REFUSAL_CODES = new Set([400, 401, 403]);
const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

function reply(status, body, headers = {}) {
  return { statusCode: status, headers: { ...JSON_HEADERS, ...headers }, body: JSON.stringify(body) };
}

// 429 with how long until the UTC day turns over.
class LimitError extends Error {
  constructor(message, retryAfterSeconds) {
    super(message);
    this.name = "LimitError";
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

function utcDay(date) {
  return date.toISOString().slice(0, 10);
}

function secondsLeftInDay(date) {
  return DAY_SECONDS - (Math.floor(date.getTime() / 1000) % DAY_SECONDS);
}

function pushHost(endpoint) {
  try {
    return new URL(endpoint).hostname;
  } catch {
    return "";
  }
}

function onlyFields(body, allowed) {
  for (const key of Object.keys(body)) {
    if (!allowed.includes(key)) throw new ValidationError("the body has a field this service does not take");
  }
}

function epochSeconds(date, plusDays) {
  return Math.floor(date.getTime() / 1000) + plusDays * 24 * 3600;
}

function readBody(event, maxBytes = MAX_BODY_BYTES) {
  if (event.body === undefined || event.body === null || event.body === "") {
    throw new ValidationError("a JSON body is required");
  }
  // Checked before decoding, so an oversized body is never unpacked.
  if (typeof event.body !== "string" || event.body.length > maxBytes * 2) {
    throw new ValidationError("body too large", 413);
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

export function createHandler({
  store,
  secrets,
  sender,
  siteOrigins,
  now = () => new Date(),
  clock = () => Date.now(),
  limits = LIMITS,
}) {
  if (!Array.isArray(siteOrigins) || siteOrigins.length === 0) {
    throw new Error("siteOrigins must name at least one https origin");
  }
  const refusedToday = new Map();

  // One /subscribe or /unsubscribe call against the caller's daily allowance.
  // The counter's name is a keyed code (never the address), so the service
  // must be configured: the key comes from its own secret.
  async function countClient(event, config, at) {
    const day = utcDay(at);
    const code = clientCode(config.senderToken, day, event.requestContext?.http?.sourceIp);
    const tooMany = new LimitError("too many requests from this network today", secondsLeftInDay(at));
    if (refusedToday.get(code) === day) throw tooMany;
    const ok = await store.take(
      `${CLIENT_CAP_PREFIX}${day}#${code}`,
      limits.clientRequestsPerDay,
      epochSeconds(at, 1)
    );
    if (ok) return;
    if (refusedToday.size >= MAX_REFUSED_NOTED) refusedToday.clear();
    refusedToday.set(code, day);
    throw tooMany;
  }

  // Room for one more subscription on this water.
  async function checkWater(waterId, at) {
    if ((await store.countByWater(waterId)) >= limits.subscriptionsPerWater) {
      throw new LimitError("this water has all the subscriptions the service takes", secondsLeftInDay(at));
    }
  }

  // Room for one more subscription at all: today's allowance first (which
  // also bounds how often the table is counted), then the live total.
  async function checkNew(at) {
    const day = utcDay(at);
    const ok = await store.take(`${NEW_CAP_PREFIX}${day}`, limits.newSubscriptionsPerDay, epochSeconds(at, 1));
    if (!ok) throw new LimitError("the service has taken all of today's new subscriptions", secondsLeftInDay(at));
    if ((await store.countSubscriptions()) >= limits.liveSubscriptions) {
      throw new LimitError("the service has all the subscriptions it takes", secondsLeftInDay(at));
    }
  }

  async function subscribe(event, config) {
    const body = readBody(event);
    onlyFields(body, SUBSCRIBE_FIELDS);
    const sub = validateSubscription(body.subscription);
    const renewal = body.water_id === undefined && typeof body.replaces === "string";
    let waterId = null;
    let oldHash = null;
    if (renewal) {
      // The worker's renewal (pushsubscriptionchange): it knows the old
      // endpoint, not the water, so the water comes from the old row.
      if (canonicalPushEndpoint(body.replaces) === null) {
        throw new ValidationError("replaces must be an https address of a browser push service");
      }
      oldHash = endpointHash(body.replaces);
    } else {
      waterId = validateWaterId(body.water_id);
    }
    const at = now();
    await countClient(event, config, at);
    const hash = endpointHash(sub.endpoint);
    const existing = await store.getSubscription(hash);
    const expiresAt = epochSeconds(at, EXPIRES_AFTER_DAYS);
    let counter = null;
    if (renewal) {
      const old = await store.getSubscription(oldHash);
      if (!old) throw new ValidationError("nothing to replace", 404);
      waterId = old.water_id;
      counter = "renewals";
      // A renewal swaps one row for another, so it needs no new room.
    } else if (!existing) {
      await checkWater(waterId, at);
      await checkNew(at);
      counter = "subscribes";
    } else if (existing.water_id !== waterId) {
      await checkWater(waterId, at);
      counter = "switches";
    } else if (
      existing.p256dh === sub.p256dh &&
      existing.auth === sub.auth &&
      existing.expires_at >= expiresAt - DAY_SECONDS
    ) {
      // The same subscription for the same water, already stored today:
      // nothing to write.
      return reply(200, { ok: true, water_id: waterId });
    }
    const item = {
      pk: SUB_PREFIX + hash,
      kind: "subscription",
      water_id: waterId,
      endpoint: sub.endpoint,
      p256dh: sub.p256dh,
      auth: sub.auth,
      created_at: existing ? existing.created_at : at.toISOString(),
      expires_at: expiresAt,
    };
    if (existing && existing.last_sent_at) item.last_sent_at = existing.last_sent_at;
    await store.putSubscription(item);
    if (oldHash && oldHash !== hash && !(await store.deleteSubscription(oldHash))) {
      // Another call replaced the old row first. A renewal is one row for
      // one row, so the row this call just added is taken back.
      if (!existing) await store.deleteSubscription(hash);
      throw new ValidationError("nothing to replace", 404);
    }
    if (counter) await store.bump({ [counter]: 1 });
    return reply(200, { ok: true, water_id: waterId });
  }

  async function unsubscribe(event, config) {
    const body = readBody(event);
    onlyFields(body, UNSUBSCRIBE_FIELDS);
    if (canonicalPushEndpoint(body.endpoint) === null) {
      throw new ValidationError("endpoint must be an https address of a browser push service");
    }
    await countClient(event, config, now());
    const removed = await store.deleteSubscription(endpointHash(body.endpoint));
    if (removed) await store.bump({ unsubscribes: 1 });
    return reply(200, { ok: true, removed });
  }

  async function sendOne(item, payload, vapidDetails, at, run) {
    const hash = item.pk.slice(SUB_PREFIX.length);
    const host = pushHost(item.endpoint);
    try {
      await sender.send(
        { endpoint: item.endpoint, keys: { p256dh: item.p256dh, auth: item.auth } },
        payload,
        { TTL: TTL_SECONDS, urgency: "normal", timeout: 5000, vapidDetails }
      );
    } catch (err) {
      const code = err && typeof err.statusCode === "number" ? err.statusCode : null;
      if (code === 404 || code === 410) {
        // The browser dropped the subscription for good.
        await store.deleteSubscription(hash);
        run.totals.removed += 1;
        return;
      }
      run.totals.failed += 1;
      if (REFUSAL_CODES.has(code)) run.refused.push({ hash, host });
      console.log(JSON.stringify({ route: "send", push_failed: true, status: code }));
      return;
    }
    run.totals.sent += 1;
    run.deliveredHosts.add(host);
    const fields = { last_sent_at: at.toISOString(), expires_at: epochSeconds(at, EXPIRES_AFTER_DAYS) };
    // A delivery ends any run of refusals.
    if (item.refusals) fields.refusals = 0;
    try {
      await store.touch(hash, fields);
    } catch (err) {
      // The message went; only the bookkeeping did not.
      console.log(JSON.stringify({ route: "send", touch_failed: true, error: err?.name || "Error" }));
    }
  }

  // A refusal counts against a subscription only when the same push service
  // took another delivery in this run: that shows the refusal is about the
  // subscription and not about this service's own credentials.
  async function settleRefusals(run) {
    for (const { hash, host } of run.refused) {
      if (!run.deliveredHosts.has(host)) continue;
      const refusals = await store.strike(hash);
      if (refusals >= limits.refusalsBeforeRemoval && (await store.deleteSubscription(hash))) {
        run.totals.removed += 1;
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
    // `skipped` is the subscriptions a call ran out of time for: they get
    // nothing from this run, and the number in the answer says so.
    const totals = { events: events.length, subscribers: 0, sent: 0, failed: 0, removed: 0, skipped: 0 };
    const run = { totals, refused: [], deliveredHosts: new Set() };
    const at = now();
    const deadline = clock() + limits.sendBudgetMs;
    for (const ev of events) {
      const items = await store.listByWater(ev.water_id);
      totals.subscribers += items.length;
      const payload = JSON.stringify({ title: ev.title, body: ev.body, url: ev.url, tag: ev.tag });
      for (let i = 0; i < items.length; i += SEND_CHUNK) {
        if (clock() >= deadline) {
          totals.skipped += items.length - i;
          break;
        }
        await Promise.all(
          items.slice(i, i + SEND_CHUNK).map((item) => sendOne(item, payload, vapidDetails, at, run))
        );
      }
    }
    await settleRefusals(run);
    if (events.length > 0) {
      await store.bump({
        send_runs: 1,
        sends: totals.sent,
        failures: totals.failed,
        removed_dead: totals.removed,
        skipped: totals.skipped,
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
      const open = method === "POST" && (path === "/subscribe" || path === "/unsubscribe");
      const token = (method === "POST" && path === "/send") || (method === "GET" && path === "/counts");
      if (!open && !token) return reply(404, { error: "not found" });
      let config;
      try {
        config = await secrets();
      } catch (err) {
        console.log(JSON.stringify({ route: path, not_configured: true, error: err?.name || "Error" }));
        return reply(503, { error: "the service is not configured" });
      }
      if (path === "/subscribe") return await subscribe(event, config);
      if (path === "/unsubscribe") return await unsubscribe(event, config);
      if (!sameToken(bearer(event), config.senderToken)) return reply(401, { error: "unauthorized" });
      return path === "/send" ? await send(event, config) : await counts();
    } catch (err) {
      if (err instanceof ValidationError) return reply(err.status, { error: err.message });
      if (err instanceof LimitError) {
        console.log(JSON.stringify({ route: path, limited: true }));
        return reply(429, { error: err.message }, { "retry-after": String(err.retryAfterSeconds) });
      }
      console.log(JSON.stringify({ route: path, failed: true, error: err?.name || "Error" }));
      return reply(500, { error: "internal error" });
    }
  };
}
