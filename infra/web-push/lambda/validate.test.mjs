import assert from "node:assert/strict";
import { createECDH } from "node:crypto";
import { test } from "node:test";
import {
  canonicalPushEndpoint,
  clientCode,
  clientNetwork,
  endpointHash,
  isAllowedPushEndpoint,
  validateEvent,
  validateSubscription,
} from "./validate.mjs";

function p256Point() {
  const ecdh = createECDH("prime256v1");
  ecdh.generateKeys();
  return ecdh.getPublicKey();
}

test("push endpoints: the browsers' services over https, nothing else", () => {
  for (const ok of [
    "https://web.push.apple.com/QAbc",
    "https://fcm.googleapis.com/fcm/send/abc",
    "https://updates.push.services.mozilla.com/wpush/v2/x",
    "https://db5p.notify.windows.com/w/?token=x",
  ]) {
    assert.equal(isAllowedPushEndpoint(ok), true, ok);
  }
  for (const bad of [
    "http://web.push.apple.com/QAbc",
    "https://web.push.apple.com:8443/QAbc",
    "https://user:pw@web.push.apple.com/QAbc",
    "https://web.push.apple.com.evil.invalid/x",
    "https://example.com/",
    "not a url",
    42,
    "https://web.push.apple.com/" + "x".repeat(3000),
    "https://web.push.apple.com/" + "x".repeat(1024),
    "https://web.push.apple.com/",
    "https://web.push.apple.com",
    "https://web.push.apple.com/QAbc#part",
    "https://web.push.apple.com/QAbc#",
    null,
    { href: "https://web.push.apple.com/QAbc" },
  ]) {
    assert.equal(isAllowedPushEndpoint(bad), false, String(bad));
  }
});

test("an endpoint has one spelling, and the row key follows it", () => {
  const plain = "https://fcm.googleapis.com/fcm/send/abc:DEF_ghi-123";
  assert.equal(canonicalPushEndpoint(plain), plain, "a browser's own spelling is kept as it is");
  for (const other of [
    "https://FCM.googleapis.com/fcm/send/abc:DEF_ghi-123",
    "https://fcm.googleapis.com:443/fcm/send/abc:DEF_ghi-123",
    "HTTPS://fcm.googleapis.com/fcm/send/abc:DEF_ghi-123",
  ]) {
    assert.notEqual(other, plain);
    assert.equal(canonicalPushEndpoint(other), plain, other);
    assert.equal(endpointHash(other), endpointHash(plain), other);
  }
  // The token is case-sensitive: a different token is a different browser.
  assert.notEqual(endpointHash(plain.toLowerCase()), endpointHash(plain));
  const windows = "https://db5p.notify.windows.com/w/?token=BQYAAAB%2bx%3d";
  assert.equal(canonicalPushEndpoint(windows), windows);
});

test("the row key is the endpoint's full SHA-256", () => {
  assert.match(endpointHash("https://web.push.apple.com/QAbc"), /^[0-9a-f]{64}$/);
  assert.notEqual(endpointHash("https://web.push.apple.com/a"), endpointHash("https://web.push.apple.com/b"));
});

test("a subscription needs a 65-byte uncompressed P-256 point on the curve and a 16-byte auth secret", () => {
  const point = p256Point();
  const p256dh = point.toString("base64url");
  const auth = Buffer.alloc(16, 2).toString("base64url");
  const good = { endpoint: "https://web.push.apple.com/QAbc", keys: { p256dh, auth } };
  assert.deepEqual(validateSubscription(good), { endpoint: good.endpoint, p256dh, auth });
  assert.deepEqual(validateSubscription({ ...good, expirationTime: null }), { endpoint: good.endpoint, p256dh, auth });
  const refused = (value, why) => assert.throws(() => validateSubscription(value), { name: "ValidationError" }, why);
  const compressed = Buffer.concat([Buffer.from([2]), point.subarray(1)]).toString("base64url");
  refused({ ...good, keys: { p256dh: compressed, auth } }, "not uncompressed");
  const offCurve = Buffer.concat([Buffer.from([4]), Buffer.alloc(64, 1)]).toString("base64url");
  refused({ ...good, keys: { p256dh: offCurve, auth } }, "65 bytes that are not a point on the curve");
  refused({ ...good, keys: { p256dh, auth: auth.slice(1) } }, "a short auth secret");
  refused({ ...good, keys: { p256dh: p256dh + "=", auth } }, "padding is not base64url");
  refused({ ...good, keys: { p256dh: p256dh.replace(/-/g, "+").replace(/_/g, "/"), auth: "+".repeat(22) } }, "base64, not base64url");
  // 22 characters hold 132 bits, so 16 bytes have several spellings; only
  // the one an encoder writes is taken.
  const loose = auth.slice(0, 21) + "h";
  assert.notEqual(loose, auth);
  assert.deepEqual(Buffer.from(loose, "base64url"), Buffer.from(auth, "base64url"));
  refused({ ...good, keys: { p256dh, auth: loose } }, "a second spelling of the same bytes");
  refused({ ...good, extra: true }, "an unknown field");
  refused({ ...good, keys: { p256dh, auth, extra: "x" } }, "an unknown key");
  refused({ ...good, keys: [p256dh, auth] }, "keys as a list");
  refused({ ...good, expirationTime: "never" }, "an expirationTime that is not a number");
  refused([good], "a list");
});

test("a caller's network: the IPv4 address, the IPv6 /64, or one shared bucket", () => {
  assert.equal(clientNetwork("203.0.113.7"), "203.0.113.7");
  assert.equal(clientNetwork("::ffff:203.0.113.7"), "203.0.113.7");
  assert.equal(clientNetwork("2001:db8:1:2::1"), "2001:db8:1:2");
  assert.equal(clientNetwork("2001:0db8:0001:0002:aaaa:bbbb:cccc:dddd"), "2001:db8:1:2");
  assert.equal(clientNetwork("2001:db8::1"), "2001:db8:0:0");
  assert.equal(clientNetwork("::1"), "0:0:0:0");
  assert.notEqual(clientNetwork("2001:db8:1:3::1"), clientNetwork("2001:db8:1:2::1"));
  for (const odd of [undefined, null, "", "not an address", 42]) {
    assert.equal(clientNetwork(odd), "unknown", String(odd));
  }
});

test("the per-client code is keyed, changes with the day, and never holds the address", () => {
  const secret = "s".repeat(48);
  const code = clientCode(secret, "2026-11-08", "203.0.113.7");
  assert.match(code, /^[0-9a-f]{32}$/);
  assert.equal(code, clientCode(secret, "2026-11-08", "203.0.113.7"), "stable within a day");
  assert.notEqual(code, clientCode(secret, "2026-11-09", "203.0.113.7"), "a new code each day");
  assert.notEqual(code, clientCode(secret, "2026-11-08", "203.0.113.8"), "per network");
  assert.notEqual(code, clientCode("t".repeat(48), "2026-11-08", "203.0.113.7"), "useless without the key");
  assert.equal(
    clientCode(secret, "2026-11-08", "2001:db8:1:2::1"),
    clientCode(secret, "2026-11-08", "2001:db8:1:2:ffff::9"),
    "one /64 is one caller"
  );
});

test("an event's link must be a page of the site", () => {
  const origins = ["https://trouttruck.com"];
  const good = { water_id: "cdfw-1", title: "t", body: "b", url: "https://trouttruck.com/water/x/?utm_medium=push" };
  assert.deepEqual(validateEvent(good, origins), good);
  assert.throws(() => validateEvent({ ...good, url: "https://trouttruck.com.evil.invalid/" }, origins));
  assert.throws(() => validateEvent({ ...good, url: "http://trouttruck.com/water/x/" }, origins));
  assert.throws(() => validateEvent({ ...good, title: "" }, origins));
  assert.throws(() => validateEvent({ ...good, body: "b".repeat(601) }, origins));
});
