import assert from "node:assert/strict";
import { test } from "node:test";
import { endpointHash, isAllowedPushEndpoint, validateEvent, validateSubscription } from "./validate.mjs";

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
  ]) {
    assert.equal(isAllowedPushEndpoint(bad), false, String(bad));
  }
});

test("the row key is the endpoint's full SHA-256", () => {
  assert.match(endpointHash("https://web.push.apple.com/QAbc"), /^[0-9a-f]{64}$/);
  assert.notEqual(endpointHash("https://web.push.apple.com/a"), endpointHash("https://web.push.apple.com/b"));
});

test("a subscription needs a 65-byte uncompressed P-256 key and a 16-byte auth secret", () => {
  const p256dh = Buffer.concat([Buffer.from([4]), Buffer.alloc(64, 1)]).toString("base64url");
  const auth = Buffer.alloc(16, 2).toString("base64url");
  const good = { endpoint: "https://web.push.apple.com/QAbc", keys: { p256dh, auth } };
  assert.deepEqual(validateSubscription(good), { endpoint: good.endpoint, p256dh, auth });
  const compressed = Buffer.concat([Buffer.from([2]), Buffer.alloc(64, 1)]).toString("base64url");
  assert.throws(() => validateSubscription({ ...good, keys: { p256dh: compressed, auth } }));
  assert.throws(() => validateSubscription({ ...good, keys: { p256dh, auth: auth.slice(1) } }));
  assert.throws(() => validateSubscription({ ...good, keys: { p256dh: p256dh + "=", auth } }), "padding is not base64url");
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
