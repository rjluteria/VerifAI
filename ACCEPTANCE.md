# Acceptance status

Development build; release acceptance is incomplete. Results must be distinguished from synthetic fixture checks.

| Requirement | Implementation / measured status |
| --- | --- |
| Four claim statuses; Unverified distinct from false | Engine and UI implemented; local aggregation checks pass |
| Two evidence tracks and exact snippets | Implemented; five live extraction/search/fetch/classification cases matched expectations; quotations checked against text offsets |
| Citation accessibility | Every supplied citation checked; failures clearly labeled; Python and MDN pages opened in browser; universal user accessibility cannot be guaranteed |
| Hybrid models and fallback/degraded mode | Configurable NVIDIA reviewers; extraction fallback; incomplete or disagreeing review abstains; live model regressions recorded privately |
| Numerical grounding | Narrow deterministic operand/source grammar; ambiguous forms remain fallible model decisions, not generally proven arithmetic support |
| Request-local semantic retrieval | Implemented with lexical fallback; no persisted vectors |
| Chrome installation and default Off | Loaded unpacked in actual Chrome; default Off observed |
| Active eligible site only | Exact hosts and worker active-tab validation; policy and adapter fixture tests |
| Streaming, edits, identity and navigation | Revision guard and explicit completion/stability implemented; synthetic adapter checks; live current-site acceptance pending |
| Popup, settings, side panel and reverify | Implemented; first-install popup inspected; full hosted flow pending |
| History default Off, retention and clear | Implemented; policy tests; native retention/restart/quota acceptance pending |
| Source network security | Bounded DNS, public IP pinning, HTTPS, redirects, robots and limits; source requests and attack fixtures; independent audit pending |
| Sessions, payloads, abuse controls | Signed expiring sessions, owner-bound jobs, origin/schema limits; local HTTP and concurrency tests; distributed/load audit pending |
| Backend temporary retention/logging | Memory-only expiring jobs; no content/credential logs; actual Render infrastructure retention review pending |
| Docker | Local image built; runtime health/restart checks recorded privately |
| Windows and macOS | macOS local execution; portable scripts and three-OS CI definition; actual Windows and remote CI pending |
| Render deployment/recovery | Deployable blueprint prepared; account setup, real HTTPS/cold-start/recovery and origin integration pending |
| Build/package and public hygiene | Package generation and source audit; no repository publication or extension store release |

A perfect small benchmark must not be advertised as universal factual accuracy. Release requires current ChatGPT/Chrome integration, real hosted recovery/privacy review, actual cross-platform checks and a broader independent evaluation.
