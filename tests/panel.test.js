import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { JSDOM } from "jsdom";

async function setup({
  benchmarkTiming = false,
  clock = Date,
  panelContext = { eligible: true, on: true },
} = {}) {
  const dom = new JSDOM(
    '<p id="stage"></p><section id="progress"></section><p id="elapsed"></p><button id="reverify"></button><main id="results"></main>',
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
        if (value.type !== "panel-context")
          messages.push(structuredClone(value));
        return value.type === "panel-context" ? panelContext : { ok: true };
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
      performance: { timeOrigin: 99999999, now: () => clock.now() + 50000 },
      BENCHMARK_TIMING: benchmarkTiming,
      requestAnimationFrame: (callback) => frames.push(callback),
    },
  );
  await new Promise((resolve) => setImmediate(resolve));
  return { dom, opened, messages, data, listeners, frames, panelContext };
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
    benchmarkClock: "wall-clock-v3",
    benchmarkClockOrigin: "dispatcher",
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
  const firstClock = JSON.parse(
    f.dom.window.document.querySelector("#benchmark-clock-record").value,
  );
  assert.equal(firstClock.started_epoch_ms, 1000);
  assert.equal(firstClock.visible_final_epoch_ms, 2700);
  assert.equal(firstClock.elapsed_ms, 1700);
  assert.equal(firstClock.cached, false);
  assert.equal(firstClock.clock_valid, true);
  f.data.storageNotice = "Fixture notice.";
  now = 5000;
  await f.listeners[0]();
  f.frames.shift()();
  f.frames.shift()();
  assert.match(
    f.dom.window.document.querySelector("#benchmark-timing").textContent,
    /1700\.000 ms/,
  );
  assert.deepEqual(
    JSON.parse(
      f.dom.window.document.querySelector("#benchmark-clock-record").value,
    ),
    firstClock,
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
    benchmarkClock: "wall-clock-v3",
    benchmarkClockOrigin: "dispatcher",
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
  assert.match(
    f.dom.window.document.querySelector("article .status").textContent,
    /^Analysis incomplete: SUPPORTED$/,
  );
  assert.equal(
    f.dom.window.document.querySelector("#stage").textContent,
    "Analysis incomplete; some checks could not finish.",
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

for (const delta of [0, -50]) {
  test(`nonpositive clock ${delta} is invalid instead of a zero latency pass`, async () => {
    class Clock extends Date {
      static now() {
        return 1000;
      }
    }
    const f = await setup({ benchmarkTiming: true, clock: Clock });
    Object.assign(f.data.first, {
      benchmarkStartedAt: 1000 - delta,
      benchmarkRun: "bad-clock",
      benchmarkClock: "wall-clock-v3",
      benchmarkClockOrigin: "dispatcher",
    });
    await f.listeners[0]();
    f.frames.shift()();
    f.frames.shift()();
    assert.match(
      f.dom.window.document.querySelector("#benchmark-timing").textContent,
      /invalid render clock.*No latency pass/,
    );
  });
}
test("handler fallback cannot establish a dispatcher-to-render latency pass", async () => {
  const f = await setup({ benchmarkTiming: true });
  Object.assign(f.data.first, {
    benchmarkStartedAt: Date.now() - 100,
    benchmarkRun: "fallback-clock",
    benchmarkClock: "wall-clock-v3",
    benchmarkClockOrigin: "handler fallback",
  });
  await f.listeners[0]();
  f.frames.shift()();
  f.frames.shift()();
  assert.match(
    f.dom.window.document.querySelector("#benchmark-timing").textContent,
    /invalid render clock.*handler fallback.*No latency pass/,
  );
});

test("owned job trace is collapsed and appears only in the developer build", async () => {
  for (const benchmarkTiming of [false, true]) {
    const f = await setup({ benchmarkTiming });
    f.data.first.job = "owned-synthetic-job";
    f.data.first.trace = {
      version: 1,
      events: [{ stage: "search", count: 1 }],
    };
    await f.listeners[0]();
    const node = f.dom.window.document.querySelector("#benchmark-causal-trace");
    if (benchmarkTiming) {
      assert.equal(node.closest("details").open, false);
      assert.deepEqual(JSON.parse(node.textContent), f.data.first.trace);
      assert.match(
        f.dom.window.document.querySelector("#benchmark-job").textContent,
        /owned-synthetic-job/,
      );
    } else {
      assert.equal(node, null);
      assert.equal(f.dom.window.document.querySelector("#benchmark-job"), null);
    }
    f.dom.window.close();
  }
});

test("private evidence inspection contains only the rendered factual result", async () => {
  for (const benchmarkTiming of [false, true]) {
    const f = await setup({ benchmarkTiming });
    f.data.first.auth = "private-credential-fixture";
    f.data.first.url = "https://chatgpt.com/c/private-conversation-fixture";
    await f.listeners[0]();
    const field = f.dom.window.document.querySelector("#benchmark-result");
    if (benchmarkTiming) {
      assert.equal(field.readOnly, true);
      assert.equal(field.closest("details").open, false);
      assert.deepEqual(JSON.parse(field.value), f.data.first.result);
      assert.doesNotMatch(
        field.value,
        /private-credential|private-conversation/,
      );
    } else assert.equal(field, null);
    f.dom.window.close();
  }
});

test("overrun stays pending with real elapsed time and no invented verdict", async () => {
  class FixedClock extends Date {
    static now() {
      return 40000;
    }
  }
  const f = await setup({ clock: FixedClock });
  f.data.first = {
    text: "Pending fact.",
    job: "job-one",
    triggeredAt: 1000,
    stage: "Searching independent sources",
    progress: {
      version: 1,
      job_id: "job-one",
      sequence: 2,
      claim_count: 3,
      stages: {
        claims: "complete",
        citations: "active",
        independent: "active",
        evaluation: "pending",
      },
    },
  };
  await f.listeners[0]();
  assert.match(
    f.dom.window.document.querySelector("#stage").textContent,
    /taking longer than expected/,
  );
  assert.match(
    f.dom.window.document.querySelector("#elapsed").textContent,
    /39.0 s/,
  );
  assert.match(
    f.dom.window.document.querySelector("#progress").textContent,
    /Checking 3 claims/,
  );
  assert.match(
    f.dom.window.document.querySelector("#progress").textContent,
    /ChatGPT citations: active/,
  );
  assert.equal(f.dom.window.document.querySelector("article"), null);
  assert.equal(f.dom.window.document.querySelector("#reverify").disabled, true);
});

test("another job's progress is hidden and completion waits for final paint", async () => {
  const f = await setup();
  f.data.first.job = "own";
  f.data.first.progress = { version: 1, job_id: "other", claim_count: 22 };
  await f.listeners[0]();
  assert.equal(
    f.dom.window.document.querySelector("#progress").textContent,
    "",
  );
  assert.equal(
    f.dom.window.document.querySelector("#stage").textContent,
    "Preparing complete results…",
  );
  while (f.frames.length) f.frames.shift()();
  assert.equal(
    f.dom.window.document.querySelector("#stage").textContent,
    "Check complete",
  );
  assert.match(
    f.dom.window.document.querySelector("#results").textContent,
    /SUPPORTED: 1/,
  );
});

test("Off and another owning tab hide evidence and invalidate scheduled paints", async () => {
  const f = await setup();
  assert.ok(f.dom.window.document.querySelector("article"));
  f.panelContext.eligible = false;
  f.panelContext.on = false;
  await f.listeners[0]();
  while (f.frames.length) f.frames.shift()();
  assert.equal(f.dom.window.document.querySelector("article"), null);
  assert.equal(
    f.dom.window.document.querySelector("#stage").textContent,
    "Verification is Off.",
  );
  assert.equal(f.dom.window.document.querySelector("#reverify").disabled, true);
  f.panelContext.on = true;
  await f.listeners[0]();
  assert.match(
    f.dom.window.document.querySelector("#stage").textContent,
    /owning response/,
  );
});
