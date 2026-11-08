// Lambda entry point (DECISIONS 0069): wires DynamoDB, SSM and web-push into
// handler.mjs. The AWS SDK v3 clients ship with the nodejs22.x runtime;
// web-push is the one dependency npm installs (package.json).
//
// Secrets come from SSM Parameter Store under SSM_PREFIX, read once per
// container: vapid-public-key, vapid-private-key, vapid-subject and
// sender-token. Terraform never sees their values; the owner puts them there
// (../README.md).
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import { GetParametersCommand, SSMClient } from "@aws-sdk/client-ssm";
import webpush from "web-push";
import { createStore } from "./dynamo.mjs";
import { createHandler } from "./handler.mjs";

const TABLE_NAME = process.env.TABLE_NAME;
const SSM_PREFIX = (process.env.SSM_PREFIX || "").replace(/\/+$/, "");
const SITE_ORIGINS = (process.env.SITE_ORIGINS || "")
  .split(",")
  .map((s) => s.trim().replace(/\/+$/, ""))
  .filter(Boolean);

const PARAMETERS = {
  vapidPublicKey: "vapid-public-key",
  vapidPrivateKey: "vapid-private-key",
  vapidSubject: "vapid-subject",
  senderToken: "sender-token",
};

const doc = DynamoDBDocumentClient.from(new DynamoDBClient({}), {
  marshallOptions: { removeUndefinedValues: true },
});
const ssm = new SSMClient({});

let cached = null;
async function secrets() {
  if (cached) return cached;
  const names = Object.values(PARAMETERS).map((n) => `${SSM_PREFIX}/${n}`);
  const res = await ssm.send(new GetParametersCommand({ Names: names, WithDecryption: true }));
  const missing = res.InvalidParameters || [];
  if (missing.length > 0) throw new Error(`missing SSM parameters: ${missing.join(", ")}`);
  const byName = new Map((res.Parameters || []).map((p) => [p.Name, p.Value]));
  const out = {};
  for (const [key, name] of Object.entries(PARAMETERS)) {
    const value = byName.get(`${SSM_PREFIX}/${name}`);
    if (!value) throw new Error(`empty SSM parameter: ${SSM_PREFIX}/${name}`);
    out[key] = value;
  }
  cached = out;
  return cached;
}

const sender = {
  send: (subscription, payload, options) => webpush.sendNotification(subscription, payload, options),
};

export const handler = createHandler({
  store: createStore(doc, TABLE_NAME),
  secrets,
  sender,
  siteOrigins: SITE_ORIGINS,
});
