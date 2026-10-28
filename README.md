# Frame Studio / 视频制作 Agent 工作台

以 Codex 为制作中枢的本地 AI 短剧工作台。HTML/JS 网页负责可视化制作；Python + SQLite 管理项目、角色版本、分镜、任务与预算；ComfyUI 执行本机工作流；**默认图片Qwen Image3.0 Pro、视频Wan3.0-Video-Prime，标准版保留可选**；FFmpeg 做成片拼接与字幕。

## 运行

Python 3.9+，应用无 pip 或 npm 依赖：

```sh
python3 server.py
# 默认端口被占用时：
PORT=8766 python3 server.py
```

打开 http://127.0.0.1:8765 或 http://127.0.0.1:8766 。交付预览使用 8766。服务仅监听 loopback，适合单人本机使用；没有多用户认证，不应暴露公网。

## 已实现

- 新增可选 **火山方舟 Seedance 2.5 / Seedream 5.0 Flash** 接入：前台与 CLI 共用适配，支持视频异步任务及图片同步单图。保留现有默认、暂停与历史。详见[接入范围、预算和验证边界](docs/ARK_INTEGRATION.md)；当前只完成离线与模拟验证，不宣称真实生成已通过。

- 顶部**工作空间 / 项目选择 / 新建项目**；当前选择持久化，刷新恢复。各项目的剧本、角色、分镜、检查、任务、配置与预算独立保存。没有季管理。
- 保留《雾港来信》示例；新项目为空白且不标作示例。**首个 Demo 目标为30秒**，与Wan3单次最长30秒对齐。源码示例四镜头共27秒，仅是演示草案，不代表本机另行导入的真实制作项目或已交付媒体。此目标只针对首个Demo，长期系列仍支持1–3分钟、上限5分钟，通过多个镜头任务拼接。
- 六个普通制作页面：制作总览、剧本、角色资产库、分镜工作台、视频制作与预览、工具与设置。机器提示词、连续性手册、参考URL、请求JSON和ComfyUI工作流移至设置内独立的“开发者诊断”；版本审计也从此进入。原数据、导出和CLI保留。
- 角色设定版本快照、分镜逐镜确认、参考图 URL、检查记录和当前项目 JSON 导出。创作导入记录来源文件/哈希/时间；每次保存有版本快照，真实任务绑定内容版本、实际请求与来源。
- 点击已下载分镜图可放大：适应窗口/原尺寸、按钮/滚轮/双指缩放、键盘与焦点管理；当前图/历史图明确区分。打开预览不生成、不外传图片，也不清空正在编辑的详情。
- 图片优先的分镜卡片：Qwen Image3.0生成/参考图编辑，完成下载本机；上方保留图片、任务状态和关键操作，详细文字默认独立折叠。单幅模板、时序预检和失败经验均保留，任务完成与质量批准分开。
- 自动只查原图片/视频任务：8秒查询、错误退避至60秒、隐藏页30秒、每任务最多90次；终态停止查供应商。刷新/切项目后恢复，保留展开状态和未保存输入。无任务ID unknown不自动重提。
- 总览由 `workflow_state.py` 纯函数统一推导有效当前审批、真实任务和人类视频审核；不手改阶段，不把图片完成当视频完成，修改内容会使旧审批失效。
- Wan3/Prime 官方请求构建、图片参考/纯文本模式、异步提交与查询、状态归一化。输入使用 `media`，不会套用旧版 `reference_urls`。另保留 Wan2.6/Seedance 对照适配；可灵仅调研。
- 网页可零请求预览 payload 与估价。分镜审批、预算预占、提交前持久化、供应商任务编号和 unknown 锁定防止重复提交。**本地UUID不等于供应商幂等保证**。
- ComfyUI 本机连接检测、基础内置图像节点工作流提交与查询；任意付费/自定义节点仍被拦截。
- 第05页以原生HTML视频播放器为主体，单镜和整片可选；支持播放/暂停、seek、音量，真实视频缺失时显示空态。原始图片/视频账本在独立开发者诊断；普通页面保留播放、状态、费用与反馈，预览不触发生成。后端本地媒体支持安全路径、Range/HEAD与正确MIME。
- FFmpeg 拼接与可选 SRT 烧录脚本。本次已安装本机 FFmpeg/FFprobe，实际通过合成素材验证；二进制不随仓库分发。

## 故事意图与内部一致性

普通用户编辑剧本、人物设定和镜头意图，审阅画面并留下自然语言反馈，不需要填写道具状态或机器规则。动作链、跨镜道具状态、参考图用途由 Agent 通过内部 `creative_details` 维护；规则只做显式结构/文字核对，必要时向用户显示简短故事问题，不冒充语义或视觉质量检查。普通反馈保存和检查不撤销审批；镜头意图、内部结构或参考图的有效改动须重新审阅。没有自动重写提示词或自动生成。

详见 [分镜辅助与诊断边界](docs/STORYBOARD_ASSIST.md)。

## Wan3.0 配置与密钥隔离

1. 在 [千问AI平台](https://platform.qianwenai.com/home/api-keys) 自行获取对应 API Key。不要在聊天、语音、截图或 GitHub 中提供密钥。
2. 在网页“工具与设置”选择 **千问AI Wan3.0-Video-Prime**，保存分辨率、音频配置。在密码输入框填写密钥，点击“安全保存到仓库外”。后端本地存储名是 `WAN3_API_KEY`，发送时映射为官方 `Authorization: Bearer`。
3. 实际密钥位于仓库外 `../.video-agent-studio-private/credentials.json`：目录0700、文件0600，原子写入。网页不回显；不使用 localStorage；不存 SQLite 或项目导出；HTTP日志不记录请求正文，异常隐藏上游内容，响应对已知凭据做脱敏。
4. 可用 `STUDIO_SECRET_FILE=/absolute/private/folder/credentials.json` 显式指定仓库外路径，指向仓库内部会被拒绝。仓库 `.env.example` 仅说明非秘密启动选项；**应用不从仓库内 .env 读取或保存密钥**。
5. 配置、历史请求受理、历史生成完成分别显示，不以存在密钥伪造即时连通。标准图片和Prime视频已有本机真实调用证据；Pro仅切换为后续默认并完成协议/报价测试，停止生成后没有追加Pro出图。

按指定模型页使用北京接口 `https://cn-beijing.maas.qianwenaiapi.com/api/v1`，固定官方域名，不允许任意第三方 endpoint。平台详细文档另展示无地域前缀别名；当前不自动切换域名，也不把旧百炼 key 视作已验证兼容。跨账号、地域、套餐权限仍需用户账户核对。

**没有全局付费开关**。图片与视频预算按项目/数据库分别授权、记账，不互相挪用；预算含历史花费与未结算/在途预占，不是每次新增金额。未知实际费用不视为0，未经验证的免费额度不提前抵扣。标准分类预算模式不设任意每镜次数门槛，保留明确redo、单在途、未知提交锁和语义/质量门槛，预算内必要修复无需反复确认价格。超相应余额才请求调整额度；预算授权不等于画面质量批准。来源与版本存仓库外授权文件及SQLite快照，网页和CLI均可查看/设置。旧有限次数试验授权只作兼容和历史。Prime按480P/720P/1080P分别¥0.45/0.90/1.80每秒保守预占；30秒为¥13.50/27/54。图像Pro按像素档位1K输出¥0.25、2K¥0.50，参考输入每张¥0.02；代码不混用标准版价格。参考输入当前仅支持最多10张 HTTPS 图片；不支持输入视频/音频、首尾帧或文件，以免遗漏输入秒数计费；后续可以在同一官方协议上扩展。

暂停后所有新媒体入口均拒绝提交；预算/未花额度和历史保留，修改预算或默认模型不会自动恢复。用户“阶段性接受首版”单独记录，不宣称每项质量指标客观完美。

## FFmpeg 成片

```sh
python3 assemble.py assets/shot-01.mp4 assets/shot-02.mp4 -o episode-01.mp4
python3 assemble.py assets/shot-01.mp4 assets/shot-02.mp4 --subtitles assets/captions.srt -o episode-01-sub.mp4
```

准备同编码、同规格、同音轨结构的审核镜头。不会覆盖已有输出。暂无网页时间线、自动配音或混音；普通拼接可能保留输入音频时间戳差异，复杂剪辑应先标准化素材。

## 测试与资料

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
python3 scripts/check_secrets.py
# 可选浏览器测试需 Playwright Python + Chromium：
python3 tests/browser_workspace.py
python3 tests/browser_polling.py
python3 tests/browser_video.py
python3 tests/browser_lightbox.py
python3 tests/browser_budgets.py
python3 tests/browser_workflow.py
```

- [当前默认Pro/Prime与报价](docs/MODEL_DEFAULTS.md)
- [图片分镜API与音频](docs/STORYBOARD_IMAGE_API.md)
- [失败经验](docs/PRODUCTION_LESSONS.md) · [429诊断](docs/RATE_LIMIT_DIAGNOSIS.md) · [角色资产后续规范](docs/CHARACTER_ASSET_BACKLOG.md)
- [千问技能安装记录](docs/QIANWEN_SKILLS.md)
- [API调研与当前决策](docs/VIDEO_API_RESEARCH.md)
- [Wan3协议核对](docs/WAN3_INTEGRATION.md)
- [FFmpeg安装验证](docs/FFMPEG_SETUP.md)
- [验证结果与限制](docs/VALIDATION.md)
- 制作 Skill：`skills/production/SKILL.md`

运行数据在 `data/studio.db`，原有单项目数据自动迁移为示例项目。只发布源码、通用示例与文档；不发布数据库、凭据、私人素材或成片。尚未选择许可证，当前不附加 LICENSE；公开可读不代表授予任意使用许可。

## 给 Codex 使用的 CLI

CLI 通过同一个本机 HTTP 后端执行，复用 SQLite、分镜审批、预算和任务防重逻辑；请先启动网页后端。标准输出为 `{"ok":true,"data":…}`，失败为标准错误 JSON + 非零退出码。

```sh
python3 cli.py projects list
python3 cli.py projects create '新故事'
python3 cli.py projects select 1
python3 cli.py script get
python3 cli.py script set --file /path/to/script.txt --continuity-file /path/to/continuity.txt
python3 cli.py characters add --file /path/to/character.json
python3 cli.py shots add --file /path/to/shot.json
python3 cli.py shots list
python3 cli.py shots approve SHOT_ID
python3 cli.py tasks preview SHOT_ID
python3 cli.py tasks submit SHOT_ID
python3 cli.py tasks status TASK_ID
python3 cli.py images list
python3 cli.py images preview SHOT_ID
python3 cli.py images submit SHOT_ID
python3 cli.py images status IMAGE_TASK_ID
python3 cli.py audit sources
python3 cli.py audit history
python3 cli.py audit tasks
python3 cli.py shots review SHOT_ID --file /path/to/review.txt
python3 cli.py provider configure --provider wan3-prime --resolution 480p --image-model qwen-image-3.0-pro
python3 cli.py provider status
python3 cli.py budgets show
python3 cli.py budgets authorize --image 3 --video 7 --source "用户明确的两项总预算授权来源"
python3 cli.py export
```

上述3/7仅为命令格式示例，不能自动作为实际项目授权。`tasks submit` 仍受审批、对应预算、防重限制；终态需要语义明确重做时可加 `--redo`，在途/unknown不允许重提。Codex不得在没有人类图片审阅时自行执行 `shots approve`；此命令绑定当前图与内容哈希。仅确认文字规划时使用 `--text-only`，不能代替图片质量批准。角色和镜头支持 list/add/update，修改镜头会撤销其审批。可用 `--url http://127.0.0.1:8765`（放在子命令前）选择后端端口。

密钥用网页入口，或在本人终端运行 `python3 cli.py secret --provider wan3-prime` 隐藏输入；没有明文 `--key` 参数，不接受管道。素材文件放项目外部/忽略素材目录，SQLite只存结构化记录和引用。SQLite使用WAL与30秒锁等待；写入带项目ID和版本检查，防止网页与CLI覆盖过期状态。网络调用前的数据库事务已提交，不持有长SQL写事务；本机单服务当前会串行化外部任务提交。
