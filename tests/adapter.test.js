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
        return { accepted: true };
      },
      onMessage: {
        addListener: (fn) => {
          receive = fn;
        },
      },
    },
  };
  window.eval(script);
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
