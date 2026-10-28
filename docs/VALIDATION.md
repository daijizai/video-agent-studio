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


## 2026-10-29 · AI素材资产库（角色＋物品）

- 主路径为故事/设定整理→AI独立母版→人工采用→必要视图→固定镜头引用；导入已有图片为补充。无新增场景分类，旧角色文字通过只读兼容投影保留。
- 接入真实Qwen异步、Seedream同步生成适配；素材任务有asset_id/kind/version/view，进入图片类别账本且无假shot_id。总费用先预占、提交意图先持久化，保留unknown锁、原任务查询、缓存恢复、模型范围与暂停门禁。未提交计划可取消释放预占。
- 镜头图片请求实际传入选中素材版本的原始像素，并保存规范化payload指纹/可复原清单/固定版本快照。新候选、新母版或采用版本不静默替换已批准镜头。
- 发布范围Python回归130项通过（排除另一工作线尚未发布的test_seedream_edit）；其中素材管理/生成/HTTP路由27项。规则JS10项通过，源码语法与diff检查通过。
- 新 browser_asset_library.py 全闭环通过：两类筛选、旧角色空态、暂停预览/禁用、Mock AI母版、人工采用前加载、独立视图/可选导入/历史、设定候选、固定镜头引用、重载隔离、手机/横屏布局和原生对话框Tab循环/Escape/焦点恢复。
- 原9组隔离浏览器回归通过：storyboard_public、storyboard_assist、workspace、ark、polling、lightbox、video、workflow、budgets。素材相关旧角色编辑测试改为新版本/人工采用流程，未绕过检查。
- 所有生成证明均为Mock/临时项目，不代表实际模型已出图；真实项目未提交任何素材生成。8766已更新并经实际页面只读核对：仍选中项目3《夜班清场》，两角色尚无图、素材任务0；项目2保持六镜有效审批与首版接受。重启前后所有项目body与授权文件指纹完全一致，两个实际项目仍暂停。截图留本机，不提交或上传私人素材。
- JPEG/WebP复用现有FFmpeg做受限解码；PNG标准库校验。无新pip包，无大模型下载或GPU租赁。规则与人工采用流程不保证模型绝不输出多格/身份偏差，需逐张审阅。

## 2026-10-29 · 三Skill交接的薄运行时合同

- 创作规范由主工作台独立发布的frame-screenplay/frame-character-assets/frame-object-assets承担；本轮只实现运行时数据消费与验证，没有改动/提交三个Skill、AGENTS、symlink或公共交接文件。
- asset_templates.py不猜脸型/服装、不解释Skill正文；校验Codex已交接设计、适用主体字段、当前视图描述、来源/版本与字节指纹、母版阶段、完整范围及实际模型映射。机械/动物等不强填人类属性，完整结构正面可作为身份基准。
- 缺交接时显示待制作助手准备，无机器参数表单；创作输入变化会使旧prompt待更新。母版不足、Skill/模板/公共合同变化、配方/实际参数变化均不能绕过新请求校验。历史真实任务/引用/首版不重写，未提交旧计划可取消后重新预览。
- 完整Python回归183项通过；规则JS10项、11组隔离浏览器回归通过。新测试Skill/交接全部生成在临时目录，模型均Mock，未新增真实生成请求。实际两个素材Skill的主文件/模板/公共交接字节合同另做只读核对，通过；没有宣称服务端已理解其创作语义。
- 8766已加载最终合同。重启前后所有项目body和仓库外授权文件指纹一致，当前选择仍为项目4；项目2六镜有效审批保留。当前项目仍暂停，素材生成任务0，设计交接未就绪时不会后台编造外观。
- 未验证真实图片的身份/几何/服装一致性；合同、模板及测试通过不等于视觉语义批准或恢复费用授权。
