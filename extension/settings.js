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
      const result = await chrome.runtime.sendMessage({
        type: "saveSettings",
        backendUrl: origin,
        historyEnabled,
        retention,
      });
      if (result.error) throw Error(result.error);
      document.querySelector("#notice").textContent = "Settings saved.";
    } catch (error) {
      document.querySelector("#notice").textContent = error.message;
    }
  });
document.querySelector("#clear").addEventListener("click", async () => {
  const result = await chrome.runtime.sendMessage({ type: "clearHistory" });
  document.querySelector("#notice").textContent =
    result.error || "Saved history cleared.";
});
