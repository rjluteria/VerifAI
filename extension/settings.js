import { backend } from "./core.js";
const values = await chrome.storage.local.get([
  "backendUrl",
  "historyEnabled",
  "retention",
]);
document.querySelector("#backend").value = values.backendUrl || "";
document.querySelector("#history").checked = Boolean(values.historyEnabled);
document.querySelector("#retention").value = values.retention || "";
document.querySelector("#identity").textContent =
  "Service allowed origin: chrome-extension://" + chrome.runtime.id;
document
  .querySelector("#settings")
  .addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const origin = backend(document.querySelector("#backend").value);
      const historyEnabled = document.querySelector("#history").checked;
      const retention = document.querySelector("#retention").value;
      if (historyEnabled && !retention)
        throw Error("Choose a retention period first.");
      const granted = await chrome.permissions.request({
        origins: [origin + "/*"],
      });
      if (!granted) throw Error("Hosted service access was not granted.");
      await chrome.storage.local.set({
        backendUrl: origin,
        historyEnabled,
        retention,
        ...(!historyEnabled ? { history: {} } : {}),
      });
      await chrome.storage.session.remove("auth");
      document.querySelector("#notice").textContent = "Settings saved.";
    } catch (error) {
      document.querySelector("#notice").textContent = error.message;
    }
  });
document.querySelector("#clear").addEventListener("click", async () => {
  await chrome.storage.local.set({ history: {} });
  document.querySelector("#notice").textContent = "Saved history cleared.";
});
