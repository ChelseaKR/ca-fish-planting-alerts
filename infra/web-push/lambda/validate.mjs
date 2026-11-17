// What the service accepts, and nothing else (DECISIONS 0069). Pure: no AWS,
// no network, so handler.test.mjs runs it as it is.
import { createECDH, createHash, createHmac } from "node:crypto";
import { isIPv4, isIPv6 } from "node:net";

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

// Longer than any address a browser push service issues today (a few
// hundred characters), far shorter than a URL can be.
export const MAX_ENDPOINT_CHARS = 1024;

// The endpoint as the URL standard writes it, or null when it is not an
// address a browser push service hands out: https, a listed host, the default
// port, no credentials, no fragment, and a path that carries the
// subscription's own token. Two spellings of one address (a host in capitals,
// an explicit :443) come back as the same string, so they are one row.
export function canonicalPushEndpoint(endpoint) {
  if (typeof endpoint !== "string" || endpoint.length > MAX_ENDPOINT_CHARS) return null;
  let url;
  try {
    url = new URL(endpoint);
  } catch {
    return null;
  }
  const host = url.hostname.toLowerCase();
  const ok =
    url.protocol === "https:" &&
    url.port === "" &&
    url.username === "" &&
    url.password === "" &&
    url.hash === "" &&
    !endpoint.includes("#") &&
    url.pathname.length > 1 &&
    (ALLOWED_PUSH_HOSTS.has(host) || ALLOWED_PUSH_HOST_SUFFIXES.some((s) => host.endsWith(s)));
  if (!ok || url.href.length > MAX_ENDPOINT_CHARS) return null;
  return url.href;
}

export function isAllowedPushEndpoint(endpoint) {
  return canonicalPushEndpoint(endpoint) !== null;
}

// The row key: the SHA-256 of the endpoint as canonicalPushEndpoint writes
// it, so the long provider URL never has to be a key and one browser is one
// row however the address was spelled.
export function endpointHash(endpoint) {
  return createHash("sha256").update(canonicalPushEndpoint(endpoint) ?? endpoint).digest("hex");
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

function plainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function onlyKeys(value, allowed, name) {
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) throw new ValidationError(`${name} has a field this service does not take`);
  }
}

// Exactly `bytes` bytes of unpadded base64url, in the one spelling that
// encodes them (so the same key cannot arrive written two ways).
function base64urlBytes(value, name, bytes) {
  const chars = Math.ceil((bytes * 4) / 3);
  if (typeof value !== "string" || value.length !== chars || !B64URL.test(value)) {
    throw new ValidationError(`${name} must be ${chars} characters of base64url`);
  }
  const buf = Buffer.from(value, "base64url");
  if (buf.length !== bytes || buf.toString("base64url") !== value) {
    throw new ValidationError(`${name} must decode to ${bytes} bytes`);
  }
  return buf;
}

// A point that is not on the curve can never be encrypted to, so a message
// to it would fail on every send.
function isP256Point(buf) {
  try {
    const ecdh = createECDH("prime256v1");
    ecdh.generateKeys();
    ecdh.computeSecret(buf);
    return true;
  } catch {
    return false;
  }
}

const SUBSCRIPTION_FIELDS = ["endpoint", "expirationTime", "keys"];
const KEY_FIELDS = ["p256dh", "auth"];

// A PushSubscription as toJSON() gives it: the endpoint, an expirationTime
// this service does not use, and the two keys. The p256dh key is an
// uncompressed P-256 point (65 bytes, 0x04 first, on the curve); auth is 16
// bytes (RFC 8291). Anything else in the object is refused. The endpoint
// comes back in its canonical spelling.
export function validateSubscription(value) {
  if (!plainObject(value)) throw new ValidationError("subscription is required");
  onlyKeys(value, SUBSCRIPTION_FIELDS, "subscription");
  const endpoint = canonicalPushEndpoint(value.endpoint);
  if (endpoint === null) {
    throw new ValidationError("endpoint must be an https address of a browser push service");
  }
  const expires = value.expirationTime;
  if (expires !== undefined && expires !== null && !(typeof expires === "number" && Number.isFinite(expires))) {
    throw new ValidationError("subscription.expirationTime must be a number or null");
  }
  const keys = value.keys;
  if (!plainObject(keys)) throw new ValidationError("subscription.keys is required");
  onlyKeys(keys, KEY_FIELDS, "subscription.keys");
  const p256dh = base64urlBytes(keys.p256dh, "p256dh", 65);
  if (p256dh[0] !== 0x04 || !isP256Point(p256dh)) {
    throw new ValidationError("p256dh must be an uncompressed P-256 point");
  }
  base64urlBytes(keys.auth, "auth", 16);
  return { endpoint, p256dh: keys.p256dh, auth: keys.auth };
}

// The network a request came from, as coarse as still tells two households
// apart: a whole IPv4 address, or the /64 an IPv6 address sits in (one home
// or phone usually holds the whole /64). Anything else is one shared bucket.
export function clientNetwork(ip) {
  if (typeof ip !== "string") return "unknown";
  if (isIPv4(ip)) return ip;
  if (!isIPv6(ip)) return "unknown";
  const bare = ip.split("%")[0].toLowerCase();
  const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/.exec(bare);
  if (mapped) return mapped[1];
  const [head, tail] = bare.split("::");
  const left = head ? head.split(":") : [];
  const right = tail ? tail.split(":") : [];
  const groups = tail === undefined ? left : [...left, ...Array(Math.max(0, 8 - left.length - right.length)).fill("0"), ...right];
  return groups
    .slice(0, 4)
    .map((g) => g.replace(/^0+(?=.)/, ""))
    .join(":");
}

// The per-client counter's name: a keyed code of the network and the day,
// never the address. The key is derived from a secret only the service
// holds, and the day is part of the input, so one network's code on one day
// says nothing about its code on the next.
export function clientCode(secret, day, ip) {
  const key = createHmac("sha256", secret).update("trout-truck web push client cap v1").digest();
  return createHmac("sha256", key).update(`${day}|${clientNetwork(ip)}`).digest("hex").slice(0, 32);
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
