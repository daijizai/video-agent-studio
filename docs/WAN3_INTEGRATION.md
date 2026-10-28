# Wan3.0-Video 接入核对

> 历史接入/调研记录保留。当前默认已按用户明确选择改为图片Pro、视频Prime；见 [当前默认与报价](MODEL_DEFAULTS.md)。不把旧标准版价格或早期未验证状态当成当前结论。
2026-10-28。最终指定主用模型：`wan3.0-video`，来自用户给出的 [模型页](https://www.qianwenai.com/models/wan3.0-video)。没有真实 key，没有生成调用、认证验收或充值。

## 官方归属与平台差异

阿里云官方帮助站 [模型价格页](https://help.aliyun.com/zh/model-studio/model-pricing) 导航直接链接到 qianwenai.com；模型页链接千问平台文档、API Key后台及阿里云，并使用阿里 CDN 协议链接。交叉证据支持这是阿里千问平台的官方产品入口，而非第三方转售页面。

[千问平台创建任务文档](https://platform.qianwenai.com/docs/api-reference/video-generation/wan30-video/create-task) 明确写明千问AI平台 API Key，`Authorization: Bearer`，以及异步请求头。模型页北京 endpoint 与详细文档的通用 endpoint 存在差别：本实现固定采用模型页 `https://cn-beijing.maas.qianwenaiapi.com/api/v1`，不把 `maas.aliyuncs.com` 旧 workspace 域名直接替换后声称兼容。相同 `DASHSCOPE_API_KEY` 环境变量名称只是代码约定，不证明旧账户密钥跨平台可用；请从此平台后台配置具有北京模型权限的 key。是否已开通与余额充足尚未核对。

## 实际字段

已核对 `POST /services/aigc/video-generation/video-synthesis` 与 `GET /tasks/{task_id}`。

- 请求体：`model`、`input.prompt`、可选 `input.media=[{type:reference_image,url:…}]`。
- 参数：`resolution` 使用 `480P/720P/1080P`，不是旧版 `size`。明确传 `ratio=16:9`、整数 `duration`、`audio`、`watermark=true`、`prompt_extend=false`。
- 参考顺序通过“图1、图2…”在提示词引用，最多10张参考图；纯文生视频不传 `media`。不沿用2.6的 character1 / reference_urls 约定。
- 官方支持2–30秒整数、30fps；有输入视频时输入+输出不超过30秒。音频开关同价。当前适配器仅开放纯文本及图片参考；其他模态的格式和计费不在本版开放。
- 标准异步状态和 task_id 持久化；结果 URL 与查询有24小时有效期。不会用提交任务的方式测试“连接”。

## 价格与授权

模型页限时七折为480P ¥0.21/秒、720P ¥0.42/秒、1080P ¥0.84/秒；原价分别¥0.30/0.60/1.20。未在公开页核实折扣截止日与账户适用细则，因此代码按原价预占：5秒480P ¥1.50、720P ¥3.00。输入视频会增加计费秒数，故当前拒绝视频/音频参考。未来计划开启时必须先确认具体预算；本轮不开启付费开关。

[阿里官方Wan3协议](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference)用于交叉核对媒体限制、计费时长和字段，但没有将其 workspace endpoint 与用户指定平台 key 混用。

## 密钥边界

`secret_store.py` 将密钥写到仓库外私密 JSON（0700/0600）。使用 `WAN3_API_KEY` 作为本地存储键，避免无意拿旧 `DASHSCOPE_API_KEY` 发到新的域名。前端输入后清空，不回显；状态仅布尔值；不存浏览器 localStorage、SQLite、导出或日志。

假密钥测试覆盖外部路径、文件权限、拒绝仓库内路径、响应/日志/数据库/导出及上游异常脱敏。不能证明所有未来代码、恶意浏览器扩展或用户手动粘贴行为都不会泄漏；必须在后续改动中继续运行检查。
