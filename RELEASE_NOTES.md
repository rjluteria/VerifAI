# VerifAI 0.1.19

Release preparation is complete only when the final release checklist/report records its tests and artifacts. Publication and repository visibility changes require separate approval. The project name is VerifAI.

## Overview

A Chrome extension for ChatGPT response verification with claim-level Supported, Partially Supported, Contradicted and Unverified results; separate citation/discovery tracks; exact quotations and provenance; an owning side panel; progress/stages/counts/elapsed/overrun handling; Re-verify and optional local history.

## Improvements

## Installation and configuration

Use Chrome 120+ and the normal `verifai-0.1.19.zip`; extract and Load unpacked from the folder containing `manifest.json`. The backend operator must allow the installation's exact extension ID and configure credentials; the user must grant the packaged service permission through Settings before enabling verification. A new installation starts Off, and history starts Off. Previously enabled installations reactivate verification on browser startup, including after Off; review the control after restart.

## Performance and known limitations

The release-preparation genuine fresh native Mercury check returned the expected Supported verdict for the 59-day claim with UI-reported 85.8 seconds. The prior 176-day claim returned the expected Contradicted verdict in 158.9 seconds. Browser results/progress were observed; observation timestamps and polling bounds were retained. This was not an exact first-paint or full warm/cold cohort qualification. Normal Cached results are separate from fresh verification.

The 30-second target is not guaranteed. Models, search, network/source access and free-host cold starts can require several minutes. A retained instrumented run had 229.401 of 253.939 seconds overlapping provider HTTP spans; this is network/service time, not exclusive GPU/LLM attribution. Provider HTTP 503s/timeouts and incorrect semantic judgments have occurred. Exact quotes and reviewer agreement do not guarantee truth. Inaccessible sources and failed reviews remain unavailable/inconclusive/incomplete; the overrun message does not fabricate a verdict.

Physical Windows Chrome/Docker, actual elapsed retention, genuine pending-worker suspension and clean-profile native control coverage are separately disclosed in [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). Automated tests do not substitute for unperformed native checks. No universal factual accuracy or guaranteed maximum time is claimed.

## Artifacts and rollback

## Rights and dependencies

No project software license is added. All rights are reserved by default; see the README license section. Third-party rights/notices remain separate in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

