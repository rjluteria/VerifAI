# VerifAI

**A Chrome extension that helps you fact-check ChatGPT responses.**

VerifAI checks factual claims in ChatGPT responses. It looks at the sources ChatGPT provides, searches for other evidence online, and shows whether each claim is supported, partly supported, contradicted, or unverified.

You can read the evidence and open the source links to check the results yourself.

**Current version:** v0.1.19  
**Browser:** Google Chrome (120 or newer)  
**Supported chatbot:** ChatGPT

[Download VerifAI](https://github.com/rjluteria/VerifAI/releases/tag/v0.1.19) · [Installation](#installation) · [How it works](#how-it-works)

## What VerifAI does

- **Checks citations.** Looks at ChatGPT's sources to see whether they support its claims.
- **Finds other evidence.** Searches beyond the links ChatGPT provides.
- **Checks individual claims.** Shows Supported, Partially Supported, Contradicted, or Unverified for each claim.
- **Shows its sources.** Provides relevant quotations and links you can inspect.
- **Works automatically.** When enabled, starts checking eligible responses after ChatGPT finishes answering.
- **Lets you check again.** Use **Re-verify** to run a fresh check.
- **Offers optional history.** Save past results locally in your browser.

VerifAI helps you review information. Its verdicts are not guaranteed to be correct.

## Installation

VerifAI isn't on the Chrome Web Store yet. You can install it from the release ZIP.

1. Download [verifai-0.1.19.zip](https://github.com/rjluteria/VerifAI/releases/download/v0.1.19/verifai-0.1.19.zip).
2. Extract the ZIP to a folder you can keep on your computer.
3. Open `chrome://extensions` in Chrome.
4. Turn on **Developer mode**, then click **Load unpacked**.
5. Select the extracted folder containing `manifest.json`.
6. Open VerifAI's **Settings** and click **Save settings**. Allow access to the hosted service if Chrome asks.
7. Open ChatGPT and switch **Enable verification** on in VerifAI's controls.

That's it. You don't need an API key, a local AI model, or your own server. VerifAI connects to its hosted backend.

Use the official ZIP without changing its files. It has a registered extension ID that the backend recognizes; users don't need to configure an allowlist. The ZIP contains no private API keys. If you want to check the download, use [SHA256SUMS from the release](https://github.com/rjluteria/VerifAI/releases/tag/v0.1.19).

## How to use it

1. Open ChatGPT and enable verification in VerifAI.
2. Ask a question that includes factual information.
3. Wait for ChatGPT to finish responding.
4. VerifAI starts checking the completed response.
5. Click **View details** to read the results and evidence.

Open the source links to check the evidence yourself. Click **Re-verify** if you want a fresh check of the same response.

### Understanding the results

| Result | What it means |
| --- | --- |
| **Supported** | The available evidence supports the claim. |
| **Partially Supported** | Some parts are supported, but other important parts aren't. |
| **Contradicted** | The available evidence conflicts with an important part of the claim. |
| **Unverified** | There isn't enough clear evidence to decide. |

**Unverified doesn't mean false.** A failed or incomplete check is shown separately, not treated as a verdict. Some responses have no factual claims that VerifAI can check.

## How it works

VerifAI uses a Chrome extension and a Python backend.

1. **Detect the response.** Wait for ChatGPT to finish answering.
2. **Find claims.** Identify factual statements that can be checked.
3. **Check citations.** Read the sources linked in the response.
4. **Find more evidence.** Search for other relevant sources online.
5. **Review the evidence.** Two fixed NVIDIA NIM AI reviewers assess the claims and sources.
6. **Check quotations.** Confirm that quoted text appears in the retrieved source.
7. **Show the results.** Display verdicts, progress, quotations, and links in Chrome.

Checking ChatGPT's citations and finding other evidence are separate steps. A matching keyword or a quotation appearing on a page doesn't automatically prove a claim is true. The models can still misunderstand the evidence.

### Technology used

| Part | Technology |
| --- | --- |
| Chrome extension | JavaScript, Manifest V3 |
| Backend | Python |
| AI reviewers | NVIDIA NIM |
| Hosting | Render |
| Tests | Python unittest, JavaScript tests |
| Build and CI | Docker, GitHub Actions |

API keys and model settings stay on the backend. See [ARCHITECTURE.md](ARCHITECTURE.md) for the technical design.

## Privacy and security

VerifAI checks supported ChatGPT pages when verification is enabled. It pauses automatically on unsupported sites and inactive tabs.

To run a check, the extension sends the response and its citations to the hosted backend. The backend sends search queries to discovery services and sends claims and evidence to NVIDIA's models. The extension doesn't contain provider API keys.

Saving verification history is optional. Saved history stays in your browser, and you can clear it in Settings. Temporary session results may still be available even when saved history is off.

The project includes safeguards for browser permissions, backend requests, source retrieval, and access to results. These reduce risk but cannot remove every security issue or prevent every prompt-injection attempt.

Read [PRIVACY.md](PRIVACY.md) and [SECURITY.md](SECURITY.md) for details.

## Known limitations

**Checks can take minutes.** The goal is 30 seconds, not a guaranteed finish time. Web searches, external models, unavailable sources, and free-host startup time can slow things down. Some recorded checks took more than two minutes. VerifAI shows progress rather than inventing a result when a check runs long.

**Results can be wrong.** The AI reviewers can misread a claim or its evidence. Even when both agree, the answer isn't guaranteed to be correct. Read the sources before relying on a verdict.

**Not every source is accessible.** Login requirements, blocked requests, changed pages, and unsupported formats can prevent a full check. VerifAI mainly works with text; complex tables, images, videos, and other media aren't reliably verified.

**Only ChatGPT is supported.** Other chatbots aren't included in this release.

**The hosted service is required.** If the backend, search service, or AI provider is unavailable, a check may fail or remain incomplete.

See [ACCEPTANCE.md](ACCEPTANCE.md) for recorded test results and timings.

## Settings and controls

- **Enable verification:** Turn automatic checking on or off. It starts off on a new installation.
- **Active / Paused:** VerifAI pauses when you leave an eligible active ChatGPT tab. There's no separate Pause button.
- **View details:** Open the results for a specific response.
- **Re-verify:** Start a fresh check. Previously saved results aren't new measurements.
- **Save local verification history:** Choose 24 hours, 7 days, 30 days, or until manually cleared. Turning saved history off clears saved history, though current session results may still be visible.

**Startup behavior:** In this version, verification can turn back on when Chrome restarts, even if you previously turned it off. Check the extension control after restarting Chrome if you don't want it enabled. Disabling the extension in Chrome stops it from running. Switching verification off prevents new submissions, but work already accepted by the backend may finish.

## Troubleshooting

| Problem | What to try |
| --- | --- |
| Verification doesn't start | Enable it, open an active ChatGPT tab, and wait for the response to finish. Check hosted-service permission in Settings. |
| VerifAI says Paused | Return to the supported tab and the response you want to inspect. |
| Backend connection fails | Check your connection and Chrome's permission to reach the hosted service. The operator manages server access and credentials. |
| A check takes a long time | Look at the progress display. Some checks take several minutes. |
| A source can't be opened | It may require a login, block automated access, or use an unsupported format. |
| A check fails or stops early | Try **Re-verify** after the service recovers. A failure is not the same as Unverified. |
| The panel shows another response | Click **View details** on the response you want to inspect. |

Refresh ChatGPT after reloading or updating the extension.

## For developers

The **Chrome extension** detects completed responses, manages controls and progress, and displays evidence. The **Python backend** handles sessions, source retrieval, model requests, evidence checks, and access to results.

### Run the tests

Use Python 3.14 and Node.js 24 or newer.

```bash
python -m unittest discover -s tests -v
npm ci
npm test
npm run format:check
```

To package the extension:

```bash
python scripts/package.py
```

The automated tests don't need an NVIDIA API key. Live verification uses credentials configured on the hosted backend. CI also runs the project's configured Ruff checks and Docker build.

### More documentation

- [Architecture](ARCHITECTURE.md) — How the extension and backend work.
- [Security](SECURITY.md) — Security measures and risks.
- [Privacy](PRIVACY.md) — What data is sent and saved.
- [Acceptance tests](ACCEPTANCE.md) — Recorded test results.
- [Changelog](CHANGELOG.md) — Changes between versions.
- [Release notes](RELEASE_NOTES.md) — What's in the release.
- [Release checklist](RELEASE_CHECKLIST.md) — Release checks.
- [Third-party notices](THIRD_PARTY_NOTICES.md) — Notices for third-party software.

## License

VerifAI is public to view but is not released under an open-source license. All rights are reserved.

Viewing the code on GitHub doesn't give permission to copy, change, redistribute, or use it commercially, except where allowed by law or GitHub's terms.
