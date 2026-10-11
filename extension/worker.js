import { eligible, savedHistory, validResult, summary } from "./core.js";
import { SERVICE_ORIGIN } from "./config.js";
let queue = Promise.resolve();
function serialized(action) {
  const task = queue.then(action);
  queue = task.catch(() => {});
  return task;
}
async function init() {
  await chrome.storage.session.setAccessLevel({
    accessLevel: "TRUSTED_CONTEXTS",
  });
  // Old Settings overrides cannot redirect any request after an upgrade.
  await chrome.storage.local.remove("backendUrl");
  const { auth } = await chrome.storage.session.get("auth");
  if (auth && auth.origin !== SERVICE_ORIGIN)
    await chrome.storage.session.remove("auth");
  const local = await chrome.storage.local.get(["enabled"]);
  const session = await chrome.storage.session.get("on");
  if (session.on === undefined)
    await chrome.storage.session.set({
      on: Boolean(local.enabled),
    });
}
const initialized = init();
chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  if (reason === "install") {
    await chrome.storage.local.set({
      everEnabled: false,
      enabled: false,
      historyEnabled: false,
    });
    await chrome.storage.session.set({ on: false });
  }
});
chrome.runtime.onStartup.addListener(async () => {
  await initialized;
  const { everEnabled } = await chrome.storage.local.get("everEnabled");
  await chrome.storage.session.set({ on: Boolean(everEnabled) });
  await chrome.storage.local.set({ enabled: Boolean(everEnabled) });
});
async function active(sender) {
  const tabs = await chrome.tabs.query({
    active: true,
    lastFocusedWindow: true,
  });
  return Boolean(
    sender.tab &&
    tabs[0]?.id === sender.tab.id &&
    eligible(sender.url) &&
    eligible(tabs[0].url),
  );
}
async function state(sender) {
  await initialized;
  const { on } = await chrome.storage.session.get("on");
  return { on: Boolean(on), active: Boolean(on) && (await active(sender)) };
}
async function submissionActive(value, requireResponse = true) {
  await initialized;
  const { on } = await chrome.storage.session.get("on");
  if (!on || !eligible(value.url)) return false;
  const [tab] = await chrome.tabs.query({
    active: true,
    lastFocusedWindow: true,
  });
  if (tab?.id !== value.tab || !eligible(tab.url)) return false;
  const current = new URL(tab.url);
  const original = new URL(value.url);
  if (
    current.origin !== original.origin ||
    current.pathname !== original.pathname
  )
    return false;
  if (!requireResponse) return true;
  if (typeof value.id !== "string" || !/^[a-f0-9]{64}$/.test(value.revision))
    return false;
  try {
    const response = await chrome.tabs.sendMessage(value.tab, {
      type: "eligible",
      id: value.id,
      revision: value.revision,
    });
    return response?.eligible === true;
  } catch {
    return false;
  }
}
async function api(path, options = {}, submission) {
  await initialized;
  const origin = SERVICE_ORIGIN;
  if (!(await chrome.permissions.contains({ origins: [origin + "/*"] })))
    throw Error("Grant hosted service access in Settings.");
  let { auth } = await chrome.storage.session.get("auth");
  if (!auth || auth.expires <= Date.now() || auth.origin !== origin) {
    const headers = {
      "X-VerifAI-Origin": chrome.runtime.getURL("").replace(/\/$/, ""),
      ...(auth?.origin === origin
        ? { Authorization: "Bearer " + auth.token }
        : {}),
    };
    const response = await fetch(origin + "/v1/session", {
      method: "POST",
      headers,
      signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) throw Error(`Service unavailable (${response.status}).`);
    const data = await response.json();
    auth = {
      token: data.token,
      expires: Date.now() + data.expires_in * 1000 - 30000,
      origin,
    };
    await chrome.storage.session.set({ auth });
  }
  if (submission && !(await submissionActive(submission))) {
    const error = Error(
      "Paused; return to the corresponding chat with verification enabled.",
    );
    error.paused = true;
    throw error;
  }
  const response = await fetch(origin + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-VerifAI-Origin": chrome.runtime.getURL("").replace(/\/$/, ""),
      Authorization: "Bearer " + auth.token,
    },
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    if (response.status === 401) await chrome.storage.session.remove("auth");
    const error = Error(`Service unavailable (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}
async function store(key, value, guarded = false) {
  return serialized(async () => {
    if (
      guarded &&
      (await chrome.storage.session.get(key))[key]?.runId !== value.runId
    )
      return;
    await chrome.storage.session.set({ [key]: value });
    const local = await chrome.storage.local.get([
      "historyEnabled",
      "retention",
      "history",
    ]);
    const history = local.historyEnabled
      ? savedHistory(local.history, local.retention)
      : {};
    if (local.historyEnabled && validResult(value.result) && local.retention)
      history[value.id] = {
        id: value.id,
        revision: value.revision,
        result: value.result,
        stage: "Complete",
        savedAt: Date.now(),
        version: 1,
      };
    try {
      await chrome.storage.local.set({
        history: savedHistory(history, local.retention),
      });
    } catch {
      let cleared = false;
      try {
        await chrome.storage.local.set({ history: {} });
        cleared = true;
      } catch {}
      await chrome.storage.session.set({
        storageNotice: cleared
          ? "History could not be saved; saved history was cleared."
          : "History could not be saved or cleared. Check Settings and try again.",
      });
    }
  });
}
async function run(key, value) {
  try {
    if (!(await submissionActive(value))) {
      const error = Error(
        "Paused; return to the corresponding chat with verification enabled.",
      );
      error.paused = true;
      throw error;
    }
    const created = await api(
      "/v1/verify",
      {
        method: "POST",
        body: JSON.stringify({ text: value.text, citations: value.citations }),
      },
      value,
    );
    await store(
      key,
      {
        ...value,
        job: created.job,
        stage: "Analyzing claims",
        result: undefined,
        attempts: value.attempts || 0,
      },
      true,
    );
    await chrome.alarms.create("poll", {
      delayInMinutes: 0.5,
      periodInMinutes: 0.5,
    });
    poll();
  } catch (error) {
    const attempts = (value.attempts || 0) + (error.paused ? 0 : 1);
    const recoverable =
      !error.status ||
      [401, 408, 429, 500, 502, 503, 504].includes(error.status);
    const retry = recoverable && attempts < 3;
    const stage = error.paused
      ? error.message
      : error.message +
        (retry
          ? " Automatic recovery will retry."
          : recoverable
            ? " Automatic retries exhausted; use Re-verify when available."
            : "");
    await store(
      key,
      {
        ...value,
        stage,
        attempts,
        retry,
        next: Date.now() + 60000,
      },
      true,
    );
    await chrome.alarms.create("poll", {
      delayInMinutes: 1,
      periodInMinutes: 0.5,
    });
  }
}
let polling = false;
let lastForegroundPoll = 0;
async function poll() {
  if (polling) return;
  polling = true;
  try {
    const data = await chrome.storage.session.get(null);
    for (const [key, value] of Object.entries(data)) {
      if (!key.startsWith("response:") || value.result) continue;
      if (!(await submissionActive(value))) continue;
      if (value.retry && value.attempts < 3 && Date.now() >= value.next) {
        await run(key, value);
        continue;
      }
      if (!value.job || value.stage === "Failed") continue;
      try {
        const job = await api("/v1/jobs/" + encodeURIComponent(value.job));
        const current = (await chrome.storage.session.get(key))[key];
        if (current?.job !== value.job) continue;
        if (job.result && !validResult(job.result)) {
          await store(
            key,
            {
              ...current,
              stage: "Failed",
              error: "Invalid verification data; use Re-verify.",
            },
            true,
          );
          continue;
        }
        await store(key, { ...current, ...job }, true);
        if (job.result || job.stage) {
          try {
            await chrome.tabs.sendMessage(value.tab, {
              type: "result",
              id: value.id,
              revision: value.revision,
              summary: job.result ? summary(job.result) : job.stage,
            });
          } catch {}
        }
      } catch (error) {
        if (error.status === 404)
          await store(
            key,
            {
              ...value,
              job: undefined,
              retry: true,
              attempts: (value.attempts || 0) + 1,
              next: Date.now() + 60000,
              stage: "Service restarted; retrying verification.",
            },
            true,
          );
        else await store(key, { ...value, stage: error.message }, true);
      }
    }
  } finally {
    polling = false;
  }
}
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "poll") poll();
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.type === "details" && sender.tab && eligible(sender.url)) {
    // Open immediately within the forwarded click gesture; selecting a result never verifies it.
    chrome.sidePanel.open({ windowId: sender.tab.windowId }).catch(() => {});
  }
  (async () => {
    if (message.type === "state") {
      const current = await state(sender);
      if (
        current.active &&
        message.poll === true &&
        Date.now() - lastForegroundPoll >= 5000
      ) {
        lastForegroundPoll = Date.now();
        poll().catch(() => {});
      }
      return current;
    }
    if (message.type === "verify") {
      if (
        !(await state(sender)).active ||
        !(await submissionActive(
          { tab: sender.tab.id, url: message.url },
          false,
        )) ||
        typeof message.text !== "string" ||
        message.text.length > 60000 ||
        !Array.isArray(message.citations) ||
        message.citations.length > 12 ||
        !/^[a-f0-9]{64}$/.test(message.revision) ||
        typeof message.id !== "string" ||
        message.id.length > 300
      )
        return { error: "ineligible" };
      const key = "response:" + sender.tab.id + ":" + message.id;
      const local = await chrome.storage.local.get([
        "history",
        "historyEnabled",
        "retention",
      ]);
      const history = local.historyEnabled
        ? savedHistory(local.history, local.retention)
        : {};
      const old =
        (await chrome.storage.session.get(key))[key] || history[message.id];
      if (old?.revision === message.revision) {
        await store(key, {
          ...old,
          text: message.text,
          citations: message.citations,
          tab: sender.tab.id,
          url: message.url,
        });
        return {
          accepted: true,
          summary: old.result ? summary(old.result) : old.stage,
        };
      }
      const value = {
        id: message.id,
        revision: message.revision,
        runId: crypto.randomUUID(),
        text: message.text,
        citations: message.citations,
        tab: sender.tab.id,
        url: message.url,
        stage: "Analyzing claims",
      };
      await store(key, value);
      run(key, value);
      return { accepted: true };
    }
    if (message.type === "details") {
      if (!(await active(sender))) return { error: "ineligible" };
      await chrome.storage.session.set({
        selected: "response:" + sender.tab.id + ":" + message.id,
      });
      return { ok: true };
    }
    if (
      !["popup.html", "settings.html", "panel.html"].some(
        (path) => sender.url === chrome.runtime.getURL(path),
      )
    )
      return { error: "sender" };
    if (message.type === "saveSettings") {
      if (Object.hasOwn(message, "backendUrl"))
        return { error: "Backend overrides are not supported." };
      const origin = SERVICE_ORIGIN;
      if (
        typeof message.historyEnabled !== "boolean" ||
        !["", "24h", "7d", "30d", "manual"].includes(message.retention) ||
        (message.historyEnabled && !message.retention)
      )
        return { error: "Choose a valid retention period first." };
      if (!(await chrome.permissions.contains({ origins: [origin + "/*"] })))
        return { error: "Hosted service access was not granted." };
      await serialized(async () => {
        const local = await chrome.storage.local.get("history");
        await chrome.storage.local.set({
          historyEnabled: message.historyEnabled,
          retention: message.retention,
          history: message.historyEnabled
            ? savedHistory(local.history, message.retention)
            : {},
        });
        await chrome.storage.session.remove("auth");
      });
      return { ok: true };
    }
    if (message.type === "clearHistory") {
      await serialized(() => chrome.storage.local.set({ history: {} }));
      return { ok: true };
    }
    if (message.type === "toggle") {
      await chrome.storage.session.set({ on: Boolean(message.on) });
      await chrome.storage.local.set({
        enabled: Boolean(message.on),
        ...(message.on ? { everEnabled: true } : {}),
      });
      return { ok: true };
    }
    if (message.type === "reverify") {
      const { selected } = await chrome.storage.session.get("selected");
      const old = (await chrome.storage.session.get(selected || ""))[selected];
      if (!old?.text)
        return { error: "Reopen the corresponding response first." };
      if (!(await submissionActive(old)))
        return {
          error:
            "Return to the corresponding ChatGPT chat and enable verification.",
        };
      const value = {
        ...old,
        runId: crypto.randomUUID(),
        result: undefined,
        job: undefined,
        attempts: 0,
        retry: false,
        stage: "Analyzing claims",
      };
      await store(selected, value);
      run(selected, value);
      return { ok: true };
    }
    return { error: "message" };
  })().then(respond, (error) => respond({ error: error.message }));
  return true;
});
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const data = await chrome.storage.session.get(null);
  await chrome.storage.session.remove(
    Object.keys(data).filter((k) => k.startsWith("response:" + tabId + ":")),
  );
});
chrome.alarms.create("cleanup", { periodInMinutes: 30 });
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== "cleanup") return;
  await serialized(async () => {
    const { history, historyEnabled, retention } =
      await chrome.storage.local.get([
        "history",
        "historyEnabled",
        "retention",
      ]);
    await chrome.storage.local.set({
      history: historyEnabled ? savedHistory(history, retention) : {},
    });
  });
});
