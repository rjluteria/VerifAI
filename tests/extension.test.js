import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { eligible, prune, backend, summary } from "../extension/core.js";
test("only exact HTTPS ChatGPT hosts qualify", () => {
  for (const u of ["https://chatgpt.com/c/1", "https://chat.openai.com/"])
    assert.equal(eligible(u), true);
  for (const u of [
    "https://chatgpt.com.evil.test",
    "http://chatgpt.com",
    "https://evil.test",
    "https://chatgpt.com:444",
    "invalid",
  ])
    assert.equal(eligible(u), false);
});
test("history expiry, invalid retention and manual retention", () => {
  const history = {
    old: { savedAt: 0 },
    recent: { savedAt: 100000000 },
    bad: {},
  };
  assert.deepEqual(Object.keys(prune(history, "24h", 100000001)), ["recent"]);
  assert.deepEqual(prune(history, "", 100000001), {});
  assert.deepEqual(Object.keys(prune(history, "manual", 100000001)), [
    "old",
    "recent",
  ]);
});
test("only exact Render origins accepted", () => {
  assert.equal(
    backend("https://verifai-example.onrender.com/"),
    "https://verifai-example.onrender.com",
  );
  for (const u of [
    "http://x.onrender.com",
    "https://x.onrender.com.evil.test",
    "https://u:p@x.onrender.com",
    "https://x.onrender.com/path",
  ])
    assert.throws(() => backend(u));
});
test("coverage summaries never imply percentage truth", () => {
  assert.equal(
    summary({ claims: [], unsupported: [] }),
    "No verifiable claims detected.",
  );
  assert.match(summary({ claims: [], unsupported: ["x"] }), /Not Verifiable/);
  assert.match(
    summary({ claims: [{ label: "UNVERIFIED" }], unsupported: [] }),
    /unverified: 1/,
  );
});
test("manifest permissions and private source boundary", () => {
  const manifest = JSON.parse(
    fs.readFileSync(new URL("../extension/manifest.json", import.meta.url)),
  );
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.host_permissions, [
    "https://chatgpt.com/*",
    "https://chat.openai.com/*",
  ]);
  assert.equal(JSON.stringify(manifest).includes("<all_urls>"), false);
  assert.deepEqual(manifest.optional_host_permissions, [
    "https://verifai-ekan.onrender.com/*",
  ]);
});

test("incomplete review summaries stay distinct from completed factual uncertainty", () => {
  const result = {
    claims: [
      {
        label: "UNVERIFIED",
        errors: ["Evidence review could not be completed."],
      },
    ],
    unsupported: [],
  };
  assert.match(summary(result), /^Analysis incomplete · /);
  result.claims[0].errors = [];
  assert.doesNotMatch(summary(result), /incomplete/);
  result.unsupported.push("Unsupported image claim.");
  assert.match(summary(result), /^Analysis incomplete · /);
});
