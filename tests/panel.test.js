import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { JSDOM } from "jsdom";

async function setup({ benchmarkTiming = false, clock = Date } = {}) {
  const dom = new JSDOM(
    '<p id="stage"></p><button id="reverify"></button><main id="results"></main>',
    { pretendToBeVisual: true },
  );
  const opened = [],
    messages = [],
    listeners = [],
    frames = [];
  const data = {
    selected: "first",
    first: {
      text: "A fact.",
      stage: "Complete",
      result: {
        claims: [
          {
            text: "A fact.",
            label: "SUPPORTED",
            tracks: {
              citation: [
                {
                  url: "https://source.example/fact?q=1#section",
                  final_url: "https://source.example/article",
                  accessible: true,
                  checked_at: 1,
                  label: "SUPPORTED",
                  reason: "Exact evidence.",
                  snippets: [{ text: "A fact." }],
                },
              ],
              independent: [],
            },
            errors: [],
          },
        ],
        unsupported: [],
        citation_access: [],
        notice: "Access measured at retrieval time.",
      },
    },
  };
  const chrome = {
    storage: {
      session: {
        async get(keys) {
          return Object.fromEntries(
            (Array.isArray(keys) ? keys : [keys]).map((k) => [k, data[k]]),
          );
        },
      },
      onChanged: {
        addListener(fn) {
          listeners.push(fn);
        },
      },
    },
    tabs: {
      async create(value) {
        opened.push(structuredClone(value));
      },
    },
    runtime: {
      async sendMessage(value) {
        messages.push(structuredClone(value));
        return { ok: true };
      },
    },
  };
  vm.runInNewContext(
    fs
      .readFileSync(new URL("../extension/panel.js", import.meta.url), "utf8")
      .replace(/^import [\s\S]*?;\r?\n/gm, ""),
    {
      document: dom.window.document,
      URL,
      chrome,
      Date: clock,
      performance: { timeOrigin: 0, now: () => clock.now() },
      BENCHMARK_TIMING: benchmarkTiming,
      requestAnimationFrame: (callback) => frames.push(callback),
    },
  );
  await new Promise((resolve) => setImmediate(resolve));
  return { dom, opened, messages, data, listeners, frames };
}
test("source and redirect links create distinct Chrome tabs with exact intended URLs", async () => {
  const f = await setup();
  const links = [...f.dom.window.document.querySelectorAll("a")];
  for (const link of links) {
    assert.equal(link.rel, "noopener noreferrer");
    assert.equal(link.target, "_blank");
    link.dispatchEvent(
      new f.dom.window.MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        button: 0,
      }),
    );
  }
  assert.deepEqual(f.opened, [
    { url: "https://source.example/fact?q=1#section", active: true },
    { url: "https://source.example/article", active: true },
  ]);
  assert.equal(f.messages.length, 0);
});
test("panel retains selection when unrelated results change and reverify is explicit", async () => {
  const f = await setup();
  f.data.second = {
    stage: "Complete",
    result: { claims: [], unsupported: [] },
  };
  await f.listeners[0]();
  assert.match(f.dom.window.document.querySelector("h2").textContent, /A fact/);
  assert.equal(f.messages.length, 0);
  f.dom.window.document.querySelector("#reverify").click();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(f.messages, [{ type: "reverify" }]);
  f.data.selected = "second";
  await f.listeners[0]();
  assert.match(
    f.dom.window.document.querySelector("#results").textContent,
    /No verifiable claims/,
  );
  assert.equal(f.opened.length, 0);
});

test("developer clock waits for complete visible rendering and preserves its first measurement", async () => {
  let now = 2000;
  class Clock extends Date {
    static now() {
      return now;
    }
  }
  const f = await setup({ benchmarkTiming: true, clock: Clock });
  Object.assign(f.data.first, {
    benchmarkStartedAt: 1000,
    benchmarkRun: "run",
  });
  await f.listeners[0]();
  assert.ok(f.dom.window.document.querySelector("article"));
  assert.equal(f.dom.window.document.querySelector("#benchmark-timing"), null);
  f.frames.shift()();
  assert.equal(f.dom.window.document.querySelector("#benchmark-timing"), null);
  now = 2700;
  f.frames.shift()();
  assert.match(
    f.dom.window.document.querySelector("#benchmark-timing").textContent,
    /final result rendered after 1700\.000 ms/,
  );
  f.data.storageNotice = "Fixture notice.";
  now = 5000;
  await f.listeners[0]();
  f.frames.shift()();
  f.frames.shift()();
  assert.match(
    f.dom.window.document.querySelector("#benchmark-timing").textContent,
    /1700\.000 ms/,
  );
  Object.assign(f.data.first, {
    benchmarkStartedAt: 4900,
    benchmarkRun: "restore",
    benchmarkRestored: true,
  });
  await f.listeners[0]();
  f.frames.shift()();
  f.frames.shift()();
  assert.match(
    f.dom.window.document.querySelector("#benchmark-timing").textContent,
    /cached result restored after 100\.000 ms/,
  );
});
test("pending replacement invalidates a scheduled benchmark completion", async () => {
  const f = await setup({ benchmarkTiming: true });
  Object.assign(f.data.first, {
    benchmarkStartedAt: Date.now() - 100,
    benchmarkRun: "old",
  });
  await f.listeners[0]();
  f.data.first = { stage: "Analyzing claims", text: "A new claim." };
  await f.listeners[0]();
  f.frames.shift()();
  f.frames.shift()();
  assert.equal(f.dom.window.document.querySelector("#benchmark-timing"), null);
  assert.equal(f.dom.window.document.querySelector("article"), null);
});

test("benchmark cannot call provider-incomplete evidence a complete final render", async () => {
  const f = await setup({ benchmarkTiming: true });
  Object.assign(f.data.first, {
    benchmarkStartedAt: Date.now() - 100,
    benchmarkRun: "provider-error",
  });
  f.data.first.result.claims[0].errors.push(
    "Independent evidence review could not be completed.",
  );
  await f.listeners[0]();
  f.frames.shift()();
  f.frames.shift()();
  assert.match(
    f.dom.window.document.querySelector("#benchmark-timing").textContent,
    /incomplete result rendered/,
  );
});

test("submission counter is visible only in the developer build", async () => {
  const normal = await setup();
  normal.data.first.benchmarkSubmissionAttempts = 3;
  await normal.listeners[0]();
  assert.equal(
    normal.dom.window.document.querySelector("#benchmark-submissions"),
    null,
  );
  const developer = await setup({ benchmarkTiming: true });
  developer.data.first.benchmarkSubmissionAttempts = 1;
  await developer.listeners[0]();
  assert.match(
    developer.dom.window.document.querySelector("#benchmark-submissions")
      .textContent,
    /browser submission attempts 1/,
  );
});
