# Private release installation and rollback

Use the normal extension ZIP and matching private source archive listed in the
shipping report. Verify their SHA-256 values against the supplied `SHA256SUMS`.
Keep the repository private; this package does not publish to the Chrome Web Store.

## Server

The existing free hosted service can sleep when idle. Cold startup, retrieval and
provider delays can exceed 30 seconds. The application must keep displaying pending
or incomplete status rather than fabricate a completed result. Restarting the
single-process server discards its in-memory jobs; the client has bounded recovery.

## Chrome

Disabling verification stops new submissions; work already accepted by external
services may finish. History is opt-in and controlled through normal Settings.
Never load a diagnostic build as the normal distribution package.

## Rollback

For the existing deployment, the prior revision `21e7ddcfdce52c9e8bbaf6e17f3ab27e85717a0a`
and its private 0.1.18 artifacts are retained. Normal operational rollbacks do not
change permissions, repository visibility or the stored credentials.

