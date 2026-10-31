# MiniMax 视频接入

中国站官方 H3 V2 接口，2026-10-31 核对。完成代码及离线验证，不代表真实账户认证或模型出片效果已验证。

## 使用

1. 工具与设置 → 执行供应商选择 MiniMax，选择 H3 / Highspeed / Lite / Max 及对应分辨率，保存配置。
2. 在同一面板输入中国站 `MINIMAX_API_KEY`，保存到仓库外私密配置（目录0700、文件0600）。不在聊天中传密钥。
3. 视频制作 → 编辑片段 Prompt、参考素材、声音参考及前置视频。H3 时长4–15秒，Max 5–15秒；纯文本可不选参考图。
4. 保存并预览完整输入，核对模型、素材及费用。修改供应商、模型、Prompt或引用后必须重新确认。
5. 明确授权项目预算及所选MiniMax模型后才能生成。设置中的预算表单提供可选模型授权框；配置密钥或预算不会解除既有生成暂停。接入工作不会自动扩大授权。
6. 查询原任务，成功后下载MP4并在候选视频中播放、人工验收。未知提交保留预占，不自动重试。

## CLI

`provider configure --provider minimax --model MiniMax-H3 --resolution 768P` 配置模型，`secret --provider minimax` 在交互终端隐藏输入并通过本机后端保存密钥。所有命令前加 `python3 cli.py`。

片段命令：`segments create` → `segments update SEGMENT_ID --file draft.json` → `segments preview SEGMENT_ID` → 用户审阅后 `segments approve SEGMENT_ID --fingerprint PREVIEW_FINGERPRINT --source HUMAN_CONFIRMATION_SOURCE` → `segments submit SEGMENT_ID`。审批不自动授权预算或恢复暂停；模型或输入变化会使旧确认失效。`segments tasks SEGMENT_ID` 列出候选，`segments status LOCAL_TASK_ID` 查询原任务。

完整草稿字段和可复制命令见 [README 的 CLI 说明](../README.md#从-cli-使用-minimax)。没有把文档示例或Agent自述当作真实用户批准，也没有以真实生成验证接入。

## 已接入范围

- 文本生成和素材图片参考生成；素材不作为隐式首帧。
- 已验收的兼容供应商视频作为前置参考；参考音频沿用声音素材。图片最多9张、视频最多3段且合计15秒、音频最多3段且合计15秒，媒体总数最多12；单段音视频2–15秒。
- H3分辨率768P/2K，其他三款480P/768P，参数不做隐式规格替换。
- H3没有独立音频开关，本接入不发送Seedance的`generate_audio`；UI明确标出声音由模型处理。“使用声音参考”仅控制是否传参考音频。
- 创建任务 `POST https://api.minimax.cn/v2/video_generation`，查询 `GET /v2/query/video_generation/{task_id}`。持久化任务ID、输入快照、usage和原始元数据；实际账单金额未知时继续保持未知。
- 费用按官方输出秒价、输入视频秒价和超额图片张数预占；输入音频免费；视频输入不足整秒向上取整预占。价格为公示原价，不冒充账户折扣或结算账单。
- 首尾帧专用编辑器、H3 Context-IR、视频再生成和任务取消未在本次接入范围。

## 验证

`python3 -m unittest discover -s tests -p 'test_minimax.py'`

`python3 -m unittest discover -s tests -p 'test_cli*.py'`

`python3 tests/browser_minimax.py`

全部使用Mock或临时项目，不提交真实视频任务。

## 官方资料

- [创建视频任务](https://platform.minimax.cn/docs/api-reference/video-generation-v2-create)
- [查询任务](https://platform.minimax.cn/docs/api-reference/video-generation-v2-query)
- [使用说明](https://platform.minimax.cn/docs/guides/video-generation)
- [价格](https://platform.minimax.cn/docs/pricing/overview)
