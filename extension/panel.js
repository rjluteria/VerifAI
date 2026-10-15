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
let renderGeneration = 0;
const benchmarkRenders = new Map();
let timerData;
let displayedResponse;
const stageLabels = {
  claims: "Identifying factual claims",
  citations: "Checking ChatGPT citations",
  independent: "Finding independent evidence",
  evaluation: "Evaluating evidence and preparing verdicts",
};
function setStatus(text) {
  const target = document.querySelector("#stage");
  if (target.textContent !== text) target.textContent = text;
}
function updateElapsed() {
  const target = document.querySelector("#elapsed");
  if (!target) return;
  const started = timerData?.triggeredAt;
  if (timerData?.cachedResult) {
    target.textContent =
      "Cached result restored · Original source retrieval times retained";
    return;
  }
  if (!Number.isFinite(started)) {
    target.textContent = "";
    return;
  }
  const elapsed = Math.max(0, (timerData.renderedAt || Date.now()) - started);
  target.textContent = `Elapsed ${(elapsed / 1000).toFixed(1)} s · Warm fresh target 30 s`;
  if (
    !timerData.result &&
    timerData.stage !== "Failed" &&
    !["paused", "failed"].includes(timerData.executionState) &&
    elapsed > 30000
  )
    setStatus(
      ["retrying", "reconnecting"].includes(timerData.executionState)
        ? "Verification is taking longer than expected. Recovering connection…"
        : "Verification is taking longer than expected. Continuing…",
    );
}
async function render() {
  const generation = ++renderGeneration;
  const { selected, storageNotice } = await chrome.storage.session.get([
    "selected",
    "storageNotice",
  ]);
  const data = selected
    ? (await chrome.storage.session.get(selected))[selected]
    : undefined;
  if (data) {
    const context = await chrome.runtime
      .sendMessage({ type: "panel-context" })
      .catch(() => ({}));
    if (generation !== renderGeneration) return;
    if (
      context.eligible !== true ||
      context.selected !== selected ||
      context.runId !== (data.runId || null)
    ) {
      last = "";
      timerData = undefined;
      displayedResponse = undefined;
      document.querySelector("#results").replaceChildren();
      document.querySelector("#progress")?.replaceChildren();
      document.querySelector("#reverify").disabled = true;
      setStatus(
        context.on === false
          ? "Verification is Off."
          : "Return to the owning response to view these results.",
      );
      updateElapsed();
      return;
    }
  }
  const paintKey = data?.runId ? "paint:" + data.runId : undefined;
  const savedPaint = paintKey
    ? (await chrome.storage.session.get(paintKey))[paintKey]
    : undefined;
  if (generation !== renderGeneration) return;
  const fingerprint = JSON.stringify([selected, data, storageNotice]);
  if (fingerprint === last) return;
  last = fingerprint;
  displayedResponse = data
    ? { responseKey: selected, expectedRunId: data.runId || null }
    : undefined;
  timerData = data
    ? {
        ...data,
        renderedAt: Number.isFinite(savedPaint) ? savedPaint : undefined,
      }
    : undefined;
  const analysisIncomplete =
    data?.result &&
    (data.result.unsupported.length ||
      data.result.claims.some((claim) => claim.errors.length));
  const overrun =
    data &&
    !data.result &&
    Number.isFinite(data.triggeredAt) &&
    Date.now() - data.triggeredAt > 30000;
  setStatus(
    analysisIncomplete
      ? "Analysis incomplete; some checks could not finish."
      : data?.result
        ? "Preparing complete results…"
        : data?.stage === "Failed" || data?.executionState === "failed"
          ? "Verification failed. Retry when available."
          : data?.executionState === "paused"
            ? data.stage
            : ["retrying", "reconnecting"].includes(data?.executionState)
              ? overrun
                ? "Verification is taking longer than expected. Recovering connection…"
                : "Connection unavailable. Automatic recovery is pending."
              : data
                ? overrun
                  ? "Verification is taking longer than expected. Continuing…"
                  : "Verifying…"
                : "Select View details beside a response.",
  );
  const progressRoot = document.querySelector("#progress");
  if (progressRoot) {
    progressRoot.replaceChildren();
    if (data?.progress?.version === 1 && data.progress.job_id === data.job) {
      if (Number.isInteger(data.progress.claim_count))
        element(
          "p",
          `Checking ${data.progress.claim_count} ${data.progress.claim_count === 1 ? "claim" : "claims"}`,
          progressRoot,
        );
      for (const [key, label] of Object.entries(stageLabels)) {
        const state = data.progress.stages?.[key];
        if (
          ["pending", "active", "complete", "failed", "unavailable"].includes(
            state,
          )
        )
          element("p", `${label}: ${state}`, progressRoot);
      }
      for (const track of ["citation", "independent"]) {
        const counts = data.progress.tracks?.[track];
        if (
          counts &&
          [counts.completed, counts.total, counts.accessible].every(
            Number.isInteger,
          ) &&
          0 <= counts.accessible &&
          counts.accessible <= counts.completed &&
          counts.completed <= counts.total &&
          counts.total <= 1000
        )
          element(
            "p",
            `${track === "citation" ? "Citation" : "Independent"} sources: ${counts.completed}/${counts.total} checks; ${counts.accessible} retrieved`,
            progressRoot,
          );
      }
    }
  }
  updateElapsed();
  document.querySelector("#reverify").disabled =
    !data?.text ||
    (!data.result &&
      data.stage !== "Failed" &&
      data.executionState !== "failed");
  const root = document.querySelector("#results");
  root.replaceChildren();
  if (storageNotice) element("p", storageNotice, root);
  if (BENCHMARK_TIMING && Number.isInteger(data?.benchmarkSubmissionAttempts))
    element(
      "p",
      `Benchmark: browser submission attempts ${data.benchmarkSubmissionAttempts}.`,
      root,
    ).id = "benchmark-submissions";
  if (BENCHMARK_TIMING && typeof data?.job === "string")
    element("p", `Benchmark job: ${data.job}`, root).id = "benchmark-job";
  if (BENCHMARK_TIMING && data?.trace?.version === 1) {
    const diagnostics = element("details", "", root);
    element("summary", "Sanitized backend timing", diagnostics);
    const timingField = element("textarea", "", diagnostics);
    timingField.id = "benchmark-causal-trace";
    timingField.setAttribute("aria-label", "Sanitized backend timing record");
    timingField.readOnly = true;
    timingField.rows = 5;
    timingField.value = JSON.stringify(data.trace);
  }
  if (!data?.result) return;
  const result = data.result;
  if (BENCHMARK_TIMING) {
    const inspection = element("details", "", root);
    element("summary", "Inspectable verification evidence", inspection);
    const field = element("textarea", "", inspection);
    field.id = "benchmark-result";
    field.setAttribute("aria-label", "Inspectable verification evidence");
    field.readOnly = true;
    field.rows = 6;
    // Factual result only: never include storage, auth, session or owning URL.
    field.value = JSON.stringify(result, null, 2);
  }
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
            source.duplicate_reason === "same_destination"
              ? "Same original destination; not independent corroboration of:"
              : "Identical retrieved content; not independent corroboration of:",
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
        if (
          source.derivation?.method ===
          "exact arithmetic from reviewer-validated unit definition"
        )
          element(
            "p",
            `Exact calculation from the quoted unit definition: ${source.derivation.calculated_IU_fraction} IU; claim asserts ${source.derivation.asserted_IU_fraction} IU. Reviewers assessed the definition; the converted comparison is calculated.`,
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
  const counts = {};
  for (const claim of result.claims)
    counts[claim.label] = (counts[claim.label] || 0) + 1;
  element(
    "p",
    ["SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNVERIFIED"]
      .map((label) => `${label.replaceAll("_", " ")}: ${counts[label] || 0}`)
      .join(" · "),
    root,
  );
  const completedCheckpoint = last;
  const finalPaint = () => {
    if (last !== completedCheckpoint || document.visibilityState !== "visible")
      return;
    timerData.renderedAt ||= Date.now();
    if (paintKey && chrome.storage.session.set && !Number.isFinite(savedPaint))
      chrome.storage.session
        .set({ [paintKey]: timerData.renderedAt })
        .catch(() => {});
    if (!analysisIncomplete) setStatus("Check complete");
    updateElapsed();
  };
  if (!BENCHMARK_TIMING)
    requestAnimationFrame(() => requestAnimationFrame(finalPaint));
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
        finalPaint();
        if (!benchmarkRenders.has(data.benchmarkRun)) {
          benchmarkRenders.set(data.benchmarkRun, {
            startedAt: data.benchmarkStartedAt,
            // Reopening a fresh result retains its first complete paint.
            // Cache restoration has a separate new dispatch clock.
            renderedAt: data.benchmarkRestored
              ? Date.now()
              : timerData.renderedAt,
          });
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
        const measurement = benchmarkRenders.get(data.benchmarkRun);
        const elapsed = measurement.renderedAt - measurement.startedAt;
        const validClock =
          data.benchmarkClock === "wall-clock-v3" &&
          data.benchmarkClockOrigin === "dispatcher" &&
          elapsed > 0;
        const clockRecord = element("textarea", "", root);
        clockRecord.id = "benchmark-clock-record";
        clockRecord.setAttribute("aria-label", "Native render clock record");
        clockRecord.readOnly = true;
        clockRecord.rows = 3;
        clockRecord.value = JSON.stringify({
          started_epoch_ms: measurement.startedAt,
          visible_final_epoch_ms: measurement.renderedAt,
          elapsed_ms: elapsed,
          clock: data.benchmarkClock,
          origin: data.benchmarkClockOrigin,
          clock_valid: validClock,
          complete: !incomplete,
          cached: Boolean(data.benchmarkRestored),
          job_id: typeof data.job === "string" ? data.job : null,
          submission_attempts: Number.isInteger(
            data.benchmarkSubmissionAttempts,
          )
            ? data.benchmarkSubmissionAttempts
            : null,
        });
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
  if (!displayedResponse) return;
  const requestedResponse = displayedResponse;
  const result = await chrome.runtime.sendMessage({
    type: "reverify",
    ...requestedResponse,
    ...(BENCHMARK_TIMING
      ? { benchmarkStartedAt: Date.now(), benchmarkClock: "wall-clock-v3" }
      : {}),
  });
  if (
    result.error &&
    displayedResponse?.responseKey === requestedResponse.responseKey &&
    displayedResponse?.expectedRunId === requestedResponse.expectedRunId
  )
    setStatus(result.error);
});
chrome.storage.onChanged.addListener(render);
// Ownership can change without a storage write or another result arriving.
chrome.tabs.onActivated?.addListener(render);
chrome.tabs.onUpdated?.addListener(render);
chrome.windows?.onFocusChanged?.addListener(render);
document.addEventListener("visibilitychange", render);
if (typeof setInterval === "function")
  setInterval(() => {
    updateElapsed();
    render();
  }, 1000);
render();
