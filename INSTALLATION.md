# Installation and rollback

VerifAI 0.1.19 uses the existing hosted backend. Users do not obtain API keys, select models, edit source or run infrastructure.

## Install in Chrome

1. Obtain the approved `verifai-0.1.19.zip` and verify its SHA-256 against `SHA256SUMS`.
2. Extract the ZIP into a stable folder. The archive is flat: `manifest.json` is at its root.
3. Open `chrome://extensions` in Chrome 120+, enable Developer mode and select **Load unpacked**.
4. Select the extracted folder containing `manifest.json` and confirm version 0.1.19.
5. Confirm the official package ID is `klpailadffhphldajafnenkidikkfpan`. The packaged public identity keeps this ID consistent across folders/profiles. The hosted service authorizes this exact origin once; users do not request backend access or edit server settings.
6. Open VerifAI Settings, keep history Off initially, save and approve Chrome's requested access to the existing hosted service.
7. Open ChatGPT, sign in normally and enable verification through VerifAI's control. A new installation starts Off.
8. Ask for a response containing factual claims. Select **View details** to inspect progress, verdicts, quotations and source links. **Re-verify** starts a fresh check; Cached results retain their original evidence.

For updates, replace files in the same stable folder, reload the extension in Chrome's Extensions manager and refresh ChatGPT. Keep the path stable to preserve its unpacked identity.

## Use and failure handling

The hosted service is `https://verifai-ekan.onrender.com`. No user endpoint or credential setting is required. Unsupported or inactive pages automatically pause verification. Off prevents new submissions; accepted external work may finish. Previously enabled installations can reactivate at browser startup; review the control after restarting.

History is optional in Settings, with 24-hour, 7-day, 30-day or manual retention. Save history Off to stop saving and clear saved history; **Clear saved history** clears saved records. Temporary session results are separate. See PRIVACY.md.

The healthy warm target is 30 seconds, not a timeout. Provider, search and free-host wake-up delays can take minutes. Slow jobs continue visibly; failures and incomplete analysis are not factual support. Inspect evidence and retry after recovery.

## Operator maintenance

The existing service retains server-side NVIDIA_API_KEY, SESSION_SECRET and optional discovery credentials. Preserve the existing origin allowlist, session checks and other security controls. The pinned Dockerfile builds and starts without a separate model file. A restart discards in-memory jobs. Keep diagnostics disabled for normal use. Do not place secrets in Git, extension files, logs or archives.

## Rollback

Use an approved fixed-model source revision from the cleaned release history and its matching extension package. Redeploy the existing service with its existing secret-store values; never restore an abandoned implementation. Restore extension files in the same folder, reload and refresh ChatGPT. Confirm `/health`, then enable verification normally and run a synthetic fresh Re-verify. A cached result does not establish backend recovery. Publication and remote history changes require separate owner approval.

## Package identity

The manifest contains a public identity value, not a secret/API credential. It fixes the official unpacked package ID across installations. The backend continues to allow only explicitly registered origins and signed owner-bound sessions; it does not accept arbitrary extension IDs or websites. A future Chrome Web Store distribution must be checked against its assigned identity before publication.
