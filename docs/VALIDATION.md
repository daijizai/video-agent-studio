# Validation / 2026-10-28

- 32 automated tests passed: CLI workflows, project isolation, approval/budget gates, duplicate/timeout protection, optimistic revisions, official video/image payloads, static-frame prompt warnings, fixed project/database-bound generation scopes, credential isolation/redaction and task snapshots, named-shot finite extensions, and historical-image queries preserving the current image/approval.
- Browser polling integration passed with temporary SQLite/private storage and mock provider: immediate submitting/queued state; query failure and backoff; running/completed with a valid test image; no further provider queries at terminal/failed/no-ID unknown; independent collapsed details; unsaved edits preserved through polling and saved correctly; switching projects isolated; responsive375/768/1440.
- Browser workspace integration covers project create/edit/switch/reload, write-only fake-key UI, zero-network Wan3 preview and disabled video submission.
- Python/JavaScript syntax checks and Git secret scan passed. Real credentials remain outside repository; database, authorization file, private creative package, generated media and screenshots excluded.
- Official CLI1.10.0 and all14 discovered official QianWen skills installed and verified locally. Provider image submit/query/download has been exercised against the real service within explicit finite authorization. Generated artifacts and account-specific evidence are kept locally, not published.
- Wan3 audio capability was checked against official schema; no video quality/audio verification is claimed until a real reviewed video is generated. No recharge or subscription purchase.
- FFmpeg6.0 and native arm64 FFprobe n4.4.1 installed. Synthetic concat/SRT test passed (H.264/AAC640x360,2.045s); stream-copy concat had an AAC timestamp adjustment, so normalize complex media first.

Limits: project-level workspace without season management; image-only reference input for video adapter; no full role-view asset library yet; no automatic cancellation/unknown-task unlock/billing reconciliation. Generated image quality still requires human review. No open-source license selected. Preview screenshots remain local per automatic approval review.

Video preview iteration: HTTP byte-range/open-ended/suffix/HEAD and invalid range/traversal/symlink tests passed. Synthetic H.264/AAC fixture verified native playback/pause/seek/volume, audio metadata, single/final selection, responsive layout and honest empty state; no generation calls and no real-project media inserted.
