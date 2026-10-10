# VerifAI

VerifAI checks factual claims in completed ChatGPT responses against the response's citations and separately discovered web sources. It is a Chrome Manifest V3 extension with a Python REST service intended for Render.

This is a development build. A Supported result means retrieved evidence supports the assertion under the implemented checks. It does not guarantee factual truth. Unknown facts, unavailable sources, conflicting sources and reviewer disagreement remain Unverified. Unverified does not mean false.

VerifAI puts the evidence beside each assertion so readers can inspect what supports it, what conflicts with it, and what remains unresolved.

| Status              | Meaning                                                                                                              |
| ------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Supported           | Retrieved evidence supports all material assertions under the implemented checks.                                    |
| Partially Supported | Separable assertions include supported and missing parts, with no established contradiction.                         |
| Contradicted        | Evidence explicitly conflicts with a material assertion on the same grounded basis.                                  |
| Unverified          | Evidence is missing, ambiguous, inaccessible, conflicting, or cannot be reliably assessed. This does not mean false. |

Opinions and commands produce the small no-verifiable-claims state. Factual content with an unsupported structure is reported as Not Verifiable instead of being silently treated as verified.

## Setup

Requirements: Chrome 120 or newer, Python 3.14, Node 24 or newer, and Docker for container tests. Tooling supports Windows and macOS. The workflow covers Windows, macOS and Linux; a release candidate requires successful checks on its own revision. Native Windows Chrome acceptance remains pending; see [the minimal native procedure](WINDOWS_ACCEPTANCE.md).

1. Deploy this directory to Render with `render.yaml`, using the Docker runtime. Configure `NVIDIA_API_KEY`, `TAVILY_API_KEY`, and `ALLOWED_ORIGINS` in the dashboard. The blueprint generates the session secret. Do not put credentials in the extension or repository.
2. In Chrome's extension manager, enable developer mode and load `extension/` unpacked. Copy its ID into Render's `ALLOWED_ORIGINS` as `chrome-extension://ID`. An exact allowlist is required. Restart the service after updating environment settings.
3. In VerifAI Settings, enter the exact HTTPS Render service origin and approve access to that origin. Normal extension users never supply a NVIDIA key.
4. Enable verification in the popup. It starts Off on installation; after first enablement it starts On in new browser sessions. Switching Off survives worker and extension reloads and lasts until manual enablement or the next browser session.

The service does not automatically load `.env`. `.env.example` documents configuration names. Use deployment environment variables or export them securely in your local shell. Optional `ALLOW_KEYLESS_SEARCH=1` enables Tavily's limited development endpoint; it is off by default and is not a production capacity promise.

## Usage

The popup shows **Active** on an eligible ChatGPT page, **Paused** when enabled outside an eligible page, and **Off** when disabled. Only the active eligible ChatGPT tab is processed. Responses need an identifiable assistant message, a recognized completion control and a stable revision. Unknown layouts fail closed. Each completed result has a View details button. The side panel shows claim statuses, separate ChatGPT Citation and Independent Sources sections, source access status, exact quotations and retrieval timestamps. Links open in new tabs. Re-verify retrieves fresh evidence and replaces the selected result. Opening a panel never starts another verification.

Queued recovery and Re-verify submit only while verification is enabled and the corresponding ChatGPT conversation is active. Changing conversations or turning verification Off pauses queued submissions. After three failed submissions, automatic retries stop; Re-verify can start another attempt.

Local history defaults Off. Enabling it requires 24 hours, 7 days, 30 days or manual retention. Saved history is bounded to the newest 100 results and a 1 MB serialized budget, even with manual retention. Records exceeding capacity are omitted. Saved history contains verification results, including derived claims, assistant-response excerpts and source quotations. The separate submission payload and job/session credentials stay in browser session storage. History is pruned on reads and periodically while Chrome runs. There is no separate history browser; reopen results from their corresponding response. Clearing saved history leaves current-session results available.

## Architecture

`extension/` contains the site adapter, session worker, popup, side panel and settings. `backend/verifai/` contains extraction, evidence retrieval, request-local ranking, classification, sessions and job handling. `tests/` covers the engine, request boundaries, real local HTTP, extension policy and synthetic DOM lifecycle. The service has no external Python dependencies.

The service extracts atomic claims in bounded paragraph groups, preserving exact response quotes. General discovery expands the claim query with an additional official-source query, deduplicates the URLs, and uses Wikipedia search if discovery produces no usable URLs. Search summaries are never treated as source evidence. Retrieved text is ranked lexically and optionally with request-local NVIDIA embeddings; vectors are not persisted.

The default NVIDIA-hosted reviewers are `nvidia/nemotron-3-super-120b-a12b` and `poolside/laguna-xs-2.1`; `PRIMARY_MODEL` and `FALLBACK_MODEL` configure them server-side. A failed review can use `REVIEW_FALLBACK_MODEL` (default `openai/gpt-oss-20b`). Two distinct models must agree for a conclusive verdict; using the same standby twice never counts as two reviewers. Incomplete or disagreeing pairs get exactly one fresh reassessment with the same evidence and a neutral decision rubric. If both the original and reassessment rounds return only one valid review, matching labels from two distinct actual models can retain the original review: both assessed the identical claim and evidence. Duplicate identities, a differing label, or a complete disagreeing pair cannot use this recovery path. Persistent disagreement or unavailable distinct reviewers remains Unverified. For Supported or Contradicted, quotations come from one complete validated review set, selected by shortest total quote text. The displayed reason describes the evidence category without adding free-form measurements or facts; reviewer explanations remain in diagnostics rather than being presented as proof. Partial decisions retain complementary supported and missing-evidence quotations from both reviews. Both distinct reviews remain required for agreement; quotations are not intersected across reviewers. Reviewers select validated evidence IDs; the backend copies the original source text rather than asking a model to reproduce punctuation.

Invalid review schemas, evidence IDs or a Partial label with an affirmatively contradictory explanation get one bounded repair. Partial support requires two to eight separable assertions, checked through atomic extraction and individual assessments by the same reviewer. A valid Partial review must include supported and missing assertions with no contradicted assertion; inconsistent atomic assessments trigger one bounded repair of the whole review. Validated assertion structure is reused only within the same classification request. Each reviewer still assesses the original claim and each atomic assertion independently; the recorded parsing model is separate from the factual reviewer identity. The cache is discarded on completion or failure and isolated between concurrent requests. These dependent checks do not count as additional independent reviewers and can add latency. Complex decomposition or an exhausted validation budget fails closed. If that structural parser is unavailable, the standby may parse the claim while the valid factual review retains its original reviewer identity. The parser identity is recorded separately and does not count as another factual reviewer.

NVIDIA requests share process-local pacing, rate-limit cooldowns and bounded retries. Each model permits one in-flight chat call per process, so concurrent jobs queue for a shared reviewer while different reviewers can proceed independently. Queue acquisition is bounded to 125 seconds; a timeout follows the same attributed standby path as a provider error. Slots release on success and failure. One neutral reassessment waits once for an observed reviewer cooldown, bounded to 120 seconds. Fallback diagnostics preserve the failure reason.

Deterministic percentage checking accepts only bounded explicit operands and a narrow, unqualified source sentence. Closed observational-only and matching temporal-increase patterns abstain on unsupported causality. A matching one-sentence non-detection above a reporting limit cannot disprove an unqualified detection assertion. Additional findings, explicit bounded claims and other effects remain in factual review. A simple unspecified duration abstains rather than guessing battery runtime. An unqualified geographic size comparison backed solely by two population counts abstains rather than choosing population over area. Explicit metric definitions, direct comparisons and additional evidence stay in factual review. Compound assertions and evidence outside these narrow patterns remain model-reviewed and fallible.

Source retrieval uses public HTTPS only, bounded subprocess DNS resolution, validated IP pinning, TLS hostname verification, redirect revalidation, robots rules and response limits. An advertised Content-Length must match the completed response. Paragraph boundaries are retained; short documents are reviewed in full and longer passages retain sentence/block boundaries. Unsupported content types, login/challenge responses and inaccessible sources do not become supporting evidence. Accessibility is measured from the service at the recorded time; the user's region, network, browser login and later page changes can differ. Identical retrieved text is reviewed once per claim, preserves each URL’s attribution, and is marked as duplicate content. Independently discovered pages can still share an original publisher; source count never establishes independent corroboration.

REST endpoints: `GET /health`, `POST /v1/session`, `POST /v1/verify`, `GET /v1/jobs/{id}`. Requests use exact origin validation, strict schemas, short-lived signed sessions, job ownership and layered in-memory limits. Origin is defense in depth, not proof of identity. The single-process limits and job store must not be mistaken for distributed controls. Capacity is two concurrent jobs; requests beyond capacity receive Retry-After. The verification time budget is checked before claims, evidence review and queued source fetches; already running external calls retain their own bounded deadlines and can finish after the job budget. Extension polling survives worker suspension through session storage and alarms. Eligible foreground scans request a poll at most every five seconds; a 30-second alarm remains the recovery mechanism. A restarted service loses jobs; clients retry within a bounded recovery policy.

## Privacy and security

The extension requests content access only for the two exact ChatGPT hosts. Hosted service access is requested separately for one Render origin. Neither the extension nor source requests carry a permanent credential. Submitted assistant response text and citation URLs go to the service. NVIDIA receives extraction inputs and selected evidence; search providers receive individual claim queries. Do not use the development build on sensitive conversations.

The service stores job results temporarily in memory, deleting them after 30 minutes or on restart. Full request payloads and fetched source documents are request-local and are released when verification completes; a running request can retain them until completion. Stored job results still contain derived claims and response/source excerpts until expiry or restart. Application logs contain a startup message and no verification content, credentials or HTTP access logs. Render and third-party infrastructure have separate logging and retention policies; those Hobby application logs currently have a documented seven-day retention. The test dashboard showed startup and platform deployment messages and no verification content; this observation does not audit all provider-internal logging or prove deletion after seven days. No persistent vector database or backend history is used.

## Development and validation

```text
python -m unittest discover -s tests -v
npm ci
npm test
python scripts/package.py
docker build -t verifai .
```

Python can be invoked as `py -3` on Windows. The package script writes an installable extension ZIP under `dist/`. CI defines Linux, macOS and Windows checks and a container build. Publishing or merely defining that workflow does not establish that remote checks ran.

Optional model evaluation (requires a locally configured `NVIDIA_API_KEY`). Keep result files outside the repository; they contain full model reasons and are local evaluation artifacts:

```text
python scripts/evaluate_accuracy.py --output evidence-run.json
python scripts/evaluate_accuracy.py --dataset evaluations/historic-audited.json --output historic-run.json
python scripts/evaluate_accuracy.py --dataset evaluations/compatibility-controls.json --output compatibility-run.json
```

Ten separate numerical-bound controls distinguish interval compatibility from evidence for a specific point estimate. Run them with `--dataset evaluations/numerical-bounds.json`; they remain a separate cohort with results pending validation.

The broad evidence corpus covers 25 cases across different domains and metric-scope holdouts. The separate historic corpus retains 56 regression cases. Six supplemental currency/unit controls are a separate, partly overlapping cohort; do not sum them with the historic/broad total. These runs test supplied-evidence classification, not full extraction, live discovery, browser access or semantic quotation accuracy. Existing result files cannot be overwritten. The separate cohorts and audit rules are described in [the evaluation methodology](evaluations/METHODOLOGY.md). Gold-label corrections and preserved original-run distinctions are documented in `evaluations/GOLD_ADJUDICATION.md`. A perfect measured run is not a universal accuracy guarantee.

## Known limitations

Basic native ChatGPT completion, regeneration, edit, SPA conversation creation and extension-to-Render flow have been tested with synthetic content. Broader lifecycle, recovery and privacy acceptance remain release gates. Current selectors are conservative and may require updates. Simple rectangular tables preserve labels and captions; merged or ambiguous tables are marked Not Verifiable. Images, OCR, charts and general code execution are outside scope. Complex tables, footnotes, ambiguous units, cross-paragraph references and general derived quantities need further testing. Oversized unsplittable blocks and claims above the request budget are reported as unverified coverage. Conflicting sources are not resolved by popularity or source counts.

Agreement between two models can still be wrong. Exact quotations establish provenance, not entailment. A successful source request is not a promise that every user can access the page. See [acceptance status](ACCEPTANCE.md) for measured checks and remaining work. No software license has been selected.

Provider references: [NVIDIA API](https://docs.api.nvidia.com/nim/reference/llm-apis), [Tavily keyless access](https://docs.tavily.com/documentation/keyless), [Chrome side panel](https://developer.chrome.com/docs/extensions/reference/api/sidePanel), [Render Blueprints](https://render.com/docs/blueprint-spec).

Retesting found Chegg content readable to the service while its page denied access in the user-facing browser. Chegg URLs are conservatively excluded from proof and remain visible as restricted sources. This exclusion does not establish universal browser accessibility for other hosts.

Claim extraction rejects reconstructed or otherwise inexact quotations. Invalid schema or quotation output receives at most one repair attempt per model within the existing extraction time budget. Provider failures move to the next configured extractor; they do not trigger output repair. Returned quotations must still occur verbatim in the original response.

A closed, internally consistent count partition compares adult or juvenile counts with the matching subgroup, never the total. It requires the same stated subject and noun and a complete two-group source sentence. Qualifiers, conflicting totals, different entities and additional source findings stay in model review. The copied source sentence remains available as the numerical evidence.

Four separate [measurement-conflict controls](evaluations/measurement-conflicts.json) preserve unresolved-conflict, correction, shared-contradiction and unit-conversion boundaries. They supplement the frozen regression corpus; current provider validation remains pending.
