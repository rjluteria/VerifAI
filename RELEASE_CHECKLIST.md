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
- [ ] Fixed-model source deployed to the existing hosted service and fresh verification measured.
- [x] Extension ZIP, cleaned source archive and SHA256SUMS generated and validated after history cleanup; final revision/hashes appear in the accompanying report.
- [ ] Separate final publication approval obtained.

## Native checks and limitations

Prior existing-profile Chrome installation, side-panel/source access and fresh progress/overrun results are retained as historical evidence. They do not certify a new deployment. A fresh install starts Off and history starts Off according to automated regression coverage.

- [ ] **MANUAL REQUIRED:** clean-profile installation, service permission, initial Off, enable/disable, unsupported-site pause and side-panel operation.
- [ ] **MANUAL REQUIRED:** native history enable/retention/clear/disable; earlier user-confirmed controls are separate evidence.
- [ ] **NOT TESTED:** actual elapsed 24-hour/7-day/30-day retention.
- [ ] **NOT TESTED:** genuine worker-only suspension during a pending job.
- [ ] **MANUAL REQUIRED:** physical Windows Chrome/Docker Desktop acceptance; Windows CI is automated coverage only.

The 30-second healthy warm target is not a guaranteed maximum. Provider errors, incorrect model judgments, inaccessible sources and cold starts remain disclosed. Slow jobs continue visibly; neither errors nor overrun are fabricated successful verdicts.
