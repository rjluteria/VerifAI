# VerifAI

VerifAI is a Chrome extension that evaluates factual claims in AI-generated responses. It examines cited sources, retrieves independent evidence, and presents claim-level results with supporting quotations and source links. VerifAI currently supports ChatGPT. Its verdicts are evidence-based assessments, not guarantees of truth.

Version **0.1.19** connects to the existing hosted service at `https://verifai-ekan.onrender.com`. Two fixed NVIDIA NIM reviewers evaluate evidence. Users do not need API keys, model settings or infrastructure. The repository remains private until publication is approved.

## Features

- **Verification:** automatic completed-response detection, factual claim extraction, citation checks, independent evidence discovery, four claim verdicts, source quotations and links, and Re-verify.
- **Interface:** inline indicators; a side panel with evidence, stages, available claim/source counts and elapsed time; continuing-overrun messages; explicit retry, failure and incomplete-analysis states; separate Cached results.
- **Privacy and security:** verification controls, supported-page restrictions and automatic pausing outside eligible active pages, optional local history, backend-only provider credentials, input/evidence validation and signed-session result ownership.

## How VerifAI works

1. Detect a completed ChatGPT assistant response and identify its associated citations.
2. Extract factual assertions while retaining qualifiers and exact response quotations.
3. Retrieve cited pages and search for independent evidence using claim queries.
4. Acquire supported public source text and select relevant passages.
5. Have the fixed NVIDIA NIM reviewers assess the claims and select exact evidence quotations.
6. Validate quotation positions/provenance and assemble verdicts from the source assessments.
7. Display results, progress and supporting evidence beside the response.

Citation verification and independent discovery are **separate tracks**. Search snippets and matching keywords are not proof. Independently discovered pages can share an original source; counting pages does not establish independent corroboration. Model agreement and exact quotations do not prove semantic correctness.

## Verification statuses

| Status | Meaning |
| --- | --- |
| Supported | Available evidence supports the evaluated claim under the implemented checks. |
| Partially Supported | Evidence supports separable parts while other material parts remain unsupported; established contradiction is not counted as partial support. |
| Contradicted | Available evidence conflicts with a material assertion on the same evaluated basis. |
| Unverified | Evidence is insufficient, ambiguous, inaccessible, conflicting or disputed by reviewers. |

Unverified does not mean false. An execution failure or incomplete analysis is shown separately and is not a successful factual determination. Opinions and commands can have no verifiable claims; unsupported factual structures can be reported as Not Verifiable.

## Installation

The normal ZIP is a flat extension package: `manifest.json` and the other extension files are at the archive root. It contains no backend or credentials.

1. Download `verifai-0.1.19.zip` from the approved release distribution and verify `SHA256SUMS`. Until publication is approved, use the privately supplied artifacts.
2. Extract the ZIP into a stable folder.
3. Open `chrome://extensions` in Chrome 120 or newer.
4. Enable **Developer mode** and select **Load unpacked**.
5. Select the extracted folder containing `manifest.json`; confirm version 0.1.19.
6. Have the service operator allow this installation's exact extension origin. Each installation/profile may have a different extension ID. The operator sets `ALLOWED_ORIGINS=chrome-extension://YOUR_EXTENSION_ID`; multiple origins are comma-separated. Settings displays the installation's service origin identifier.
7. Open VerifAI's **Settings**, leave history Off initially, and select **Save settings**. Approve access to the configured hosted service when Chrome prompts. Missing host permission or a missing server allowlist entry prevents connection; the ZIP cannot preauthorize a new installation.
8. Open ChatGPT, sign in normally if needed, and open VerifAI's control. Turn **Enable verification** On. It starts Off on a new installation.
9. Ask ChatGPT for a response containing factual claims. VerifAI checks eligible completed assistant responses while the supported tab is active.
10. Select **View details** to inspect results and evidence. Use **Re-verify** for an existing result when a fresh run is needed.

## Usage

- **Enable/disable:** use **Enable verification** in the extension control. Off prevents new submissions; already accepted external work may finish. A new installation starts Off. On browser startup, a previously enabled installation reactivates verification, including after a prior Off selection; review the control after restarting Chrome. Disabling the extension in Chrome prevents that activation.
- **Active/Paused:** with verification enabled, eligible HTTPS ChatGPT pages can be Active. Unsupported sites, inactive tabs or a response that no longer owns the panel pause/hide its verification view. Return to the owning ChatGPT response to resume viewing. Pausing is automatic; there is no separate manual Pause button.
- **Progress:** the inline indicator and side panel show actual verification stages, elapsed time and available counts. Beyond the 30-second target, the application continues rather than manufacturing a verdict.
- **Evidence:** select **View details**, inspect each claim's citation and discovery tracks, read the quotations/retrieval information, and open source links. Unsupported sources have no supporting quotations.
- **Re-verify:** starts a fresh job for the displayed owning response. Cached results retain their original evidence and timestamps; they are not fresh verification measurements.
- **History:** Settings → choose retention → enable **Save local verification history** → **Save settings**. Options are 24 hours, 7 days, 30 days, or Until manually cleared. **Clear saved history** removes saved local history. Saving history Off clears that saved history and stops future saving; session results can still remain visible. See [PRIVACY.md](PRIVACY.md).
- **Failures:** read the displayed failure/incomplete message, confirm connectivity and permissions, and retry using Re-verify when the provider/service recovers. An Unverified label alone is not proof of a transport failure or proof that a claim is false.

## Architecture

The Manifest V3 extension handles response capture, owner-bound state, progress and evidence presentation. The Python backend manages signed sessions and bounded in-memory jobs, acquires public evidence and invokes fixed NVIDIA NIM reviewers. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Limitations and performance

The target is 30 seconds for healthy, warm, fresh verification; it is not a guarantee. External models, search, retrieval and free-host cold starts can make a verification take several minutes. Final hosted Mercury checks returned the expected Supported verdict in 146.340 seconds before obsolete-setting removal and 29.860 seconds afterward. A separate fresh native Chrome Re-verify returned Supported with UI-reported 97.2 seconds and correct continuing-overrun behavior. These are individual measurements, not a warm/cold cohort or exact first-paint qualification; they do not establish that removing unused settings caused a speedup.

Models can make incorrect judgments, including confusing two measurement properties despite relevant evidence. Sources can be unavailable, incomplete, region-restricted, login-dependent or later changed. A source accessible to the backend may differ from what a browser can access. Complex tables, media and arbitrary code execution are outside supported text verification. Results must be reviewed alongside the evidence. No universal accuracy or maximum-latency claim is made. Historical acceptance evidence is preserved in [ACCEPTANCE.md](ACCEPTANCE.md).

## Security and privacy

Provider credentials stay server-side. Restricted permissions, signed-session ownership, bounded validated requests, public-source retrieval controls and exact quotation provenance reduce risk; they do not eliminate model error or prompt injection. Verification sends response content/citations to the backend, claim queries to discovery services and claims/evidence to NVIDIA. Optional local history is not the only temporary storage. See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md).

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Verification does not start | Enable verification, grant service access in Settings, confirm the server allowlists this extension ID, activate a supported ChatGPT tab and wait for the assistant response to finish. Refresh ChatGPT after updating/reloading the extension. |
| Remains Paused | Return to the supported active tab and owning response. Off must be switched On through the normal control. Unsupported websites never activate verification. |
| Backend connection failure | Check permissions, allowlisted origin, `/health`, network and free-host wake-up. Only the operator can fix service credentials. |
| Long verification | Inspect actual progress; the 30-second target is not a timeout that fabricates a verdict. Provider timeouts/retries and source acquisition can take minutes. |
| Source unavailable | Inspect the unavailable entry. Login/challenges/unsupported content cannot be bypassed or used as proof. Other accessible sources may still be checked. |
| Provider error/incomplete analysis | The operator checks provider availability and service limits. Retry after recovery; unavailable source evidence cannot establish support. |
| Side panel belongs to another response | Select View details on the intended response; return to its owning tab before using Re-verify. |

## Development and release checks

Python 3.14 runs the standard-library backend/tests; Node.js 24+ runs the JavaScript tests and formatter. Use `python -m unittest discover -s tests -v`, `npm ci`, `npm test`, `npm run format:check`, and the configured Ruff checks. `python scripts/package.py` creates the normal ZIP. CI also builds the pinned Docker image on the current workflow. No provider key is needed for deterministic tests. Live verification uses credentials held by the hosted service.

See [CHANGELOG.md](CHANGELOG.md), [RELEASE_NOTES.md](RELEASE_NOTES.md), [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Manual and automated checks are distinguished; a checklist's unperformed item is not a passing native test.

## License

VerifAI is distributed without an open-source software license. All rights are reserved by default.

Public availability of the source code does not grant permission to copy, modify, redistribute, or commercially use the software beyond permissions provided by applicable law or the hosting platform's terms.

