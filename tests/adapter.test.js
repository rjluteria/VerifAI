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
  { active = true, stopped = false, completion = true } = {},
) {
  const page = new JSDOM(
    `<article>${stopped ? '<button data-testid="stop-button"></button>' : ""}<div data-message-author-role="assistant" data-message-id="message-1">${markup}</div>${completion ? '<button data-testid="copy-turn-action-button"></button>' : ""}</article><div data-message-author-role="user">Secret user content</div>`,
    {
      url: "https://chatgpt.com/c/test",
      runScripts: "outside-only",
      pretendToBeVisual: true,
    },
  );
  const window = page.window;
  let clock = 0,
    scan;
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
      onMessage: { addListener: () => {} },
    },
  };
  window.eval(script);
  await scan();
  clock = 2000;
  await scan();
  return { page, window, sent, scan, setClock: (value) => (clock = value) };
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
