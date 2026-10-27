# Validation / 2026-10-28

- Python syntax compilation and JavaScript syntax checks passed.
- 22 automated tests passed: CLI end-to-end workflow, optimistic revision guard, approval/budget gates, duplicate/timeout protection, project isolation and stale-tab protection, persistence, Wan3/Wan2.6/Seedance request contracts and status mapping, zero-request preview, paid gate, credential file isolation, permissions, error/log/database/export redaction. All provider transports mocked; keys used only in tests are fake.
- Browser integration uses temporary database/private storage: new project, editing isolation, switching back, reload selection, write-only fake-key UI, Wan3 request preview, paid button disabled, navigation, no season labels, responsive widths375/768/1440.
- FFmpeg6.0 + native arm64 FFprobe n4.4.1 installed into ~/.local/bin. Real synthetic 2-shot concat and SRT burn-in passed. ffprobe found H.264/AAC 640x360 with 2.045s duration. Synthetic material is not AI-generated. Stream-copy concat reported an AAC timestamp adjustment; complex media should be normalized first.
- No real provider authentication or generation, no purchase, no spending. ComfyUI live model generation not claimed.
- First source version published through the authenticated GitHub connector: main / ee7270cb9580524566b1e4eff265512457a1a63c. Local HTTPS Git lacks credentials; SSH unavailable; connector publication avoids extracting credentials.

Limits: no season or episode management; character snapshots via API rather than history viewer; no uploaded reference-image library; only image/text input for Wan3; no automatic result download, cancellation, unknown-task unlock, timeline mixer or actual billing reconciliation. Reference-image URLs and model output remain subject to vendor access and validation. No license selected.
