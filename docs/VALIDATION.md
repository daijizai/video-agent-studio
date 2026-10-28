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


## 2026-10-29 · 故事审阅与独立开发者诊断

- 普通剧本/分镜/视频/设置视图移除机器规则表单、原提示与原始JSON；通过独立开发者诊断进入原工具，CLI/导出及数据库字段保留。
- 新增内部动作链/道具状态/参考用途契约、显式矛盾线索检查及版本化审批绑定。只读检查/反馈保存不改变审批；故事意图有效修改重新审阅，旧记录无批量迁移。
- `node --test tests/storyboard_checks.test.js`：10项通过。
- `python3 -m unittest discover -s tests -v`：当前共享工作区83项通过（含并行ComfyUI线未发布测试）；另经发布前独立复核，本次发布文件对应68项Python回归全部通过（排除并行ComfyUI线测试）。
- 两项新增隔离浏览器测试通过：普通流程无机器字段、隐藏数据保存无损、剧本/人物可编辑、自然语言反馈、审批不被预检更改、故事意图重载/项目隔离、键盘与375px/横屏布局；诊断表单另行验证选填字段/定位/保存及零提交。
- 现有 `browser_workspace.py`、`browser_polling.py`、`browser_lightbox.py`、`browser_ark.py`、`browser_video.py`、`browser_workflow.py`、`browser_budgets.py` 全部通过。API估价预览测试明确进入诊断；普通镜头编辑测试改用故事意图。Ark浏览器生成仅为隔离Mock，视频播放测试仅用临时合成测试素材，不访问实际项目或模型。
- 实际数据库只读核对：《明日失物所》6镜、6个有效审批、`COMPLETE`、`accepted_first_version`；没有启动8766、执行实际生成、写入或迁移实际SQLite。
- 规则是确定性文本/结构线索，不能检验真实画面或保证一致性；反馈不会自动触发模型、改写提示词或恢复已暂停生成。
