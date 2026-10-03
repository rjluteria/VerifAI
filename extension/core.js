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
  if (!(retention in durations)) return {};
  return Object.fromEntries(
    Object.entries(history).filter(
      ([, v]) =>
        Number.isFinite(v.savedAt) && now - v.savedAt < durations[retention],
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
  return labels
    .map(
      (label) =>
        `${label.replaceAll("_", " ").toLowerCase()}: ${result.claims.filter((c) => c.label === label).length}`,
    )
    .join(" · ");
}
