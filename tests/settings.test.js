import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { JSDOM } from "jsdom";
import { SERVICE_ORIGIN } from "../extension/config.js";

test("settings hides endpoint controls and saves history with configured permission", async () => {
  const html = fs.readFileSync(
    new URL("../extension/settings.html", import.meta.url),
    "utf8",
  );
  const script = fs
    .readFileSync(new URL("../extension/settings.js", import.meta.url), "utf8")
    .replace(/^import .*;\n/, "");
  const dom = new JSDOM(html, { runScripts: "outside-only" });
  const messages = [],
    permissions = [];
  dom.window.SERVICE_ORIGIN = SERVICE_ORIGIN;
  dom.window.chrome = {
    storage: {
      local: {
        get: async (keys) => {
          assert.equal(keys.includes("backendUrl"), false);
          return {
            historyEnabled: false,
            retention: "24h",
            backendUrl: "https://other.onrender.com",
          };
        },
      },
    },
    permissions: {
      request: async (value) => {
        permissions.push(value);
        return true;
      },
    },
    runtime: {
      id: "test",
      sendMessage: async (value) => {
        messages.push(value);
        return { ok: true };
      },
    },
  };
  await dom.window.eval("(async () => {" + script + "})()");
  assert.equal(dom.window.document.querySelector("#backend"), null);
  assert.equal(dom.window.document.querySelector('input[type="url"]'), null);
  assert.doesNotMatch(
    dom.window.document.body.textContent,
    /Hosted service URL|https:\/\//,
  );
  dom.window.document.querySelector("#history").checked = true;
  dom.window.document
    .querySelector("#settings")
    .dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(permissions[0].origins[0], SERVICE_ORIGIN + "/*");
  assert.deepEqual(JSON.parse(JSON.stringify(messages[0])), {
    type: "saveSettings",
    historyEnabled: true,
    retention: "24h",
  });
  assert.equal(
    dom.window.document.querySelector("#notice").textContent,
    "Settings saved.",
  );
  dom.window.close();
});
