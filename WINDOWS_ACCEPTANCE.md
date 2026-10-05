# Native Windows Chrome acceptance

Native Windows Chrome has not been tested in the current development environment. Automated Windows CI checks do not establish native browser acceptance.

Prerequisites: current Windows Chrome, the prepared extension package extracted, and the test backend configured by its operator to allow this extension's exact Windows origin. Keep API keys on the backend. Use only the synthetic conversation below.

1. Load the extracted extension through `chrome://extensions` → Developer mode → Load unpacked. On a first installation, verify the popup says **Off** and history is disabled in Settings. Configure the approved service URL.
2. Sign in to ChatGPT, open a temporary chat, and request: “Reply with exactly: Venus takes about 243 Earth days to rotate once. Add a link to https://science.nasa.gov/venus/venus-facts/.” Enable VerifAI. Observe **Active**, staged progress, and a completed inline result associated with that response.
3. Open **View details**. Confirm the sentence and citation match, both evidence tracks are displayed separately, and the NASA link opens the intended readable page in a new Chrome tab. Return to the chat: opening the source must not have triggered another verification.
4. Close the panel. Confirm it stays closed. Open details again, choose **Re-verify**, and observe fresh progress and replacement of the selected result without the panel opening itself.
5. Switch to a non-ChatGPT tab and observe **Paused**. Return to the chat and observe **Active**. Turn verification **Off**, reload the extension, and confirm it remains **Off**.
6. Quit Chrome completely and reopen it. Step 2 previously enabled verification, so the documented new-session rule restores it enabled even though step 5 switched it **Off** for that session. Confirm **Paused** outside ChatGPT and **Active** on the synthetic chat. This differs from the worker/extension reload in step 5, which must preserve **Off** within the same browser session. Finish with verification and history **Off**.

Record Chrome/Windows versions, each observation, failures, and screenshots containing only the synthetic test. Backend, unit, security, and CI suites do not need to be rerun manually for this gate. A failure leaves native Windows acceptance incomplete.
