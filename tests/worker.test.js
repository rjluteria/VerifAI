import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { webcrypto } from "node:crypto";
import * as core from "../extension/core.js";
import { SERVICE_ORIGIN } from "../extension/config.js";
const source = fs
  .readFileSync(new URL("../extension/worker.js", import.meta.url), "utf8")
  .replace(/^import [\s\S]*?;\r?\n/gm, "");
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
  eligibility = true,
  benchmarkTiming = false,
} = {}) {
  const calls = [];
  const deliveries = [];
  const eligibilityChecks = [];
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
      async sendMessage(...args) {
        if (args[1]?.type === "eligible") {
          eligibilityChecks.push(args);
          return {
            eligible:
              typeof eligibility === "function" ? eligibility() : eligibility,
          };
        }
        deliveries.push(args);
      },
      onRemoved: event(),
    },
    alarms: { async create() {}, onAlarm: event() },
    permissions: {
      async contains() {
        return true;
      },
    },
    sidePanel: {
      async open() {
        calls.push("open");
      },
    },
  };
  const context = vm.createContext({
    ...core,
    SERVICE_ORIGIN,
    BENCHMARK_TIMING: benchmarkTiming,
    performance,
    chrome,
    crypto: webcrypto,
    URL,
    AbortSignal,
    TextEncoder,
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
    deliveries,
    eligibilityChecks,
    send,
    poll: () => vm.runInContext("poll()", context),
    store: (...args) => vm.runInContext("store", context)(...args),
  };
}
test("first session is OFF; browser startup restores prior enablement", async () => {
  const first = await setup();
  assert.equal((await first.send({ type: "state" })).on, false);
  const later = await setup({ local: { everEnabled: true } });
  assert.equal((await later.send({ type: "state" })).on, false);
  await later.chrome.runtime.onStartup.listeners[0]();
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
    url: "https://chatgpt.com/c/test",
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
    url: "https://chatgpt.com/c/test",
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
      revision: "a".repeat(64),
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
      revision: "a".repeat(64),
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
    url: "https://chatgpt.com/c/test",
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
    revision: "a".repeat(64),
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
test("SPA conversations bind to the captured response URL despite an older sender URL", async () => {
  const requests = [];
  const f = await setup({
    local: { backendUrl: "https://test.onrender.com" },
    session: { on: true },
    fetcher: async (url, options) => {
      requests.push({ url, body: options.body });
      return {
        ok: true,
        json: async () =>
          url.endsWith("/v1/session")
            ? { token: "test-session", expires_in: 900 }
            : url.endsWith("/v1/verify")
              ? { job: "job" }
              : { stage: "Verifying evidence" },
      };
    },
  });
  const request = {
    type: "verify",
    url: "https://chatgpt.com/c/test",
    id: "/c/test:message",
    revision: "a".repeat(64),
    text: "A synthetic fact.",
    citations: [],
  };
  const sender = {
    tab: { id: 1 },
    url: "https://chatgpt.com/?temporary-chat=true",
  };
  assert.equal((await f.send(request, sender)).accepted, true);
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(requests.some((r) => r.url.endsWith("/v1/verify")));
  assert.equal(
    f.chrome.storage.session.data["response:1:/c/test:message"].url,
    request.url,
  );
  const prior = requests.length;
  assert.equal(
    (await f.send({ ...request, url: "https://chatgpt.com/c/old" }, sender))
      .error,
    "ineligible",
  );
  assert.equal(
    (await f.send({ ...request, url: undefined }, sender)).error,
    "ineligible",
  );
  assert.equal(requests.length, prior);
});
test("exhausted capacity retries stop and accurately explain manual recovery", async () => {
  const key = "response:1:message";
  const f = await setup({
    local: { backendUrl: "https://test.onrender.com" },
    session: {
      on: true,
      [key]: {
        id: "message",
        revision: "a".repeat(64),
        tab: 1,
        url: "https://chatgpt.com/c/test",
        runId: "run",
        text: "A synthetic fact.",
        citations: [],
        retry: true,
        attempts: 2,
        next: 0,
      },
    },
    fetcher: async (url) =>
      url.endsWith("/v1/session")
        ? {
            ok: true,
            json: async () => ({ token: "test-session", expires_in: 900 }),
          }
        : { ok: false, status: 429 },
  });
  await f.poll();
  const saved = f.chrome.storage.session.data[key];
  assert.equal(saved.attempts, 3);
  assert.equal(saved.retry, false);
  assert.match(saved.stage, /Automatic retries exhausted/);
  assert.doesNotMatch(saved.stage, /will retry/);
  const count = f.calls.length;
  await f.poll();
  assert.equal(f.calls.length, count);
});
test("OFF survives cleared session storage on extension reload; browser startup restores prior enablement", async () => {
  const f = await setup({ local: { everEnabled: true, enabled: false } });
  assert.equal((await f.send({ type: "state" })).on, false);
  await f.chrome.runtime.onStartup.listeners[0]();
  assert.equal((await f.send({ type: "state" })).active, true);
  const sender = { url: "chrome-extension://test/popup.html" };
  await f.send({ type: "toggle", on: false }, sender);
  assert.equal(f.chrome.storage.local.data.enabled, false);
  const reloaded = await setup({ local: f.chrome.storage.local.data });
  assert.equal((await reloaded.send({ type: "state" })).on, false);
});

test("history cannot enable without retention and content senders cannot change it", async () => {
  const f = await setup();
  const request = {
    type: "saveSettings",
    historyEnabled: true,
    retention: "",
  };
  assert.equal((await f.send(request)).error, "sender");
  assert.ok(
    (await f.send(request, { url: "chrome-extension://test/settings.html" }))
      .error,
  );
  assert.equal(f.chrome.storage.local.data.historyEnabled, undefined);
});
test("failed history writes retain current result and accurately describe failed cleanup", async () => {
  const f = await setup({
    local: { historyEnabled: true, retention: "manual" },
  });
  f.chrome.storage.local.set = async () => {
    throw Error("write failed");
  };
  await f.store("response:1:message", {
    id: "message",
    revision: "a".repeat(64),
    result: { claims: [], unsupported: [] },
  });
  assert.equal(
    f.chrome.storage.session.data["response:1:message"].result.claims.length,
    0,
  );
  assert.match(
    f.chrome.storage.session.data.storageNotice,
    /could not be saved or cleared/,
  );
});
test("settings changes and saves are serialized so disabled history stays empty", async () => {
  const f = await setup({
    local: { historyEnabled: true, retention: "manual" },
  });
  const save = f.store("response:1:message", {
    id: "message",
    revision: "a".repeat(64),
    result: { claims: [], unsupported: [] },
  });
  const disable = f.send(
    {
      type: "saveSettings",
      historyEnabled: false,
      retention: "manual",
    },
    { url: "chrome-extension://test/settings.html" },
  );
  await Promise.all([save, disable]);
  assert.equal(f.chrome.storage.local.data.historyEnabled, false);
  assert.deepEqual(f.chrome.storage.local.data.history, {});
});

test("extension settings in a Chrome tab can save, but forged page origins cannot", async () => {
  const f = await setup();
  const request = {
    type: "saveSettings",
    historyEnabled: false,
    retention: "",
  };
  assert.equal(
    (
      await f.send(request, {
        tab: { id: 3 },
        url: "chrome-extension://test/settings.html",
      })
    ).ok,
    true,
  );
  assert.equal(
    (
      await f.send(request, {
        tab: { id: 3 },
        url: "chrome-extension://test/settings.html.evil",
      })
    ).error,
    "sender",
  );
  assert.equal(
    (await f.send(request, { tab: { id: 3 }, url: "https://chatgpt.com/" }))
      .error,
    "sender",
  );
});

test("foreground polling is throttled and delivers honest stage updates", async () => {
  const value = {
    id: "message",
    revision: "a".repeat(64),
    tab: 1,
    url: "https://chatgpt.com/c/test",
    runId: "run",
    job: "job",
    stage: "Analyzing claims",
  };
  const f = await setup({
    local: { backendUrl: "https://test.onrender.com" },
    session: {
      on: true,
      auth: {
        origin: SERVICE_ORIGIN,
        token: "test-token",
        expires: Date.now() + 60000,
      },
      "response:1:message": value,
    },
    fetcher: async () => ({
      ok: true,
      json: async () => ({ stage: "Searching independent sources" }),
    }),
  });
  await f.send({ type: "state", poll: true });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(f.calls.filter((v) => v === "fetch").length, 1);
  assert.equal(f.deliveries[0][1].summary, "Searching independent sources");
  await f.send({ type: "state", poll: true });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(f.calls.filter((v) => v === "fetch").length, 1);
});
test("completion waits require a declared session capability; old services keep immediate polling", async () => {
  for (const completionWait of [undefined, false, true]) {
    const requests = [];
    const f = await setup({
      session: {
        on: true,
        auth: {
          origin: SERVICE_ORIGIN,
          token: "token",
          expires: Date.now() + 60000,
          completionWait,
        },
        "response:1:message": {
          id: "message",
          revision: "a".repeat(64),
          tab: 1,
          url: "https://chatgpt.com/c/test",
          runId: "run",
          job: "job",
          stage: "Analyzing claims",
        },
      },
      fetcher: async (url) => {
        requests.push(url);
        return {
          ok: true,
          json: async () => ({ stage: "Searching independent sources" }),
        };
      },
    });
    await f.poll();
    assert.deepEqual(requests, [
      SERVICE_ORIGIN +
        "/v1/jobs/job" +
        (completionWait === true ? "?wait=5" : ""),
    ]);
    assert.equal(
      f.chrome.storage.session.data["response:1:message"].job,
      "job",
    );
  }
});
test("late result from superseded job cannot overwrite its replacement", async () => {
  let finish;
  const pending = new Promise((resolve) => {
    finish = resolve;
  });
  const old = {
    id: "message",
    revision: "a".repeat(64),
    tab: 1,
    url: "https://chatgpt.com/c/test",
    runId: "old",
    job: "old-job",
    stage: "Verifying evidence",
  };
  const f = await setup({
    local: { backendUrl: "https://test.onrender.com" },
    session: {
      on: true,
      auth: {
        origin: SERVICE_ORIGIN,
        token: "test-token",
        expires: Date.now() + 60000,
      },
      "response:1:message": old,
    },
    fetcher: async () => ({ ok: true, json: async () => pending }),
  });
  const polled = f.poll();
  await new Promise((resolve) => setImmediate(resolve));
  const replacement = {
    ...old,
    runId: "new",
    job: "new-job",
    revision: "b".repeat(64),
  };
  await f.chrome.storage.session.set({ "response:1:message": replacement });
  finish({ stage: "Complete", result: { claims: [], unsupported: [] } });
  await polled;
  assert.equal(
    f.chrome.storage.session.data["response:1:message"].job,
    "new-job",
  );
  assert.equal(
    f.chrome.storage.session.data["response:1:message"].result,
    undefined,
  );
  assert.equal(f.deliveries.length, 0);
});

test("branch or response replacement at the same URL prevents queued content transmission", async () => {
  const f = await setup({
    eligibility: false,
    session: { on: true },
    local: { backendUrl: "https://test.onrender.com" },
  });
  await f.send({
    type: "verify",
    url: "https://chatgpt.com/c/test",
    id: "/c/test:message",
    revision: "a".repeat(64),
    text: "A synthetic fact.",
    citations: [],
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(f.eligibilityChecks.length > 0);
  assert.equal(f.calls.length, 0);
});
test("same-URL eligibility is rechecked after session creation before posting response text", async () => {
  let present = true;
  const posts = [];
  const f = await setup({
    eligibility: () => present,
    session: { on: true },
    local: { backendUrl: "https://test.onrender.com" },
    fetcher: async (url) => {
      posts.push(url);
      present = false;
      return {
        ok: true,
        json: async () => ({ token: "synthetic-session", expires_in: 900 }),
      };
    },
  });
  await f.send({
    type: "verify",
    url: "https://chatgpt.com/c/test",
    id: "/c/test:message",
    revision: "a".repeat(64),
    text: "A synthetic fact.",
    citations: [],
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(posts, [SERVICE_ORIGIN + "/v1/session"]);
  assert.ok(f.eligibilityChecks.length >= 2);
});

test("legacy endpoint and auth cannot redirect configured verification", async () => {
  const urls = [];
  const f = await setup({
    local: { backendUrl: "https://other.onrender.com", historyEnabled: false },
    session: {
      on: true,
      auth: {
        origin: "https://other.onrender.com",
        token: "legacy",
        expires: Date.now() + 60000,
      },
    },
    fetcher: async (url, options) => {
      urls.push(url);
      assert.notEqual(options.headers.Authorization, "Bearer legacy");
      return {
        ok: true,
        json: async () =>
          url.endsWith("/v1/session")
            ? { token: "configured", expires_in: 3600 }
            : url.endsWith("/v1/verify")
              ? { job: "new" }
              : { stage: "Verifying evidence" },
      };
    },
  });
  assert.equal(f.chrome.storage.local.data.backendUrl, undefined);
  assert.equal(f.chrome.storage.session.data.auth, undefined);
  assert.equal(
    (
      await f.send({
        type: "verify",
        id: "configured",
        revision: "d".repeat(64),
        text: "A fact.",
        citations: [],
        url: "https://chatgpt.com/c/test",
      })
    ).accepted,
    true,
  );
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(urls.includes(SERVICE_ORIGIN + "/v1/session"));
  assert.ok(urls.includes(SERVICE_ORIGIN + "/v1/verify"));
  assert.ok(urls.every((url) => new URL(url).origin === SERVICE_ORIGIN));
  assert.equal(
    (
      await f.send(
        {
          type: "saveSettings",
          backendUrl: "https://other.onrender.com",
          historyEnabled: false,
          retention: "",
        },
        { url: "chrome-extension://test/settings.html" },
      )
    ).error,
    "Backend overrides are not supported.",
  );
});

test("developer timing distinguishes fresh verification, restoration and Re-verify", async () => {
  const value = {
    id: "message",
    revision: "a".repeat(64),
    tab: 1,
    url: "https://chatgpt.com/c/test",
    text: "A fact.",
    citations: [],
  };
  const f = await setup({
    benchmarkTiming: true,
    session: { on: true },
    fetcher: async (url) => ({
      ok: true,
      json: async () =>
        url.endsWith("/v1/session")
          ? { token: "token", expires_in: 900 }
          : { job: "job" },
    }),
  });
  await f.send({ type: "verify", ...value });
  await new Promise((resolve) => setImmediate(resolve));
  const key = "response:1:message";
  let stored = f.chrome.storage.session.data[key];
  assert.ok(Number.isFinite(stored.benchmarkStartedAt));
  assert.equal(stored.benchmarkRestored, false);
  const firstRun = stored.benchmarkRun;
  // A restoration retains the already verified revision; it does not verify again.
  stored.result = { claims: [], unsupported: [], notice: "Fixture." };
  const requests = f.calls.filter((v) => v === "fetch").length;
  await f.send({ type: "verify", ...value });
  assert.equal(f.calls.filter((v) => v === "fetch").length, requests);
  stored = f.chrome.storage.session.data[key];
  assert.equal(stored.benchmarkRestored, true);
  assert.notEqual(stored.benchmarkRun, firstRun);
  f.chrome.storage.session.data.selected = key;
  const restoreRun = stored.benchmarkRun;
  await f.send(
    { type: "reverify" },
    { url: "chrome-extension://test/panel.html" },
  );
  stored = f.chrome.storage.session.data[key];
  assert.equal(stored.benchmarkRestored, false);
  assert.notEqual(stored.benchmarkRun, restoreRun);
});

test("developer clock includes dispatch before worker wakeup and never enters API payload", async () => {
  const bodies = [];
  const f = await setup({
    benchmarkTiming: true,
    session: { on: true },
    fetcher: async (url, options) => {
      if (options.body) bodies.push(JSON.parse(options.body));
      return {
        ok: true,
        json: async () =>
          url.endsWith("/v1/session")
            ? { token: "token", expires_in: 900 }
            : { job: "job" },
      };
    },
  });
  const start = performance.timeOrigin + performance.now() - 1000;
  await f.send({
    type: "verify",
    id: "message",
    revision: "a".repeat(64),
    url: "https://chatgpt.com/c/test",
    text: "A fact.",
    citations: [],
    benchmarkStartedAt: start,
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(
    f.chrome.storage.session.data["response:1:message"].benchmarkStartedAt,
    start,
  );
  assert.deepEqual(bodies.at(-1), { text: "A fact.", citations: [] });
});

test("developer submission count survives a worker restart without posting the pending job again", async () => {
  let originalPosts = 0;
  const first = await setup({
    benchmarkTiming: true,
    session: { on: true },
    fetcher: async (url, options) => {
      if (url.endsWith("/v1/verify")) {
        originalPosts++;
        assert.deepEqual(JSON.parse(options.body), {
          text: "A synthetic fact.",
          citations: [],
        });
      }
      return {
        ok: true,
        json: async () =>
          url.endsWith("/v1/session")
            ? { token: "fixture", expires_in: 900 }
            : url.endsWith("/v1/verify")
              ? { job: "owned-job" }
              : { stage: "Verifying evidence" },
      };
    },
  });
  await first.send({
    type: "verify",
    id: "message",
    revision: "a".repeat(64),
    text: "A synthetic fact.",
    citations: [],
    url: "https://chatgpt.com/c/test",
  });
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  const key = "response:1:message";
  assert.equal(
    first.chrome.storage.session.data[key].benchmarkSubmissionAttempts,
    1,
  );
  let resumedPosts = 0;
  const second = await setup({
    benchmarkTiming: true,
    session: first.chrome.storage.session.data,
    fetcher: async (url, options) => {
      if (options.method === "POST") resumedPosts++;
      assert.ok(url.includes("/v1/jobs/owned-job"));
      return {
        ok: true,
        json: async () => ({
          stage: "Complete",
          result: {
            claims: [],
            unsupported: [],
            notice: "Protocol fixture only.",
          },
        }),
      };
    },
  });
  await second.poll();
  assert.equal(originalPosts, 1);
  assert.equal(resumedPosts, 0);
  assert.equal(second.chrome.storage.session.data[key].job, "owned-job");
  assert.equal(second.chrome.storage.session.data[key].stage, "Complete");
  assert.equal(
    second.chrome.storage.session.data[key].benchmarkSubmissionAttempts,
    1,
  );
});
