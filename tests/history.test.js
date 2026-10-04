import test from "node:test";
import assert from "node:assert/strict";
import { prune, savedHistory, validResult } from "../extension/core.js";
const now = 3000000000;
const record = (id, savedAt = now) => ({
  id,
  revision: "a".repeat(64),
  savedAt,
  result: { claims: [], unsupported: [] },
  text: "discarded input",
  job: "discarded job",
});
test("all timed retentions remove records exactly at expiration; manual retains old records", () => {
  for (const [retention, duration] of [
    ["24h", 86400000],
    ["7d", 604800000],
    ["30d", 2592000000],
  ]) {
    const history = {
      expired: record("expired", now - duration),
      valid: record("valid", now - duration + 1),
    };
    assert.deepEqual(Object.keys(savedHistory(history, retention, now)), [
      "valid",
    ]);
    assert.equal(Object.keys(savedHistory(history, "manual", now)).length, 2);
  }
});
test("malformed, future, unknown-version and invalid-result records fail closed", () => {
  for (const input of [null, undefined, [], "invalid"])
    assert.deepEqual(prune(input, "manual", now), {});
  const history = {
    nil: null,
    future: record("future", now + 1),
    wrongId: record("different"),
    version: { ...record("version"), version: 2 },
    invalid: {
      ...record("invalid"),
      result: { claims: [{}], unsupported: [] },
    },
    valid: record("valid"),
  };
  assert.deepEqual(Object.keys(savedHistory(history, "manual", now)), [
    "valid",
  ]);
  assert.deepEqual(savedHistory(history, "toString", now), {});
  assert.equal(validResult({ claims: [{}], unsupported: [] }), false);
});
test("legacy envelopes migrate without retaining submission or backend job fields", () => {
  const value = savedHistory({ valid: record("valid") }, "manual", now).valid;
  assert.equal(value.version, 1);
  assert.equal(value.stage, "Complete");
  assert.equal("text" in value, false);
  assert.equal("job" in value, false);
  assert.deepEqual(savedHistory({ valid: value }, "manual", now).valid, value);
});
test("history bounds record count and byte capacity, retaining newest records", () => {
  const history = Object.fromEntries(
    Array.from({ length: 110 }, (_, i) => [
      String(i),
      record(String(i), now - i),
    ]),
  );
  const saved = savedHistory(history, "manual", now);
  assert.equal(Object.keys(saved).length, 100);
  assert.equal("109" in saved, false);
  history.big = {
    ...record("big"),
    result: { claims: [], unsupported: ["x".repeat(1000001)] },
  };
  const bounded = savedHistory(history, "manual", now);
  assert.equal("big" in bounded, false);
  assert.ok(new TextEncoder().encode(JSON.stringify(bounded)).length < 1000000);
});

test("corrupt history cannot restore script, credential or malformed source links", () => {
  for (const url of [
    "javascript:alert(1)",
    "http://source.example/",
    "https://user:password@source.example/",
    "invalid",
  ]) {
    const result = {
      claims: [
        {
          text: "A fact.",
          label: "SUPPORTED",
          errors: [],
          tracks: {
            citation: [
              {
                url,
                label: "SUPPORTED",
                reason: "evidence",
                accessible: true,
                snippets: [{ text: "A fact." }],
              },
            ],
            independent: [],
          },
        },
      ],
      unsupported: [],
    };
    assert.equal(validResult(result), false);
    assert.deepEqual(
      savedHistory(
        { invalid: { ...record("invalid"), result } },
        "manual",
        now,
      ),
      {},
    );
  }
});
