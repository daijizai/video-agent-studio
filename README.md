# Frame Studio / 视频制作 Agent 工作台

面向长期角色 IP、系列 AI 短剧的本地制作工作台。Codex 负责制作推理与策划，HTML 工作台负责编辑和进度，Python/SQLite 负责状态与预算，ComfyUI 执行工作流，FFmpeg 负责后期拼接。

## 本地运行

Python 3.9+，无需 pip 依赖：

```sh
python3 server.py
```

打开 http://127.0.0.1:8765 。当前交付预览使用 http://127.0.0.1:8766 （默认端口已被其他服务占用）。可用 `PORT=8766 python3 server.py` 更换端口。服务仅监听本机，适合单人使用；没有多用户认证，请勿暴露公网。

## 第一版已实现

- 六个可交互页面：制作总览、剧本与连续性、角色资产库、分镜工作台、执行与检查、工具与设置。
- 剧本和设定编辑、角色版本快照、分镜添加/编辑/逐镜确认、检查记录、JSON 导出。
- SQLite 持久化与本集预算；总时长 300 秒上限。按任务预占估价，**预占不是实际账单**。
- 本机 ComfyUI `/system_stats` 检测、API 格式工作流 `/prompt` 提交、`/history/{prompt_id}` 查询；编号持久化、重复提交拦截、未知结果锁定。
- 制作 Skill：`skills/production/SKILL.md`；供应商协议：`providers.py`。
- `assemble.py` 拼接同编码/同规格审核镜头，可选 SRT 烧录。当前版本不提供网页成片导出、自动混音或语音合成。

首次启动的《雾港来信》为**示例策划内容**，共 27 秒，仅用于演示交互，未达到完整一集长度。抽象分镜画面是 CSS 占位；没有生成视频、参考图、模型连接或费用。项目编辑存入 `data/studio.db`；修改示例不会调用模型。页面的演示标记保留，真实执行记录单独展示。

## ComfyUI 使用与限制

在设置页保存本机地址，例如 `http://127.0.0.1:8188`，粘贴通过 ComfyUI 导出的 **API 格式** JSON。在 CLIPTextEncode 文本中使用 `{{prompt}}` 注入镜头描述。默认不提供伪造工作流：模型、节点和输入必须匹配你的 ComfyUI 安装。

第一版只允许基础内置图像节点（名单见 server.py），用于证明连接和任务生命周期。**视频节点、第三方节点、付费节点尚未接入**；不要把本版本视为已完成视频模型集成。可灵、阿里云等供应商仅有适配协议，无凭据、无实现、无付费生成。ComfyUI 完成结果目前展示输出元数据，媒体文件需在 ComfyUI 侧检查。

提交前必须确认镜头并有足够预算。意图先落库，再提交网络请求；网络超时标记 unknown，不自动重试。需在 ComfyUI 手动核对未知任务。当前版本不提供取消、自动重做与未知任务解锁；要重做可添加一个新镜头，但务必先核对旧任务。没有供应商实际费用回传。

## 成片脚本

需要自行安装 FFmpeg。准备同分辨率、同编码、同帧率且具有一致音轨结构的镜头：

```sh
python3 assemble.py assets/shot-01.mp4 assets/shot-02.mp4 -o episode-01.mp4
python3 assemble.py assets/shot-01.mp4 assets/shot-02.mp4 --subtitles assets/captions.srt -o episode-01-sub.mp4
```

不会覆盖已有输出。暂无 FFmpeg 时明确报错。声音混音、片头、时间线编辑仍待实现。

## 数据与开源边界

只发布源代码和通用示例。`data/`、`.env`、本机数据库、素材和成片不应入库。没有选择开源许可证，当前暂未附加 LICENSE，公开可读不代表授予任意使用许可。

## 验证

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```

浏览器 smoke 测试需要可选的 Playwright Python 包及 Chromium；运行 `python3 tests/browser_smoke.py`（先启动服务）。
