# 千问官方 Skills 安装记录

2026-10-28，根据用户指定 https://platform.qianwenai.com/skills.md ，使用Codex官方skill-installer安装到 `~/.codex/skills`，不覆盖现有目录。

清单页头写9个、表格列10个；两个指定仓库实际包含14个正式SKILL目录，已全部安装，并逐文件SHA-256比对临时审阅副本与安装副本一致。

- `QianWen-AI/qianwen-ai` 固定提交 `11b1805167d91bc931dbaad85e17036a72e98ae0`：qianwen-audio-tts、qianwen-image-generation、qianwen-find-skills、qianwen-model-selector、qianwen-ops-auth、qianwen-payment、qianwen-update-check、qianwen-text、qianwen-usage、qianwen-video-generation、qianwen-vision。
- `QianWen-AI/qianwenai-deploy` 固定提交 `5e476b3d085946f41014094e2e44e7409aa92644`：qianwenai-deploy、qianwenai-observe、qianwenai-operate。

Node20.19满足要求；官方CLI `@qianwenai/qianwen-cli@1.10.0` 已安装。用户在当前权限确认后完成官方设备登录，服务器认证成功，CLI会话由系统钥匙串管理。未提取会话token。模型APIKey与CLI会话是两类凭据；经用户对创建时的明确确认，专用APIKey由浏览器只写传入本地后端，保存在仓库外0700/0600文件，不输出原值。

官方认证skill建议仓库内.env，但本项目遵循用户更严格的仓库外隔离要求。安装payment/deploy技能不代表充值、订阅或云部署授权；本轮没有这些操作。技能可在下一轮对话中被发现使用。
