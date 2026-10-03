# Acceptance status

Development build; release acceptance is incomplete. Accuracy hardening measured 80/80 supplied-evidence decisions, 26/26 atomic claims from 24 diverse controlled full-pipeline responses, 25/25 real-source snapshot decisions (citation 4/4; independently discovered 21/21), and 4/4 fresh live claim verdicts. These are bounded measured results, not universal accuracy. The separate semantic and user-browser accessibility audit is recorded in the private hardening report. Final packaging/deployment checks are recorded there; controlled retrieval, source snapshots and fresh live retrieval are distinct scopes.

| Requirement | Implementation / measured status |
| --- | --- |
| Four claim statuses; Unverified distinct from false | Engine and UI implemented; local aggregation checks pass |
| Two evidence tracks and exact snippets | Implemented; exact candidate IDs copied from evidence; separate semantic/context review; inaccessible and incomplete sources cannot establish proof |
| Citation accessibility | Every supplied citation checked; failures clearly labeled; Python and MDN pages opened in browser; universal user accessibility cannot be guaranteed |
| Hybrid models and fallback/degraded mode | Configurable NVIDIA reviewers; extraction fallback; actual distinct reviewer identities required; bounded standby and one neutral reassessment; persistent incomplete or disagreeing review abstains; live regressions preserved privately |
| Numerical grounding | Narrow deterministic operand/source grammar; ambiguous forms remain fallible model decisions, not generally proven arithmetic support |
| Request-local semantic retrieval | Implemented with lexical fallback; no persisted vectors |
| Chrome installation and default Off | Loaded unpacked in actual Chrome; default Off observed |
| Active eligible site only | Exact hosts, captured conversation URL and worker active-tab validation; queued submission race regressions; native Off/Active/Paused and Off reverify refusal observed |
| Streaming, edits, identity and navigation | Revision guard and explicit completion/stability implemented; native completed prose/citation, regeneration, edited false assertion and newly created SPA conversation observed; broader lifecycle acceptance pending |
| Popup, settings, side panel and reverify | Implemented; first-install popup and settings inspected; native inline details, both evidence tracks, hosted result, panel remains closed and fresh reverify observed |
| History default Off, retention and clear | Implemented; policy tests; native retention/restart/quota acceptance pending |
| Source network security | Bounded DNS, public IP pinning, HTTPS, redirects, robots and limits; source requests and attack fixtures; independent audit pending |
| Sessions, payloads, abuse controls | Signed expiring sessions, owner-bound jobs, origin/schema limits; local HTTP and concurrency tests; distributed/load audit pending |
| Backend temporary retention/logging | Memory-only expiring jobs; no content/credential logs; actual Render infrastructure retention review pending |
| Docker | Local image built; runtime health/restart checks recorded privately |
| Windows and macOS | macOS local execution; portable scripts and three-OS CI definition; Windows, macOS and Linux CI passed; native Windows Chrome acceptance pending |
| Render deployment/recovery | Free HTTPS service deployed with auto-deploy Off; boundary and post-restart checks passed; native extension polling and two hosted synthetic claim cases passed with development search enabled; idle cold-start outage duration remains unmeasured |
| Build/package and public hygiene | Package generation and source audit; private repository and CI established; no public repository or extension store release |

A perfect small benchmark must not be advertised as universal factual accuracy. Release requires current ChatGPT/Chrome integration, real hosted recovery/privacy review, actual cross-platform checks and a broader independent evaluation.
