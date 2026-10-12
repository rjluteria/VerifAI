export const HOSTS = new Set(["chatgpt.com", "chat.openai.com"]);
export function eligible(url) {
  try {
    const u = new URL(url);
    return (
      u.protocol === "https:" &&
      !u.port &&
      !u.username &&
      !u.password &&
      HOSTS.has(u.hostname)
    );
  } catch {
    return false;
  }
}
export function prune(history, retention, now = Date.now()) {
  const durations = {
    "24h": 86400000,
    "7d": 604800000,
    "30d": 2592000000,
    manual: Infinity,
  };
  if (
    !Object.hasOwn(durations, retention) ||
    !history ||
    typeof history !== "object" ||
    Array.isArray(history)
  )
    return {};
  return Object.fromEntries(
    Object.entries(history).filter(
      ([, v]) =>
        v &&
        typeof v === "object" &&
        !Array.isArray(v) &&
        Number.isFinite(v.savedAt) &&
        v.savedAt <= now &&
        now - v.savedAt < durations[retention],
    ),
  );
}
export function backend(url) {
  const u = new URL(url);
  if (
    u.protocol !== "https:" ||
    !u.hostname.endsWith(".onrender.com") ||
    u.username ||
    u.password ||
    u.port ||
    u.pathname !== "/" ||
    u.search ||
    u.hash
  )
    throw Error("Use the exact HTTPS Render service origin.");
  return u.origin;
}
function proofUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password;
  } catch {
    return false;
  }
}
export function validResult(result) {
  const labels = new Set([
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTED",
    "UNVERIFIED",
  ]);
  return Boolean(
    result &&
    Array.isArray(result.claims) &&
    result.claims.length <= 60 &&
    Array.isArray(result.unsupported) &&
    result.unsupported.every((v) => typeof v === "string") &&
    result.claims.every(
      (claim) =>
        claim &&
        typeof claim.text === "string" &&
        labels.has(claim.label) &&
        Array.isArray(claim.errors) &&
        ["citation", "independent"].every(
          (track) =>
            Array.isArray(claim.tracks?.[track]) &&
            claim.tracks[track].every(
              (source) =>
                source &&
                typeof source.url === "string" &&
                proofUrl(source.url) &&
                (!source.final_url || proofUrl(source.final_url)) &&
                labels.has(source.label) &&
                typeof source.reason === "string" &&
                typeof source.accessible === "boolean" &&
                Array.isArray(source.snippets) &&
                source.snippets.every(
                  (snippet) => typeof snippet?.text === "string",
                ),
            ),
        ),
    ) &&
    (result.citation_access === undefined ||
      (Array.isArray(result.citation_access) &&
        result.citation_access.every(
          (source) =>
            source &&
            typeof source.url === "string" &&
            proofUrl(source.url) &&
            (!source.final_url || proofUrl(source.final_url)) &&
            typeof source.accessible === "boolean",
        ))),
  );
}
export function savedHistory(history, retention, now = Date.now()) {
  const rows = Object.entries(prune(history, retention, now))
    .filter(
      ([id, value]) =>
        id.length <= 300 &&
        value.id === id &&
        /^[a-f0-9]{64}$/.test(value.revision) &&
        (value.version === undefined || value.version === 1) &&
        validResult(value.result),
    )
    .sort((a, b) => b[1].savedAt - a[1].savedAt);
  const result = {};
  let size = 0;
  for (const [id, value] of rows.slice(0, 100)) {
    const safe = {
      id,
      revision: value.revision,
      result: value.result,
      stage: "Complete",
      savedAt: value.savedAt,
      version: 1,
    };
    const bytes = new TextEncoder().encode(JSON.stringify([id, safe])).length;
    if (size + bytes > 1000000) continue;
    size += bytes;
    Object.defineProperty(result, id, {
      value: safe,
      enumerable: true,
      configurable: true,
      writable: true,
    });
  }
  return result;
}
export function summary(result) {
  if (!result.claims.length)
    return result.unsupported.length
      ? "Not Verifiable: some content could not be analyzed."
      : "No verifiable claims detected.";
  const labels = [
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTED",
    "UNVERIFIED",
  ];
  const incomplete =
    result.unsupported.length ||
    result.claims.some((claim) => claim.errors?.length);
  const counts = labels
    .map(
      (label) =>
        `${label.replaceAll("_", " ").toLowerCase()}: ${result.claims.filter((c) => c.label === label).length}`,
    )
    .join(" · ");
  return incomplete ? "Analysis incomplete · " + counts : counts;
}
