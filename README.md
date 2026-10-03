# VerifAI

VerifAI checks factual claims in completed ChatGPT responses against the response's citations and separately discovered web sources. It is a Chrome Manifest V3 extension with a Python REST service intended for Render.

This is a development build. A Supported result means retrieved evidence supports the assertion under the implemented checks. It does not guarantee factual truth. Unknown facts, unavailable sources, conflicting sources and reviewer disagreement remain Unverified. Unverified does not mean false.

## Setup

Requirements: Chrome 120 or newer, Python 3.14, Node 24 or newer, and Docker for container tests. Tooling supports Windows and macOS; Windows, macOS and Linux CI pass; native Windows Chrome acceptance remains pending.

1. Deploy this directory to Render with `render.yaml`, using the Docker runtime. Configure `NVIDIA_API_KEY`, `TAVILY_API_KEY`, and `ALLOWED_ORIGINS` in the dashboard. The blueprint generates the session secret. Do not put credentials in the extension or repository.
2. In Chrome's extension manager, enable developer mode and load `extension/` unpacked. Copy its ID into Render's `ALLOWED_ORIGINS` as `chrome-extension://ID`. An exact allowlist is required. Restart the service after updating environment settings.
3. In VerifAI Settings, enter the exact HTTPS Render service origin and approve access to that origin. Normal extension users never supply a NVIDIA key.
4. Enable verification in the popup. It starts Off on installation; after first enablement it starts On in new browser sessions. Switching Off survives worker and extension reloads and lasts until manual enablement or the next browser session.

The service does not automatically load `.env`. `.env.example` documents configuration names. Use deployment environment variables or export them securely in your local shell. Optional `ALLOW_KEYLESS_SEARCH=1` enables Tavily's limited development endpoint; it is off by default and is not a production capacity promise.

## Usage

Only the active eligible ChatGPT tab is processed. Responses need an identifiable assistant message, a recognized completion control and a stable revision. Unknown layouts fail closed. Each completed result has a View details button. The side panel shows claim statuses, separate ChatGPT Citation and Independent Sources sections, source access status, exact quotations and retrieval timestamps. Links open in new tabs. Re-verify retrieves fresh evidence and replaces the selected result. Opening a panel never starts another verification.

Queued recovery and Re-verify submit only while verification is enabled and the corresponding ChatGPT conversation is active. Changing conversations or turning verification Off pauses queued submissions. After three failed submissions, automatic retries stop; Re-verify can start another attempt.

Local history defaults Off. Enabling it requires 24 hours, 7 days, 30 days or manual retention. Saved history contains verification results; the raw submitted response is kept only in browser session storage. History is pruned on reads and periodically while Chrome runs. There is no separate history browser; reopen results from their corresponding response. Clearing saved history leaves current-session results available.

## Architecture

`extension/` contains the site adapter, session worker, popup, side panel and settings. `backend/verifai/` contains extraction, evidence retrieval, request-local ranking, classification, sessions and job handling. `tests/` covers the engine, request boundaries, real local HTTP, extension policy and synthetic DOM lifecycle. The service has no external Python dependencies.

The service extracts atomic claims in bounded paragraph groups, preserving exact response quotes. General discovery uses Tavily with Wikipedia search as a failure fallback. Search summaries are never treated as source evidence. Retrieved text is ranked lexically and optionally with request-local NVIDIA embeddings; vectors are not persisted. The default NVIDIA-hosted reviewers are `z-ai/glm-5.3-flash` and `openai/gpt-oss-20b`; `PRIMARY_MODEL` and `FALLBACK_MODEL` configure them server-side. Two configured reviewers must agree for a conclusive model verdict. Both must return exact evidence quotations. Invalid review schemas or quotations get one bounded repair attempt using the same evidence; still-invalid reviews abstain. Deterministic percentage checking accepts only bounded explicit operands and a narrow, unqualified source sentence. Arbitrary numerical prose remains model-reviewed and fallible.

Source retrieval uses public HTTPS only, bounded subprocess DNS resolution, validated IP pinning, TLS hostname verification, redirect revalidation, robots rules and response limits. Unsupported content types, login/challenge responses and inaccessible sources do not become supporting evidence. Accessibility is measured from the service at the recorded time; the user's region, network, browser login and later page changes can differ. Duplicate track membership is preserved without claiming publisher independence.

REST endpoints: `GET /health`, `POST /v1/session`, `POST /v1/verify`, `GET /v1/jobs/{id}`. Requests use exact origin validation, strict schemas, short-lived signed sessions, job ownership and layered in-memory limits. Origin is defense in depth, not proof of identity. The single-process limits and job store must not be mistaken for distributed controls. Capacity is two concurrent jobs; requests beyond capacity receive Retry-After. Extension polling survives worker suspension through session storage and alarms. A restarted service loses jobs; clients retry within a bounded recovery policy.

## Privacy and security

The extension requests content access only for the two exact ChatGPT hosts. Hosted service access is requested separately for one Render origin. Neither the extension nor source requests carry a permanent credential. Submitted assistant response text and citation URLs go to the service. NVIDIA receives extraction inputs and selected evidence; search providers receive individual claim queries. Do not use the development build on sensitive conversations.

The service stores job results temporarily in memory, deleting them after 30 minutes or on restart. Request text and source documents are request-local and are released when verification completes; a running request can retain them until completion. Application logs contain a startup message and no verification content, credentials or HTTP access logs. Render and third-party infrastructure have separate logging and retention policies; those account policies must be reviewed before release. No persistent vector database or backend history is used.

## Development and validation

```text
python -m unittest discover -s tests -v
npm ci
npm test
python scripts/package.py
docker build -t verifai .
```

Python can be invoked as `py -3` on Windows. The package script writes an installable extension ZIP under `dist/`. CI defines Linux, macOS and Windows checks and a container build. Publishing or merely defining that workflow does not establish that remote checks ran.

## Known limitations

Basic native ChatGPT completion, regeneration, edit, SPA conversation creation and extension-to-Render flow have been tested with synthetic content. Broader lifecycle, recovery and privacy acceptance remain release gates. Current selectors are conservative and may require updates. Simple rectangular tables preserve labels and captions; merged or ambiguous tables are marked Not Verifiable. Images, OCR, charts and general code execution are outside scope. Complex tables, footnotes, ambiguous units, cross-paragraph references and general derived quantities need further testing. Oversized unsplittable blocks and claims above the request budget are reported as unverified coverage. Conflicting sources are not resolved by popularity or source counts.

Agreement between two models can still be wrong. Exact quotations establish provenance, not entailment. A successful source request is not a promise that every user can access the page. See [acceptance status](ACCEPTANCE.md) for measured checks and remaining work. No software license has been selected.

Provider references: [NVIDIA API](https://docs.api.nvidia.com/nim/reference/llm-apis), [Tavily keyless access](https://docs.tavily.com/documentation/keyless), [Chrome side panel](https://developer.chrome.com/docs/extensions/reference/api/sidePanel), [Render Blueprints](https://render.com/docs/blueprint-spec).
