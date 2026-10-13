import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { webcrypto } from "node:crypto";
import { JSDOM } from "jsdom";
const script = fs.readFileSync(
  new URL("../extension/content.js", import.meta.url),
  "utf8",
);
async function fixture(
  markup,
  {
    active = true,
    stopped = false,
    completion = true,
    announcement = true,
    copyDisabled = false,
    modern = false,
    role = "assistant",
    benchmarkTiming = false,
  } = {},
) {
  const page = new JSDOM(
    modern
      ? `<div>${stopped ? '<button aria-label="Stop"></button>' : ""}<div data-content-search-unit-key="turn:assistant"><h4 data-conversation-role="${role}">Role heading</h4><div data-chatgpt-selection-message-id="modern-1"><div data-markdown-text-style="assistant-message">${markup}</div></div></div><div data-conversation-role="user">Secret user content</div>${completion ? `<div class="turn-action-controls"><button aria-label="Copy" ${copyDisabled ? 'aria-disabled="true"' : ""}></button></div>` : ""}</div>${announcement ? '<span role="status" aria-live="polite">Response complete</span>' : ""}`
      : `<article>${stopped ? '<button data-testid="stop-button"></button>' : ""}<div data-message-author-role="assistant" data-message-id="message-1">${markup}</div>${completion ? '<button data-testid="copy-turn-action-button"></button>' : ""}</article><div data-message-author-role="user">Secret user content</div>`,
    {
      url: "https://chatgpt.com/c/test",
      runScripts: "outside-only",
      pretendToBeVisual: true,
    },
  );
  const window = page.window;
  let clock = 0,
    scan,
    receive;
  const sent = [];
  window.Date.now = () => clock;
  Object.defineProperty(window, "crypto", { value: webcrypto });
  window.TextEncoder = TextEncoder;
  window.setInterval = (fn) => {
    scan = fn;
    return 1;
  };
  window.chrome = {
    runtime: {
      sendMessage: async (msg) => {
        if (msg.type === "state") return { active, on: true };
        sent.push(msg);
        return { accepted: true, runId: "fixture-run", runSequence: 0 };
      },
      onMessage: {
        addListener: (fn) => {
          receive = fn;
        },
      },
    },
  };
  window.eval(
    script.replace(
      "const BENCHMARK_TIMING = false;",
      "const BENCHMARK_TIMING = " + benchmarkTiming + ";",
    ),
  );
  await scan();
  clock = 2000;
  await scan();
  return {
    page,
    window,
    sent,
    scan,
    receive,
    setClock: (value) => (clock = value),
  };
}
test("adapter excludes user/hidden/UI text and submits stable completed assistant text", async () => {
  const f = await fixture(
    "<p>Visible fact.</p><p hidden>Private hidden text</p><script>secret()</script><button>Copy</button>",
  );
  assert.equal(f.sent.length, 1);
  assert.equal(f.sent[0].text, "Visible fact.");
  assert.match(f.sent[0].revision, /^[a-f0-9]{64}$/);
  f.page.window.close();
});
test("inactive tab, streaming and unknown completion fail closed", async () => {
  for (const options of [
    { active: false },
    { stopped: true },
    { completion: false },
  ]) {
    const f = await fixture("<p>A fact.</p>", options);
    assert.equal(f.sent.length, 0);
    f.page.window.close();
  }
});
test("revision changes need another stable interval and do not duplicate old submissions", async () => {
  const f = await fixture("<p>A fact.</p>");
  await f.scan();
  assert.equal(f.sent.length, 1);
  f.window.document.querySelector("p").textContent = "A changed fact.";
  f.setClock(3000);
  await f.scan();
  assert.equal(f.sent.length, 1);
  f.setClock(5000);
  await f.scan();
  assert.equal(f.sent.length, 2);
  assert.notEqual(f.sent[0].revision, f.sent[1].revision);
  f.page.window.close();
});
test("table row and column relationships survive extraction", async () => {
  const f = await fixture(
    "<table><caption>Revenue in USD, 2025</caption><tr><th>Region</th><th>Revenue</th></tr><tr><td>West</td><td>20</td></tr></table>",
  );
  assert.match(f.sent[0].text, /Region: West; Revenue: 20/);
  assert.match(f.sent[0].text, /USD, 2025/);
  f.page.window.close();
});
test("ambiguous table fails closed and citations remain HTTPS", async () => {
  const f = await fixture(
    '<table><tr><th colspan="2">Numbers</th></tr><tr><td>20</td><td>30</td></tr></table><a href="https://example.org/source">Source</a><a href="http://example.org/insecure">Unsafe</a>',
  );
  assert.match(f.sent[0].text, /Not Verifiable/);
  assert.deepEqual(Array.from(f.sent[0].citations), [
    "https://example.org/source",
  ]);
  f.page.window.close();
});

test("multi-level headers and qualifiers retain each row context", async () => {
  const f = await fixture(
    '<table><caption>Revenue USD</caption><thead><tr><th rowspan="2">Entity</th><th colspan="2">Revenue</th></tr><tr><th>2024</th><th>2025</th></tr></thead><tbody><tr><th scope="row">Aster</th><td>80</td><td>100</td></tr></tbody><tfoot><tr><td colspan="3">Estimated values</td></tr></tfoot></table>',
  );
  assert.match(
    f.sent[0].text,
    /Entity: Aster; Revenue \/ 2024: 80; Revenue \/ 2025: 100/,
  );
  assert.match(f.sent[0].text, /Estimated values/);
  f.page.window.close();
});

test("citations inside a table survive structured text conversion", async () => {
  const f = await fixture(
    '<table><tr><th>Entity</th><th>Value</th></tr><tr><td>Aster</td><td>80 <a href="https://example.org/source">source</a></td></tr></table>',
  );
  assert.deepEqual(Array.from(f.sent[0].citations), [
    "https://example.org/source",
  ]);
  f.page.window.close();
});

test("current ChatGPT role and message markers extract only completed assistant content", async () => {
  const f = await fixture(
    '<p>A cited fact. <a href="https://example.org/source">Source</a></p>',
    { modern: true },
  );
  assert.equal(f.sent.length, 1);
  assert.equal(f.sent[0].text, "A cited fact. Source");
  assert.equal(f.sent[0].id, "/c/test:modern-1");
  assert.deepEqual(Array.from(f.sent[0].citations), [
    "https://example.org/source",
  ]);
  f.window.close();
});
test("current ChatGPT adapter rejects user role, streaming, and missing completion", async () => {
  for (const options of [
    { role: "user" },
    { stopped: true },
    { completion: false },
  ]) {
    const f = await fixture("<p>A fact.</p>", { modern: true, ...options });
    assert.equal(f.sent.length, 0);
    f.window.close();
  }
});

test("late inline results cannot label replaced text before the next scan", async () => {
  const f = await fixture("<p>A fact.</p>");
  const original = f.sent[0];
  f.window.document.querySelector("p").textContent = "Replacement fact.";
  f.receive({
    type: "result",
    runId: "fixture-run",
    id: original.id,
    revision: original.revision,
    summary: "SUPPORTED old response",
  });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.doesNotMatch(
    f.window.document.querySelector("[data-verifai-label]").textContent,
    /SUPPORTED old/,
  );
  f.window.close();
});
test("late results from a different SPA conversation are not rendered", async () => {
  const f = await fixture("<p>A fact.</p>");
  const original = f.sent[0];
  f.window.history.pushState({}, "", "/c/other");
  f.receive({
    type: "result",
    runId: "fixture-run",
    id: original.id,
    revision: original.revision,
    summary: "SUPPORTED old conversation",
  });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.doesNotMatch(
    f.window.document.querySelector("[data-verifai-label]").textContent,
    /SUPPORTED old/,
  );
  f.window.close();
});

test("response eligibility rejects replaced, streaming, hidden and other-branch content", async () => {
  const f = await fixture("<p>A fact.</p>");
  const original = f.sent[0];
  const eligible = () =>
    new Promise((resolve) =>
      f.receive(
        { type: "eligible", id: original.id, revision: original.revision },
        {},
        resolve,
      ),
    );
  assert.equal((await eligible()).eligible, true);
  f.window.document.querySelector("article").style.display = "none";
  assert.equal((await eligible()).eligible, false);
  f.window.document.querySelector("article").style.display = "";
  const stop = f.window.document.createElement("button");
  stop.setAttribute("aria-label", "Stop");
  f.window.document.body.append(stop);
  assert.equal((await eligible()).eligible, false);
  stop.remove();
  f.window.document.querySelector("p").textContent = "Replacement fact.";
  assert.equal((await eligible()).eligible, false);
  f.window.document.querySelector("p").textContent = "A fact.";
  f.window.history.pushState({}, "", "/c/other");
  assert.equal((await eligible()).eligible, false);
  f.window.close();
});

test("refreshed modern responses use persistent completion controls, not transient announcements", async () => {
  const completed = await fixture("<p>A saved fact.</p>", {
    modern: true,
    announcement: false,
  });
  assert.equal(completed.sent.length, 1);
  completed.window.close();
  for (const options of [
    { completion: false, announcement: true },
    { copyDisabled: true, announcement: true },
  ]) {
    const incomplete = await fixture("<p>An unfinished fact.</p>", {
      modern: true,
      ...options,
    });
    assert.equal(incomplete.sent.length, 0);
    incomplete.window.close();
  }
});

test("multiple refreshed responses keep distinct identities and do not borrow completion controls", async () => {
  const f = await fixture("<p>First fact.</p>", {
    modern: true,
    announcement: false,
  });
  const second = f.window.document.body.firstElementChild.cloneNode(true);
  second
    .querySelector("[data-chatgpt-selection-message-id]")
    .setAttribute("data-chatgpt-selection-message-id", "modern-2");
  second.querySelector("p").textContent = "Second fact.";
  second.querySelector(".turn-action-controls").remove();
  f.window.document.body.append(second);
  f.setClock(4000);
  await f.scan();
  assert.equal(f.sent.length, 1);
  const controls = f.window.document.createElement("div");
  controls.className = "turn-action-controls";
  controls.innerHTML = '<button aria-label="Copy"></button>';
  second.append(controls);
  await f.scan();
  f.setClock(6000);
  await f.scan();
  assert.equal(f.sent.length, 2);
  assert.equal(f.sent[1].id, "/c/test:modern-2");
  assert.equal(f.sent[1].text, "Second fact.");
  f.window.close();
});

test("View details follows current conversation identity when a response node is reused", async () => {
  const f = await fixture("<p>A fact.</p>");
  f.window.history.pushState({}, "", "/c/reused-node");
  f.setClock(4000);
  await f.scan();
  assert.equal(f.window.document.querySelector("[data-verifai]"), null);
  f.setClock(6000);
  await f.scan();
  f.window.document.querySelector("[data-verifai] button").click();
  assert.equal(f.sent.at(-1).type, "details");
  assert.equal(f.sent.at(-1).id, "/c/reused-node:message-1");
  f.window.close();
});

test("developer clock begins at content dispatch; normal submissions omit timing", async () => {
  for (const enabled of [false, true]) {
    const f = await fixture("<p>A fact.</p>", { benchmarkTiming: enabled });
    const sent = f.sent[0];
    if (enabled) {
      assert.ok(Number.isFinite(sent.benchmarkStartedAt));
      assert.equal(sent.benchmarkStartedAt, 2000);
      assert.equal(sent.benchmarkClock, "wall-clock-v3");
    } else assert.equal(Object.hasOwn(sent, "benchmarkStartedAt"), false);
    f.page.window.close();
  }
});

test("same-revision results from a superseded verification run cannot overwrite progress", async () => {
  const f = await fixture("<p>A fact.</p>");
  const message = f.sent[0];
  f.receive({
    type: "verification-started",
    id: message.id,
    revision: message.revision,
    runId: "replacement-run",
    runSequence: 1,
  });
  f.receive({
    type: "result",
    id: message.id,
    revision: message.revision,
    runId: "fixture-run",
    summary: "Old retry failure",
  });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.doesNotMatch(
    f.window.document.querySelector("[data-verifai-label]").textContent,
    /Old retry failure/,
  );
  f.receive({
    type: "result",
    id: message.id,
    revision: message.revision,
    runId: "replacement-run",
    summary: "Service unavailable; automatic recovery will retry.",
  });
  // WebCrypto completes asynchronously; runner load must not decide this assertion.
  const deadline = Date.now() + 2000;
  while (
    !f.window.document
      .querySelector("[data-verifai-label]")
      .textContent.includes("automatic recovery will retry") &&
    Date.now() < deadline
  ) {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.match(
    f.window.document.querySelector("[data-verifai-label]").textContent,
    /automatic recovery will retry/,
  );
  f.window.close();
});

test("out-of-order start notices cannot roll a response back to an earlier Re-verify run", async () => {
  const f = await fixture("<p>A fact.</p>");
  const message = f.sent[0];
  f.receive({
    type: "verification-started",
    id: message.id,
    revision: message.revision,
    runId: "newest",
    runSequence: 2,
  });
  f.receive({
    type: "verification-started",
    id: message.id,
    revision: message.revision,
    runId: "older",
    runSequence: 1,
  });
  f.receive({
    type: "result",
    id: message.id,
    revision: message.revision,
    runId: "older",
    summary: "Old final verdict",
  });
  f.receive({
    type: "result",
    id: message.id,
    revision: message.revision,
    runId: "newest",
    summary: "Current verification progress",
  });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(
    f.window.document.querySelector("[data-verifai-label]").textContent,
    "Current verification progress",
  );
  f.window.close();
});

test("unavailable response placeholders never submit or offer factual details", async () => {
  for (const modern of [false, true]) {
    for (const text of [
      "This response couldn’t load",
      "This response couldn't load.",
    ]) {
      const f = await fixture(`<p>${text}</p>`, { modern });
      assert.equal(f.sent.length, 0);
      assert.match(
        f.window.document.querySelector("[data-verifai]").textContent,
        /Not Verifiable: response unavailable/,
      );
      assert.equal(
        f.window.document.querySelector("[data-verifai] button"),
        null,
      );
      f.window.close();
    }
  }
});

test("a load error replacing a pending response rejects eligibility and stale results", async () => {
  const f = await fixture("<p>A real factual claim.</p>");
  const original = f.sent[0];
  f.window.document.querySelector("p").textContent =
    "This response couldn’t load";
  const eligibility = await new Promise((resolve) =>
    f.receive(
      { type: "eligible", id: original.id, revision: original.revision },
      {},
      resolve,
    ),
  );
  assert.equal(eligibility.eligible, false);
  await f.scan();
  f.receive({
    type: "result",
    id: original.id,
    revision: original.revision,
    runId: "fixture-run",
    summary: "SUPPORTED stale claim",
  });
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.doesNotMatch(
    f.window.document.querySelector("[data-verifai]").textContent,
    /SUPPORTED/,
  );
  assert.equal(f.sent.length, 1);
  f.window.document.querySelector("p").textContent =
    "A restored factual claim.";
  await f.scan();
  f.setClock(4000);
  await f.scan();
  assert.equal(f.sent.length, 2);
  assert.equal(f.sent[1].text, "A restored factual claim.");
  f.window.close();
});

test("standalone citation captions do not become claims but destinations and factual anchor text remain", async () => {
  const f = await fixture(
    '<p>First fact. Second fact.</p><p><a href="https://example.org/one">Source 1</a></p><p><a href="https://example.org/two">Reference 2</a></p><p><a href="https://example.org/three">Mercury rotates in about 59 days.</a></p>',
  );
  assert.equal(f.sent.length, 1);
  assert.doesNotMatch(f.sent[0].text, /Source 1|Reference 2/);
  assert.match(f.sent[0].text, /First fact\. Second fact\./);
  assert.match(f.sent[0].text, /Mercury rotates in about 59 days/);
  assert.deepEqual(Array.from(f.sent[0].citations), [
    "https://example.org/one",
    "https://example.org/two",
    "https://example.org/three",
  ]);
  f.window.close();
});

test("the load-error phrase inside a factual response is not a blanket filter", async () => {
  const f = await fixture(
    "<p>The interface displayed “This response couldn’t load” yesterday. Mercury rotates in about 59 days.</p>",
  );
  assert.equal(f.sent.length, 1);
  assert.match(f.sent[0].text, /Mercury rotates/);
  f.window.close();
});

test("caption extraction follows actual hydrated semantic lines, retaining citation order", async () => {
  for (const markup of [
    '<p>A factual statement.\n<span><span role="presentation"><a href="https://example.org/a"><span>Source 1</span><svg></svg></a></span></span></p>',
    '<p>A factual statement.<br><span><a href="https://example.org/a">Citation #1</a></span></p>',
    '<div><p>A factual statement.</p><div><span><a href="https://example.org/a">[Reference 1]</a></span></div></div>',
    '<p>A factual statement.\n<a href="https://example.org/a">Source 1</a> <a href="https://example.org/b">Reference 2</a></p>',
  ]) {
    const f = await fixture(markup, { modern: true });
    assert.equal(f.sent.length, 1);
    assert.equal(f.sent[0].text, "A factual statement.");
    assert.equal(f.sent[0].citations[0], "https://example.org/a");
    if (markup.includes("example.org/b"))
      assert.deepEqual(Array.from(f.sent[0].citations), [
        "https://example.org/a",
        "https://example.org/b",
      ]);
    f.window.close();
  }
});
test("inline factual anchors and structured table identifiers are not discarded as captions", async () => {
  for (const markup of [
    '<p><a href="https://example.org/a">Source 1</a> reported 12 observations.</p>',
    '<p><a href="https://example.org/a">The instrument weighs 3 kg.</a></p>',
    '<table><tr><th>Instrument</th><th>Count</th></tr><tr><td><a href="https://example.org/a">Source 1</a></td><td>12</td></tr></table>',
  ]) {
    const f = await fixture(markup);
    assert.match(f.sent[0].text, /Source 1|instrument weighs 3 kg/);
    assert.deepEqual(Array.from(f.sent[0].citations), [
      "https://example.org/a",
    ]);
    f.window.close();
  }
});
test("caption line removal preserves factual text after a break and delayed citation hydration", async () => {
  const f = await fixture(
    '<p>First factual statement.<br><a href="https://example.org/a">Source 1</a><br>Second factual statement.</p>',
  );
  assert.equal(
    f.sent[0].text,
    "First factual statement.\n\nSecond factual statement.",
  );
  f.window.document
    .querySelector("p")
    .insertAdjacentHTML(
      "beforeend",
      '\n<span><a href="https://example.org/b">Source 2</a></span>',
    );
  f.setClock(3000);
  await f.scan();
  assert.equal(f.sent.length, 1);
  f.setClock(5000);
  await f.scan();
  assert.equal(f.sent.length, 2);
  assert.deepEqual(Array.from(f.sent[1].citations), [
    "https://example.org/a",
    "https://example.org/b",
  ]);
  assert.equal(f.sent[1].text, f.sent[0].text);
  f.window.close();
});

test("a caption-shaped linked subject with a continuing assertion remains factual text", async () => {
  const f = await fixture(
    '<p><a href="https://example.org/a">Source 1</a>\nreported 12 observations.</p>',
  );
  assert.equal(f.sent[0].text, "Source 1\nreported 12 observations.");
  f.window.close();
});

test("computed inline wrappers retain factual linked subjects and block facts retain separation", async () => {
  const inline = await fixture(
    '<div><span>The </span><div style="display:inline"><a href="https://example.org/a">Source 1</a></div><span> reported 12 observations.</span></div>',
  );
  assert.equal(inline.sent[0].text, "The Source 1 reported 12 observations.");
  inline.window.close();
  const blocks = await fixture(
    '<div>First factual statement.</div><div>Second factual statement.</div><div><a href="https://example.org/a">Source 1</a></div>',
  );
  assert.equal(
    blocks.sent[0].text,
    "First factual statement.\n\nSecond factual statement.",
  );
  blocks.window.close();
});

test("archived native intensity DOM retains fact and citation without caption atom", async () => {
  const f = await fixture(
    '<p class="TextBase-hXhSqg Text-lIMP0_" data-d-text-flow="" data-d-component="text">Earthquake intensity describes ground shaking at a particular locality.\n<span class="Trigger-C5mz9C" data-d-component="popover-trigger" data-d-inline="" data-d-inline-text="" role="presentation" type="button" aria-haspopup="dialog" aria-expanded="false" data-state="closed"><a class="" href="https://www.usgs.gov/publications/magnitude-and-intensity-measures-earthquake-size-and-severity" rel="noopener noreferrer" target="_blank"><span class="TextBase-hXhSqg Text-lIMP0_" data-d-text-flow="" data-d-component="text" data-d-inline="" data-d-text-decoration="underline-dotted">Source 1</span><span class="ms-1"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" data-d-component="icon" data-d-inline="" style="display: inline-block; vertical-align: text-bottom;"><path fill-rule="evenodd" d="M16.243 6.757a1 1 0 0 1 1 1v7.072a1 1 0 0 1-2 0v-4.657L8.464 16.95a1 1 0 0 1-1.414-1.414l6.778-6.779H9.172a1 1 0 0 1 0-2h7.07Z" clip-rule="evenodd"></path></svg></span></a></span></p>',
    { modern: true },
  );
  assert.equal(f.sent.length, 1);
  assert.equal(
    f.sent[0].text,
    "Earthquake intensity describes ground shaking at a particular locality.",
  );
  assert.deepEqual(Array.from(f.sent[0].citations), [
    "https://www.usgs.gov/publications/magnitude-and-intensity-measures-earthquake-size-and-severity",
  ]);
  f.page.window.close();
});
