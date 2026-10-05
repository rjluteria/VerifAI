# Evaluation methodology

VerifAI's evaluations measure separate parts of the system. A percentage applies only to the named cohort and recorded run. Keep extraction, source categories, final verdicts, quotation provenance, semantic context and browser readability separate. Never add unrelated cohorts together to report a larger accuracy total.

## Supplied evidence

The public audited datasets contain 56 historic regression cases and 25 broad cases. Each case includes a claim, supplied evidence, expected category and rationale. Expected labels are fixed before model calls. Earlier adjudication and original failing-run distinctions are documented in [GOLD_ADJUDICATION.md](GOLD_ADJUDICATION.md).

Use `scripts/evaluate_accuracy.py` separately with each dataset and a configured NVIDIA key. Store outputs outside the repository. The runner refuses to overwrite a previous result, records the dataset digest and configured models, and checks each returned quotation against the supplied evidence. It uses the same classification code as the service. A correct category and exact quotation do not establish successful extraction, live retrieval or semantic quotation quality.

## Controlled pipeline

The separate controlled evaluation supplies complete response text to extraction and uses predetermined source documents and discovery URLs. Its 25 responses include two compound responses, requiring 27 atomic assertions. Both citation and independent-source tracks must preserve the expected category for every atomic assertion. Duplicate document text is a copy with separate URL attribution; it is not independent corroboration.

Count extraction failures and missing or extra atomic assertions as failures. Do not drop such responses from the denominator. Verify exact response quotes and source offsets. Review each selected quotation against the surrounding source text separately from automated offset checks.

## Fixed real-source snapshots

The fixed cohort contains 25 source-category records: four citation records and 21 independently discovered records. URLs and document snapshots were preserved from earlier retrieval. A rerun on these documents tests ranking and categorization, not current retrieval or fresh search. Inaccessible sources must remain Unverified without admitted proof. Multiple records can refer to one URL or document; records are not distinct sources.

## Fresh live verification

Fresh live runs perform new citation retrieval and independent discovery for four predetermined textual claims. Preserve the retrieved documents privately for exact offset and surrounding-context audits. Record retrieval time, availability, source identity and actual reviewers. Test new proof URLs in the native user-facing browser. A successful service fetch does not imply browser access, and a readable page does not imply entailment.

The small live cohort cannot establish universal factual correctness, long-term search reliability or population-level accuracy. Source availability and external model responses can change between runs.

## Browser, reliability and performance

Native browser tests use synthetic conversations and record actual inline results, panel selection, link navigation, lifecycle state and recovery. Synthetic DOM tests and Windows CI do not replace native Windows Chrome testing.

Fault tests exercise provider/network failures, unavailable reviewers, malformed outputs, missing evidence and injection attempts. Safe abstention is required; failures must not fabricate evidence or force a conclusive category. Fault-fixture success is distinct from observed hosted-provider recovery.

Private stage traces distinguish model calls, search, retrieval, ranking, retries, cooldowns, serialization and polling. Nested spans overlap and must not be added as independent costs. Compare the same workload where possible, disclose model/configuration differences and preserve rejected experiments. Percentiles from four cases are descriptive, not dependable production tail estimates. Docker probes with mocked models are resource tests, not factual-accuracy or hosted-load tests.

Full source text, private browser captures and development diagnostics are excluded from this repository. The public classification datasets and deterministic tests are reproducible here; the private controlled, snapshot, live and native acceptance artifacts are separate evidence with the limits described above. See [acceptance status](../ACCEPTANCE.md) for the measured revision and remaining gates.
