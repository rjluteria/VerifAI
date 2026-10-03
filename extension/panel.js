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
  } catch {}
}
let last = "";
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
  document.querySelector("#stage").textContent =
    data?.stage || "Select View details beside a response.";
  document.querySelector("#reverify").disabled = !data?.text;
  const root = document.querySelector("#results");
  root.replaceChildren();
  if (storageNotice) element("p", storageNotice, root);
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
    element("p", claim.label.replaceAll("_", " "), card).className = "status";
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
  for (const citation of result.citation_access)
    if (!citation.accessible) {
      const p = element("p", "Citation could not be retrieved: ", root);
      link(citation.url, p);
    }
  element("p", result.notice, root).className = "muted";
}
document.querySelector("#reverify").addEventListener("click", async () => {
  const result = await chrome.runtime.sendMessage({ type: "reverify" });
  if (result.error) document.querySelector("#stage").textContent = result.error;
});
chrome.storage.onChanged.addListener(render);
render();
