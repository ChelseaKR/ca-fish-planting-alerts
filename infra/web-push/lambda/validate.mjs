// What the service accepts, and nothing else (DECISIONS 0069). Pure: no AWS,
// no network, so handler.test.mjs runs it as it is.
import { createHash } from "node:crypto";

export class ValidationError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.name = "ValidationError";
    this.status = status;
  }
}

// The push services a browser can hand out an endpoint on. Ported from
// Family Greenhouse's pushEndpoint.ts: the service must never be made to POST
// to an address a caller chose.
const ALLOWED_PUSH_HOSTS = new Set([
  "android.googleapis.com",
  "fcm.googleapis.com",
  "updates.push.services.mozilla.com",
  "push.services.mozilla.com",
  "web.push.apple.com",
]);
const ALLOWED_PUSH_HOST_SUFFIXES = [".notify.windows.com", ".wns.windows.com"];

export function isAllowedPushEndpoint(endpoint) {
  if (typeof endpoint !== "string" || endpoint.length > 2048) return false;
  let url;
  try {
    url = new URL(endpoint);
  } catch {
    return false;
  }
  const host = url.hostname.toLowerCase();
  return (
    url.protocol === "https:" &&
    (url.port === "" || url.port === "443") &&
    url.username === "" &&
    url.password === "" &&
    (ALLOWED_PUSH_HOSTS.has(host) || ALLOWED_PUSH_HOST_SUFFIXES.some((s) => host.endsWith(s)))
  );
}

// The row key: the endpoint's SHA-256, so the long provider URL never has to
// be a key and one browser is one row.
export function endpointHash(endpoint) {
  return createHash("sha256").update(endpoint).digest("hex");
}

// The v2 snapshot's water id pattern (schema/snapshot.v2.json).
const WATER_ID = /^[a-z]{2,4}-[a-z0-9]+(-[a-z0-9]+)*$/;
const B64URL = /^[A-Za-z0-9_-]+$/;

export function validateWaterId(value) {
  if (typeof value !== "string" || value.length > 120 || !WATER_ID.test(value)) {
    throw new ValidationError("water_id must be a snapshot water id");
  }
  return value;
}

function base64urlBytes(value, name, bytes) {
  if (typeof value !== "string" || !B64URL.test(value)) {
    throw new ValidationError(`${name} must be base64url`);
  }
  const buf = Buffer.from(value, "base64url");
  if (buf.length !== bytes) throw new ValidationError(`${name} must decode to ${bytes} bytes`);
  return buf;
}

// A PushSubscription as toJSON() gives it: the endpoint and its two keys. The
// p256dh key is an uncompressed P-256 point (65 bytes, 0x04 first); auth is
// 16 bytes (RFC 8291).
export function validateSubscription(value) {
  if (!value || typeof value !== "object") throw new ValidationError("subscription is required");
  if (!isAllowedPushEndpoint(value.endpoint)) {
    throw new ValidationError("endpoint must be an https address of a browser push service");
  }
  const keys = value.keys;
  if (!keys || typeof keys !== "object") throw new ValidationError("subscription.keys is required");
  const p256dh = base64urlBytes(keys.p256dh, "p256dh", 65);
  if (p256dh[0] !== 0x04) throw new ValidationError("p256dh must be an uncompressed P-256 point");
  base64urlBytes(keys.auth, "auth", 16);
  return { endpoint: value.endpoint, p256dh: keys.p256dh, auth: keys.auth };
}

function text(value, name, max) {
  if (typeof value !== "string" || value.trim() === "" || value.length > max) {
    throw new ValidationError(`${name} must be a string of at most ${max} characters`);
  }
  return value;
}

// One message from the pipeline (cfpa.push.Notification.to_json). The link
// must be a page of this site: the worker also checks, but the service never
// forwards an address it would not want opened.
export function validateEvent(value, siteOrigins) {
  if (!value || typeof value !== "object") throw new ValidationError("an event must be an object");
  const url = text(value.url, "url", 500);
  if (!siteOrigins.some((origin) => url === origin || url.startsWith(`${origin}/`))) {
    throw new ValidationError("url must be a page of this site");
  }
  const out = {
    water_id: validateWaterId(value.water_id),
    title: text(value.title, "title", 200),
    body: text(value.body, "body", 600),
    url,
  };
  if (value.tag !== undefined && value.tag !== null) out.tag = text(value.tag, "tag", 120);
  return out;
}
