import { BENCHMARK_TIMING } from "./config.js";
function element(tag, text, parent) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (parent) parent.append(node);
  return node;
}
function link(url, parent) {
  try {
    const u = new URL(url);
    if (u.protocol !== "https:" || u.username || u.password) return;
    const a = element("a", url, parent);
    a.href = u.href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.addEventListener("click", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      chrome.tabs.create({ url: a.href, active: true }).catch(() => {
        document.querySelector("#stage").textContent =
          "The source tab could not be opened. Try the link again.";
      });
    });
  } catch {}
}
let last = "";
const benchmarkRenders = new Map();
async function render() {
  const { selected, storageNotice } = await chrome.storage.session.get([
    "selected",
    "storageNotice",
  ]);
  const data = selected
    ? (await chrome.storage.session.get(selected))[selected]
    : undefined;
  const fingerprint = JSON.stringify([selected, data, storageNotice]);
  if (fingerprint === last) return;
  last = fingerprint;
  const analysisIncomplete =
    data?.result &&
    (data.result.unsupported.length ||
      data.result.claims.some((claim) => claim.errors.length));
  document.querySelector("#stage").textContent = analysisIncomplete
    ? "Analysis incomplete; some checks could not finish."
    : data?.stage || "Select View details beside a response.";
  document.querySelector("#reverify").disabled = !data?.text;
  const root = document.querySelector("#results");
  root.replaceChildren();
  if (storageNotice) element("p", storageNotice, root);
  if (BENCHMARK_TIMING && Number.isInteger(data?.benchmarkSubmissionAttempts))
    element(
      "p",
      `Benchmark: browser submission attempts ${data.benchmarkSubmissionAttempts}.`,
      root,
    ).id = "benchmark-submissions";
  if (!data?.result) return;
  const result = data.result;
  if (!result.claims.length)
    element(
      "p",
      result.unsupported.length
        ? "Not Verifiable: analysis incomplete."
        : "No verifiable claims detected.",
      root,
    );
  for (const limitation of result.unsupported)
    element("p", "Not Verifiable: " + limitation, root);
  for (const claim of result.claims) {
    const card = element("article", "", root);
    element("h2", claim.text, card);
    const label = claim.label.replaceAll("_", " ");
    element(
      "p",
      claim.errors.length ? "Analysis incomplete: " + label : label,
      card,
    ).className = "status";
    for (const [track, sources] of Object.entries(claim.tracks)) {
      element(
        "h3",
        track === "citation" ? "ChatGPT Citation" : "Independent Sources",
        card,
      );
      if (track === "independent" && sources.length)
        element(
          "p",
          "These pages were found independently; they may share an original source. Their number does not establish independent corroboration.",
          card,
        );
      if (!sources.length)
        element("p", "No evidence available for this track.", card);
      for (const source of sources) {
        const section = element("section", "", card);
        link(source.url, section);
        element(
          "p",
          source.accessible
            ? "Retrieved " + new Date(source.checked_at * 1000).toLocaleString()
            : "Source inaccessible to verification service",
          section,
        );
        element(
          "p",
          source.label.replaceAll("_", " ") + ": " + source.reason,
          section,
        );
        if (source.review_reconsidered)
          element(
            "p",
            "Reviewers repeated the assessment because initial reviews disagreed or could not be completed.",
            section,
          );
        if (source.duplicate_of) {
          element(
            "p",
            "Identical retrieved content; not independent corroboration of:",
            section,
          );
          link(source.duplicate_of, section);
        }
        for (const snippet of source.snippets)
          element("blockquote", snippet.text, section);
        if (source.calculation)
          element(
            "p",
            "Calculation from the claim’s stated operands.",
            section,
          );
        if (source.final_url && source.final_url !== source.url) {
          element("p", "Redirect destination:", section);
          link(source.final_url, section);
        }
      }
    }
    for (const error of claim.errors) element("p", error, card);
  }
  for (const citation of result.citation_access || [])
    if (!citation.accessible) {
      const p = element("p", "Citation could not be retrieved: ", root);
      link(citation.url, p);
    }
  element("p", result.notice, root).className = "muted";
  if (
    BENCHMARK_TIMING &&
    Number.isFinite(data.benchmarkStartedAt) &&
    data.benchmarkRun
  ) {
    const checkpoint = last;
    // Two frames allow the complete verdict/evidence DOM to be painted first.
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        if (last !== checkpoint || document.visibilityState !== "visible")
          return;
        if (!benchmarkRenders.has(data.benchmarkRun)) {
          benchmarkRenders.set(
            data.benchmarkRun,
            Date.now() - data.benchmarkStartedAt,
          );
          if (benchmarkRenders.size > 200)
            benchmarkRenders.delete(benchmarkRenders.keys().next().value);
        }
        const incomplete =
          result.unsupported.length ||
          result.claims.some((claim) => claim.errors.length);
        const kind = data.benchmarkRestored
          ? "cached result restored"
          : incomplete
            ? "incomplete result rendered"
            : "final result rendered";
        const elapsed = benchmarkRenders.get(data.benchmarkRun);
        const validClock =
          data.benchmarkClock === "wall-clock-v3" &&
          data.benchmarkClockOrigin === "dispatcher" &&
          elapsed > 0;
        element(
          "p",
          validClock
            ? `Benchmark: ${kind} after ${elapsed.toFixed(3)} ms. Clock: wall-clock-v3; origin: dispatcher.`
            : `Benchmark: invalid render clock (${elapsed.toFixed(3)} ms; origin: ${data.benchmarkClockOrigin || "unknown"}). No latency pass.`,
          root,
        ).id = "benchmark-timing";
      }),
    );
  }
}
document.querySelector("#reverify").addEventListener("click", async () => {
  const result = await chrome.runtime.sendMessage({
    type: "reverify",
    ...(BENCHMARK_TIMING
      ? { benchmarkStartedAt: Date.now(), benchmarkClock: "wall-clock-v3" }
      : {}),
  });
  if (result.error) document.querySelector("#stage").textContent = result.error;
});
chrome.storage.onChanged.addListener(render);
render();
