// The DynamoDB store behind handler.mjs (DECISIONS 0069). One table, hash key
// pk: "SUB#<sha256 of the endpoint>" rows for subscriptions, one "COUNTERS"
// row for the totals, and a sparse index by_water on water_id for the send
// fan-out. Thin on purpose: the logic that is tested lives in handler.mjs.
import {
  DeleteCommand,
  GetCommand,
  PutCommand,
  QueryCommand,
  ScanCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";

const COUNTERS_PK = "COUNTERS";
const SUB_PREFIX = "SUB#";

export function createStore(doc, tableName) {
  async function getSubscription(hash) {
    const res = await doc.send(new GetCommand({ TableName: tableName, Key: { pk: SUB_PREFIX + hash } }));
    return res.Item || null;
  }

  async function putSubscription(item) {
    await doc.send(new PutCommand({ TableName: tableName, Item: item }));
  }

  async function deleteSubscription(hash) {
    const res = await doc.send(
      new DeleteCommand({ TableName: tableName, Key: { pk: SUB_PREFIX + hash }, ReturnValues: "ALL_OLD" })
    );
    return Boolean(res.Attributes);
  }

  async function listByWater(waterId) {
    const items = [];
    let start;
    do {
      const res = await doc.send(
        new QueryCommand({
          TableName: tableName,
          IndexName: "by_water",
          KeyConditionExpression: "#w = :w",
          ExpressionAttributeNames: { "#w": "water_id" },
          ExpressionAttributeValues: { ":w": waterId },
          ExclusiveStartKey: start,
        })
      );
      items.push(...(res.Items || []));
      start = res.LastEvaluatedKey;
    } while (start);
    return items;
  }

  async function touch(hash, fields) {
    const names = {};
    const values = {};
    const sets = [];
    for (const [k, v] of Object.entries(fields)) {
      names[`#${k}`] = k;
      values[`:${k}`] = v;
      sets.push(`#${k} = :${k}`);
    }
    await doc.send(
      new UpdateCommand({
        TableName: tableName,
        Key: { pk: SUB_PREFIX + hash },
        UpdateExpression: `SET ${sets.join(", ")}`,
        ExpressionAttributeNames: names,
        ExpressionAttributeValues: values,
        ConditionExpression: "attribute_exists(pk)",
      })
    ).catch((err) => {
      // The row went away between the read and the touch: nothing to record.
      if (err?.name !== "ConditionalCheckFailedException") throw err;
    });
  }

  async function bump(counts) {
    const names = {};
    const values = {};
    const adds = [];
    for (const [k, v] of Object.entries(counts)) {
      if (!v) continue;
      names[`#${k}`] = k;
      values[`:${k}`] = v;
      adds.push(`#${k} :${k}`);
    }
    if (adds.length === 0) return;
    await doc.send(
      new UpdateCommand({
        TableName: tableName,
        Key: { pk: COUNTERS_PK },
        UpdateExpression: `ADD ${adds.join(", ")}`,
        ExpressionAttributeNames: names,
        ExpressionAttributeValues: values,
      })
    );
  }

  async function counters() {
    const res = await doc.send(new GetCommand({ TableName: tableName, Key: { pk: COUNTERS_PK } }));
    const item = { ...(res.Item || {}) };
    delete item.pk;
    return item;
  }

  // Every subscription, or those whose endpoint starts with the prefix.
  async function countSubscriptions(endpointPrefix) {
    let total = 0;
    let start;
    do {
      const res = await doc.send(
        new ScanCommand({
          TableName: tableName,
          Select: "COUNT",
          FilterExpression: endpointPrefix
            ? "begins_with(#pk, :p) AND begins_with(#e, :e)"
            : "begins_with(#pk, :p)",
          ExpressionAttributeNames: endpointPrefix ? { "#pk": "pk", "#e": "endpoint" } : { "#pk": "pk" },
          ExpressionAttributeValues: endpointPrefix ? { ":p": SUB_PREFIX, ":e": endpointPrefix } : { ":p": SUB_PREFIX },
          ExclusiveStartKey: start,
        })
      );
      total += res.Count || 0;
      start = res.LastEvaluatedKey;
    } while (start);
    return total;
  }

  return { getSubscription, putSubscription, deleteSubscription, listByWater, touch, bump, counters, countSubscriptions };
}
