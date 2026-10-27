# V1 validation / 2026-10-28

- Python syntax compilation: passed (3.9).
- JavaScript `node --check`: passed.
- Seven automated HTTP/backend tests with a temporary SQLite database: passed.
- Provider responses are mocked in tests. No real model job was submitted.
- Chromium: all six navigation pages loaded without JavaScript errors.
- Responsive overflow checks: passed at widths 375, 768 and 1440.
- Browser: script save produced the SQLite save confirmation.
- ComfyUI endpoints were checked against the local ComfyUI server implementation. A real connection or generation was not claimed.
- FFmpeg absent from PATH: actual media assembly not tested.
- Public repository creation was blocked by automatic approval review. No repository URL or remote push is claimed.

Known V1 limits: single local planning project, no episode switcher; character revision snapshots available through `/api/revisions` rather than a history viewer; no reference-image upload; output metadata only; no inline generated-media player; no video-node/provider implementation; no automatic billing reconciliation, task cancellation, unknown-task unlock, or timeline mixer.
