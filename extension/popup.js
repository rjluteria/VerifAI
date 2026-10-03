import { eligible } from "./core.js";
const { on } = await chrome.storage.session.get("on");
const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
document.querySelector("#on").checked = Boolean(on);
document.querySelector("#status").textContent = on
  ? eligible(tab?.url)
    ? "Active"
    : "Paused"
  : "Off";
document.querySelector("#on").addEventListener("change", async (event) => {
  await chrome.runtime.sendMessage({
    type: "toggle",
    on: event.target.checked,
  });
  location.reload();
});
document
  .querySelector("#settings")
  .addEventListener("click", () => chrome.runtime.openOptionsPage());
