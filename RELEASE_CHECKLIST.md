# Release checklist — VerifAI 0.1.19

The repository stays private. History cleanup was authorized and verified; publication requires separate owner approval.

## Local preparation

- [x] Fixed NVIDIA NIM reviewers, hosted endpoint and server-only credentials restored.
- [x] Verification prompts, retrieval, exact quotations, provenance, reviewer disagreement and incomplete-analysis safeguards preserved.
- [x] Progress, elapsed/overrun handling, owner-bound Re-verify, history and restricted permissions preserved.
- [x] Installation, architecture, security, privacy, changelog and release notes describe the fixed service.
- [x] No project LICENSE or rights grant added; third-party notices retained.
- [x] Local validation: 193 Python and 99 JavaScript tests, Ruff/Prettier, Docker build/secure startup, packaging and bounded secret/history audits passed.

## Delivery status

- [x] Owner authorized history cleanup; only the affected release branch was rewritten.
- [x] Remote history replaced and verified from a fresh clone; unrelated branches remain intact.
- [x] Cleaned implementation passed Linux, macOS, Windows and container CI; the accompanying report identifies the final documentation revision and its CI.
- [x] Tested fixed-model source deployed to the existing free service; real hosted verification passed before and after removing obsolete settings (146.340 s and 29.860 s). Credentials, session secrets, permissions and plan were not changed.
- [x] Fresh native Chrome Re-verify returned the expected Supported verdict in UI-reported 97.2 s; progress and continuing overrun were observed. Both supporting source destinations opened with the relevant text.
- [x] Seven explicitly approved obsolete CI runs were deleted and verified absent; retained old host caches are disclosed separately.
- [x] Extension ZIP, cleaned source archive and SHA256SUMS generated and validated after history cleanup; final revision/hashes appear in the accompanying report.
- [ ] Separate final publication approval obtained.

## Native checks and limitations

Existing-profile Chrome restored Cached results after reopening ChatGPT. A new Re-verify then exercised the cleaned hosted deployment, including side-panel ownership, progress/elapsed/overrun, correct final verdict and supporting links. This is distinct from a clean-profile installation. A fresh install starts Off and history starts Off according to automated regression coverage.

- [ ] **MANUAL REQUIRED:** clean-profile installation, service permission, initial Off, enable/disable, unsupported-site pause and side-panel operation.
- [ ] **MANUAL REQUIRED:** native history enable/retention/clear/disable; earlier user-confirmed controls are separate evidence.
- [ ] **NOT TESTED:** actual elapsed 24-hour/7-day/30-day retention.
- [ ] **NOT TESTED:** genuine worker-only suspension during a pending job.
- [ ] **MANUAL REQUIRED:** physical Windows Chrome/Docker Desktop acceptance; Windows CI is automated coverage only.

The 30-second healthy warm target is not a guaranteed maximum. Provider errors, incorrect model judgments, inaccessible sources and cold starts remain disclosed. Slow jobs continue visibly; neither errors nor overrun are fabricated successful verdicts.
