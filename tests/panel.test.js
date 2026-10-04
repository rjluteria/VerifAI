import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { JSDOM } from "jsdom";

async function setup() {
  const dom = new JSDOM(
    '<p id="stage"></p><button id="reverify"></button><main id="results"></main>',
  );
  const opened = [],
    messages = [],
    listeners = [];
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
    fs.readFileSync(new URL("../extension/panel.js", import.meta.url), "utf8"),
    { document: dom.window.document, URL, chrome, Date },
  );
  await new Promise((resolve) => setImmediate(resolve));
  return { dom, opened, messages, data, listeners };
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
