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
  fetcher,
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
    fetch: async (...args) => {
      calls.push("fetch");
      if (fetcher) return fetcher(...args);
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
  return {
    chrome,
    calls,
    send,
    poll: () => vm.runInContext("poll()", context),
  };
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

test("queued retries pause while OFF, inactive or on a different conversation", async () => {
  for (const [on, tab] of [
    [false, { id: 1, url: "https://chatgpt.com/c/test" }],
    [true, { id: 2, url: "https://chatgpt.com/c/test" }],
    [true, { id: 1, url: "https://chatgpt.com/c/other" }],
    [true, { id: 1, url: "https://example.org/" }],
  ]) {
    const value = {
      id: "message",
      tab: 1,
      url: "https://chatgpt.com/c/test",
      text: "A fact.",
      retry: true,
      attempts: 1,
      next: 0,
    };
    const f = await setup({
      tab,
      local: { backendUrl: "https://test.onrender.com" },
      session: { on, "response:1:message": value },
    });
    await f.poll();
    assert.equal(f.calls.length, 0);
    assert.equal(
      f.chrome.storage.session.data["response:1:message"].attempts,
      1,
    );
  }
});
test("Re-verify preserves a result when its chat is inactive or verification is OFF", async () => {
  for (const on of [false, true]) {
    const value = {
      id: "message",
      tab: 1,
      url: "https://chatgpt.com/c/old",
      text: "A fact.",
      result: { claims: [] },
    };
    const f = await setup({
      session: {
        on,
        selected: "response:1:message",
        "response:1:message": value,
      },
    });
    const answer = await f.send(
      { type: "reverify" },
      { url: "chrome-extension://test/panel.html" },
    );
    assert.match(answer.error, /corresponding ChatGPT chat/);
    assert.ok(f.chrome.storage.session.data["response:1:message"].result);
    assert.equal(f.calls.length, 0);
  }
});
test("navigation during session creation prevents transmitting response text", async () => {
  const tab = { id: 1, url: "https://chatgpt.com/c/test" };
  const requests = [];
  const f = await setup({
    tab,
    local: { backendUrl: "https://test.onrender.com" },
    session: { on: true },
    fetcher: async (url, options) => {
      requests.push({ url, body: options.body });
      tab.url = "https://chatgpt.com/c/other";
      return {
        ok: true,
        json: async () => ({ token: "test-session", expires_in: 900 }),
      };
    },
  });
  await f.send({
    type: "verify",
    id: "message",
    revision: "a".repeat(64),
    text: "A private response.",
    citations: [],
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(requests.length, 1);
  assert.ok(requests[0].url.endsWith("/v1/session"));
  assert.equal(requests[0].body, undefined);
  const saved = f.chrome.storage.session.data["response:1:message"];
  assert.equal(saved.retry, true);
  assert.equal(saved.attempts, 0);
  assert.match(saved.stage, /Paused/);
});
test("paused retry resumes only after its chat is active and enabled", async () => {
  const requests = [];
  const value = {
    id: "message",
    tab: 1,
    url: "https://chatgpt.com/c/test",
    text: "A fact.",
    citations: [],
    runId: "run",
    retry: true,
    attempts: 1,
    next: 0,
  };
  const f = await setup({
    local: { backendUrl: "https://test.onrender.com" },
    session: { on: false, "response:1:message": value },
    fetcher: async (url, options) => {
      requests.push({ url, options });
      return {
        ok: true,
        json: async () =>
          url.endsWith("/v1/session")
            ? { token: "test-session", expires_in: 900 }
            : { job: "new-job" },
      };
    },
  });
  await f.poll();
  assert.equal(requests.length, 0);
  f.chrome.storage.session.data.on = true;
  await f.poll();
  assert.equal(requests.length, 2);
  assert.ok(requests[1].url.endsWith("/v1/verify"));
  assert.equal(JSON.parse(requests[1].options.body).text, "A fact.");
  assert.equal(
    requests[1].options.headers["X-VerifAI-Origin"],
    "chrome-extension://test",
  );
  assert.equal(
    f.chrome.storage.session.data["response:1:message"].job,
    "new-job",
  );
});
