# Release checklist — VerifAI 0.1.19

Publication is not authorized by this checklist. Keep the repository private and stop for final user approval. The final report identifies exact commits, deployment, checksums, test counts and CI results; this checklist describes the verified scope and manual limits.

## Preparation

- [x] Preserve baseline verification/security architecture, model configuration, frozen gold and rollback artifacts.
- [x] Complete README, installation, architecture, security, privacy, configuration, changelog and release notes.
- [x] Default JSON example matches supported defaults; alternative uses distinct actual NVIDIA NIM IDs and is labeled experimental.
- [x] Add local schema/example/documentation contract tests; no inference needed for syntax validation.
- [x] No project LICENSE, software-rights grant or open-source claim added; third-party notices retained separately.
- [x] Tracked release tree excludes private outputs, keys, dependency caches and generated archives; .gitignore excludes normal local outputs.
- [x] Release packaging script validates the manifest and produces a flat extension ZIP with normal clocks Off.
- [x] Preserve historical failing accuracy/performance records; do not relabel them as passing.

## Functional evidence

- [x] Existing native Chrome installation upgraded/reloaded to functional 0.1.19 baseline; ChatGPT refresh and cached restoration observed.
- [x] Genuine fresh native Re-verify: release-preparation Mercury axial-59 returned Supported in UI-reported 85.8 seconds; prior axial-176 returned Contradicted in 158.9 seconds. Progress, continuing overrun and visible final evidence observed; not exact first-paint qualification.
- [x] Owner-bound side panel, source links and code-level unsupported-site/default-state/history/lifecycle behavior covered by current regression tests and retained native observations.
- [x] Latest retained hosted vitamin-D two-claim result matched both gold labels, with no incomplete claims; same reasoning pipeline, separately scoped prior live measurement.
- [ ] **MANUAL REQUIRED:** clean Chrome profile installation and service-origin approval, initial Off, enable/disable, unsupported-site pausing and side-panel operation. Existing-profile update and automated default/permission tests are not a clean-profile native install.
- [ ] **MANUAL REQUIRED:** native Settings history enable/retention/clear/disable in a clean profile. Earlier user-confirmed history setup/cleanup and deterministic tests are separately retained. Restricted extension controls were not accessed through a workaround.
- [ ] **NOT TESTED:** actual elapsed 24-hour/7-day/30-day retention; automatic tests exercise expiry logic.
- [ ] **NOT TESTED:** genuine worker-only suspension during a pending job; deterministic recovery and ordinary reloads are separate evidence.
- [ ] **MANUAL REQUIRED:** physical Windows Chrome and Docker Desktop acceptance; Windows CI is automated coverage only.

## Final validation and delivery

- [x] Backend and extension versions remain 0.1.19; no runtime/engine changes are required for release documentation.
- [x] Installation directions match manifest, flat package and actual Settings controls; operator allowlist/host-permission requirements are explicit.
- [x] Credentials, personal-path/private-artifact patterns and locally reachable Git history audited; synthetic test fixtures are adjudicated separately.
- [x] Dependency inventory/notices reviewed; runtime extension contains no vendored third-party JavaScript.
- [x] Existing fixed provider/retrieval/authentication and privacy defaults documented accurately, including browser-startup reactivation and transient caches.
- [ ] **FINAL REPORT:** Python/JS counts, lint/format, example validation, startup/Docker checks and final cross-platform CI result.
- [ ] **FINAL REPORT:** exact revision, backend deployment revision, final ZIP/source archive, package audit and verified SHA-256 checksums.
- [x] 30-second target and real latency/provider/source/cold-start limitations disclosed without fabricating success.
- [x] No repository-public, GitHub release, Chrome Web Store, permissions or paid infrastructure action authorized/performed.

The two FINAL REPORT rows are completed by the accompanying report after the final artifact/CI pass. Remaining manual checks must not be reported as passing or as confirmed defects. Publication requires explicit user approval even when preparation is ready.

