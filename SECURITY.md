# Security

This document describes implemented controls in VerifAI 0.1.19, not an exhaustive security certification. The repository and release candidate remain private until approved. See [PRIVACY.md](PRIVACY.md) for transmitted/stored data and [ARCHITECTURE.md](ARCHITECTURE.md) for boundaries.

## Extension permissions and ownership

The manifest requests `storage`, `sidePanel` and `alarms`, content-script access only to supported ChatGPT hosts, and optional access to the configured hosted service. It does not request all sites, browsing history or provider keys. The worker validates sender, active tab, eligible HTTPS URL, response revision and displayed run. Unsupported pages pause verification. Trusted-context session storage limits content-script access to signed-session state. A new installation starts Off; browser startup reactivates an installation that was previously enabled. Review the control after restart; disabling the extension in Chrome prevents automatic activity.

## API boundary

The service validates exact allowed extension origins, strict request schemas, input sizes and short-lived signed anonymous sessions. Job ownership is checked before and after a completion wait. Origin headers can be forged by non-browser clients; they are defense in depth, not authentication or a user identity. Sessions are anonymous capabilities, not accounts. Layered in-memory rate limits, HTTP limits and two-job capacity bound one process; horizontal deployments would need separately designed shared controls.

## Source and provider requests

Public evidence retrieval allows supported HTTPS destinations with global IP checks, bounded subprocess DNS, IP pinning, TLS verification, redirect destination/robots revalidation and bounded response type/size/time. Local/private destinations, unsupported responses and challenges are not supporting evidence. Public source requests do not carry browser cookies or model/search credentials. These checks reduce SSRF/rebinding risk; they do not guarantee every third-party page is safe or accurate.

## Prompt and evidence controls

Assistant responses, search results and retrieved text are untrusted data. Code owns extraction/review prompts and schema checks. Search snippets are not proof; exact source quotations, offsets/hashes and distinct reviewer identities are validated. Injection controls and regression tests reduce risk but cannot eliminate prompt injection or semantic model error. A correct substring can still be irrelevant to a claim. Missing/failed evidence is not fabricated into success; failed reviews remain incomplete or inconclusive.

## Storage and logging

Optional history is Off on installation, requires retention selection, and is bounded/pruned. Disabling history through Save settings clears persisted history; Clear saved history affects only VerifAI's saved history. Session results and already accepted server work can remain. Browser storage is not a dedicated encrypted secrets vault. Do not verify confidential material unless the operator's service/provider processing is acceptable.

The backend suppresses routine HTTP request logging and prints a content-free startup notice. Normal responses/errors omit raw provider diagnostics and credentials. Optional diagnostics are Off by default; hosting/reverse-proxy/provider logging is outside this code's control. The operator must protect environment secrets and avoid enabling content/debug logging in surrounding infrastructure.

## Reporting a vulnerability

No dedicated security email or private vulnerability-reporting service is configured by this repository. Do not invent an address, publish a secret in a public issue, or attach private ChatGPT content. Use an existing private contact with the repository owner to agree on a confidential reporting channel first. If no such channel is available, ask the owner for one without disclosing exploit details or sensitive data. Reports can identify the affected version, sanitized reproduction and impact once a private channel is agreed.

Do not rotate credentials, rewrite history, change permissions or publish an advisory automatically. A suspected exposed credential requires owner review. The release audit checks current files, packages and locally reachable Git history for known patterns; that bounded scan is not proof that no secret can exist.

