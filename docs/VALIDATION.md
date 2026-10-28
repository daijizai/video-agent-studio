# Validation / 2026-10-28

## Ark adapter iteration

- 59 unit/HTTP tests passed, including 12 new Ark contract and persistence cases. New tests use fake credentials, temporary SQLite/assets and mock provider responses; no real Ark inference was submitted.
- `tests/browser_ark.py` passed: both new model choices persist; changing models does not resume a paused fixture; offline request preview works; synchronous image results appear without false quality approval; project isolation and 375/768/1440 layouts pass.
- Local port 8766 restarted and read-only checked: the existing project remains paused, new image/video execution is disabled, prior Qwen/Wan defaults remain, the accepted first-version film is preserved and its local MP4 serves HTTP 206 range playback.
- Seedance reference approvals use a versioned request binding; changed actual reference URLs require renewed approval for a new Ark request. Existing Wan approval hashes and film history are not rewritten.
- See `ARK_INTEGRATION.md` for pinned models, supported subset, reservation basis and real-generation validation limits.

- 47 automated tests passed: CLI workflows, project isolation, approval/budget gates, duplicate/timeout protection, optimistic revisions, official video/image payloads, static-frame prompt warnings, fixed project/database-bound generation scopes, credential isolation/redaction and task snapshots, named-shot finite extensions, and historical-image queries preserving the current image/approval.
- Browser polling integration passed with temporary SQLite/private storage and mock provider: immediate submitting/queued state; query failure and backoff; running/completed with a valid test image; no further provider queries at terminal/failed/no-ID unknown; independent collapsed details; unsaved edits preserved through polling and saved correctly; switching projects isolated; responsive375/768/1440.
- Browser workspace integration covers project create/edit/switch/reload, write-only fake-key UI, zero-network Wan3 preview and disabled video submission.
- Python/JavaScript syntax checks and Git secret scan passed. Real credentials remain outside repository; database, authorization file, private creative package, generated media and screenshots excluded.
- Official CLI1.10.0 and all14 discovered official QianWen skills installed and verified locally. Provider image submit/query/download has been exercised against the real service within explicit finite authorization. Generated artifacts and account-specific evidence are kept locally, not published.
- Real Prime minimum-resolution 30-second output was downloaded and technically verified for playable H.264 video and non-silent AAC audio. The user accepted the first version provisionally and paused further generation. This is not an objective guarantee of exact dialogue, voice identity or every prop metric. No extra ASR/TTS/visual model calls after the pause, no recharge/subscription purchase.
- FFmpeg6.0 and native arm64 FFprobe n4.4.1 installed. Synthetic concat/SRT test passed (H.264/AAC640x360,2.045s); stream-copy concat had an AAC timestamp adjustment, so normalize complex media first.

Limits: project-level workspace without season management; image-only reference input for video adapter; no full role-view asset library yet; no automatic cancellation/unknown-task unlock/billing reconciliation. Generated image quality still requires human review. No open-source license selected. Preview screenshots remain local per automatic approval review.

Video preview iteration: HTTP byte-range/open-ended/suffix/HEAD and invalid range/traversal/symlink tests passed. Synthetic H.264/AAC fixture verified native playback/pause/seek/volume, audio metadata, single/final selection, responsive layout and honest empty state; no generation calls and no real-project media inserted.

Image-preview iteration: local fixture browser test passed click-to-open, fit/original size, buttons/wheel and simulated two-touch zoom, current/history switching, Esc/button/backdrop close, keyboard focus trap/restore, retained expanded details and unsaved input, mobile viewport bounds, project isolation, and reclassifying an open old image as historical when a newer image arrives. No model submissions or external image transfer.

Separate-budget iteration: unit/HTTP/CLI and temporary browser tests passed independent caps, no borrowing, unknown/unsettled/inflight commitments, explicit source versions, persistence/project isolation, unchanged quality approval and budgeted explicit video redo. No model calls in tests.

Finalization: pure persisted-fact workflow tests cover preparation, image-only activity, valid approval, real queued/running/submitting tasks, failure/unknown, retry, stale approval rollback, old-video mismatch and provisional acceptance. Defaults/price tests cover Pro1K/2K and Prime480P/720P/1080P. Pause blocks image/video/local workflow submission while retaining budgets. Six browser suites passed, including persisted overview refresh/init rollback. Actual local fifth-page playback defaulted to the existing full film, returned Range206, sought successfully and retained progress with zero generation submissions.
