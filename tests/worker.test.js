import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { webcrypto } from "node:crypto";
import * as core from "../extension/core.js";
const source = fs
  .readFileSync(new URL("../extension/worker.js", import.meta.url), "utf8")
  .replace(/^import .*?;\r?\n/, "");
function area(initial = {}) {
  const data = structuredClone(initial);
  return {
    data,
    async get(keys) {
      if (keys === null) return structuredClone(data);
      const list = Array.isArray(keys) ? keys : [keys];
      return Object.fromEntries(
        list.filter((k) => k in data).map((k) => [k, structuredClone(data[k])]),
      );
    },
    async set(values) {
      Object.assign(data, structuredClone(values));
    },
    async remove(keys) {
      for (const key of Array.isArray(keys) ? keys : [keys]) delete data[key];
    },
    async setAccessLevel() {},
  };
}
function event() {
  const listeners = [];
  return {
    listeners,
    addListener(fn) {
      listeners.push(fn);
    },
  };
}
async function setup({
  local = {},
  session = {},
  tab = { id: 1, url: "https://chatgpt.com/c/test" },
} = {}) {
  const calls = [];
  const chrome = {
    storage: { local: area(local), session: area(session) },
    runtime: {
      onInstalled: event(),
      onStartup: event(),
      onMessage: event(),
      getURL: (path) => "chrome-extension://test/" + path,
    },
    tabs: {
      async query() {
        return [tab];
      },
      async sendMessage() {},
      onRemoved: event(),
    },
    alarms: { async create() {}, onAlarm: event() },
    sidePanel: {
      async open() {
        calls.push("open");
      },
    },
  };
  const context = vm.createContext({
    ...core,
    chrome,
    crypto: webcrypto,
    URL,
    AbortSignal,
    console,
    Date,
    Promise,
    fetch: async () => {
      calls.push("fetch");
      throw Error("test network disabled");
    },
  });
  vm.runInContext(source, context);
  await new Promise((resolve) => setImmediate(resolve));
  function send(message, sender = { tab, url: tab.url }) {
    return new Promise((resolve) =>
      chrome.runtime.onMessage.listeners[0](message, sender, resolve),
    );
  }
  return { chrome, calls, send };
}
test("first session is OFF; later session restores prior enablement", async () => {
  const first = await setup();
  assert.equal((await first.send({ type: "state" })).on, false);
  const later = await setup({ local: { everEnabled: true } });
  assert.equal((await later.send({ type: "state" })).active, true);
});
test("session OFF persists across worker initialization", async () => {
  const f = await setup({
    local: { everEnabled: true },
    session: { on: false },
  });
  assert.equal((await f.send({ type: "state" })).on, false);
});
test("noneligible and inactive senders cannot submit content", async () => {
  const f = await setup({ session: { on: true } });
  const request = {
    type: "verify",
    id: "test",
    revision: "a".repeat(64),
    text: "A fact.",
    citations: [],
  };
  assert.equal(
    (
      await f.send(request, {
        tab: { id: 2 },
        url: "https://chatgpt.com/c/other",
      })
    ).error,
    "ineligible",
  );
  assert.equal(
    (await f.send(request, { tab: { id: 1 }, url: "https://evil.example" }))
      .error,
    "ineligible",
  );
  assert.equal(f.calls.length, 0);
});
test("content script cannot change global settings or start selected reverify", async () => {
  const f = await setup();
  assert.equal((await f.send({ type: "toggle", on: true })).error, "sender");
  assert.equal((await f.send({ type: "reverify" })).error, "sender");
  assert.equal(f.chrome.storage.session.data.on, false);
});
test("extension popup toggles persist within session", async () => {
  const f = await setup();
  const sender = { url: "chrome-extension://test/popup.html" };
  await f.send({ type: "toggle", on: true }, sender);
  assert.equal(f.chrome.storage.local.data.everEnabled, true);
  assert.equal((await f.send({ type: "state" })).active, true);
  await f.send({ type: "toggle", on: false }, sender);
  assert.equal((await f.send({ type: "state" })).active, false);
});
test("View details selects an existing result without network activity", async () => {
  const f = await setup({ session: { on: true } });
  await f.send({ type: "details", id: "message" });
  assert.equal(f.chrome.storage.session.data.selected, "response:1:message");
  assert.deepEqual(f.calls, ["open"]);
});
test("valid history restores without verification", async () => {
  const saved = {
    id: "message",
    revision: "a".repeat(64),
    savedAt: Date.now(),
    result: { claims: [], unsupported: [] },
    stage: "Complete",
  };
  const f = await setup({
    session: { on: true },
    local: {
      historyEnabled: true,
      retention: "24h",
      history: { message: saved },
    },
  });
  const result = await f.send({
    type: "verify",
    id: "message",
    revision: saved.revision,
    text: "A fact.",
    citations: [],
  });
  assert.equal(result.accepted, true);
  assert.equal(f.calls.length, 0);
  assert.equal(
    f.chrome.storage.session.data["response:1:message"].text,
    "A fact.",
  );
});
