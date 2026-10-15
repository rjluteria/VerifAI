# Privacy

VerifAI 0.1.19 does not perform all verification locally. Enabling it permits the supported response/citation processing described here. Third parties and the service operator have their own policies; this project does not promise zero third-party retention.

## Data accessed and transmitted

On eligible active HTTPS ChatGPT pages, the content script reads completed assistant-response text and associated citation links for verification. It identifies responses/revisions to bind results to the correct response. It is not designed to upload the whole account, all chats or unrelated website content; response text can itself contain personal or confidential information. Do not treat the absence of a history save as absence of transmission.

The extension sends the selected assistant response, citation URLs and a response identifier to the configured hosted backend. The backend extracts claims, sends claim queries to the configured search service or encyclopedia fallback, fetches public evidence URLs, and sends claims/evidence to NVIDIA NIM for extraction/review and supported embedding ranking. Source sites see server-origin requests; they do not receive the user's browser cookies from this implementation. Render, NVIDIA, discovery providers, encyclopedia services and source websites can process request/network metadata under their own policies.

## Temporary and saved storage

The extension keeps operational state, signed-session tokens, pending jobs, response identity/URL information and cached results in browser session storage. This is separate from opt-in saved history. It can remain while history saving is Off, and clearing saved history does not clear every active session result.

The backend keeps jobs and results in process memory. Jobs have an expiry 30 minutes after creation; expired entries are removed during request cleanup and the roughly one-minute cleanup loop. Expiry is not a promise of immediate byte-level erasure. Restarting the service loses its process-local jobs. Signed anonymous sessions expire after 15 minutes; client renewal may preserve ownership. No persistent content database is implemented by this service. Hosting/provider systems may have separate storage/logging that these code-level limits do not control.

When **Save local verification history** is enabled, validated results are saved locally with a response ID/revision, claim text, verdicts, source/evidence details, save time and format version. This can reveal the substance of a conversation even though it is not a full-chat archive. Saved history is limited to the newest eligible 100 records and an approximately 1 MB serialized budget; storage failures are surfaced. It is not intended as encrypted confidential storage or browser-sync history.

## Retention and deletion

History is Off on a new installation. Enabling requires one of the implemented options:

| Setting | Eligible saved-history retention |
| --- | --- |
| 24 hours | Less than 24 hours from save time |
| 7 days | Less than 7 days from save time |
| 30 days | Less than 30 days from save time |
| Until manually cleared | No age expiry, subject to record/size limits and browser removal |

Pruning occurs when history is accessed or updated, not as a guaranteed exact-time secure-erase service. Invalid/future-dated entries are rejected. **Clear saved history** removes VerifAI's persisted history. Saving with history disabled clears that persisted history and stops future saving. Neither action retracts inputs already transmitted, cancels accepted remote work, clears every current session view, deletes unrelated browser data, or controls third-party retention. Browser uninstall/profile controls can remove extension storage under Chrome's behavior.

## User controls

Use **Enable verification** in the extension control to enable/disable current verification. A fresh installation starts Off. **On browser startup, a previously enabled installation reactivates verification even if it was Off before the restart.** Review the control after restarting; disable the extension through Chrome if automatic activation is unwanted. This existing restart behavior is not a promise that Off persists across browser startups.

The extension automatically pauses new eligible activity outside supported/active/owning response contexts. There is no separate manual Pause button. Returning to the correct ChatGPT response restores its view; already accepted external work may finish while paused or Off. Optional local history and its retention/clear controls are in Settings. Re-verify submits a fresh request; Cached results retain original verdicts, evidence and retrieval timestamps.

## Logging and operator responsibilities

The backend suppresses routine request logs and intentionally excludes content and credentials from its startup notice and sanitized errors. Optional causal/runtime diagnostics default Off. The application cannot promise that hosting infrastructure or external services retain no logs. Operators must configure their own secrets, access controls, surrounding logs and third-party terms appropriately, and users should assess those policies before sending sensitive response content.
