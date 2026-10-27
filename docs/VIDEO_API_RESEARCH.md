# 视频 API 首轮试验决策

核对日期：2026-10-28（中国标准时间）。用户最终指定 **千问AI平台 Wan3.0-Video 主用**；详见 [Wan3协议核对](WAN3_INTEGRATION.md)。2.6仅保留成本对照。语音里的“Synth”按上下文推断为字节 Seedance，名称仍可由用户纠正。以下均为官方资料；未登录购买页面、未充值、未提交生成请求。价格会变，应在真实试验前再次核价。

## 建议与可审阅比较

| 候选 | 官方直连接入与条件 | 价格口径和试验成本 | 角色参考、音频与时长 | 本轮决定 |
|---|---|---|---|---|
| 阿里 Wan 2.6 R2V Flash | 百炼 API Key + 对应地域业务空间 ID；开通模型与账户计费资格须在控制台核对 | 北京 720P 无声 ¥0.15/秒、有声 ¥0.30/秒；1080P 无声 ¥0.25/秒、有声 ¥0.50/秒。输入参考视频 + 输出视频均计费；图片参考不增加视频秒数。5 秒无声、仅参考图约 ¥0.75 | 0–5 图、0–3 视频，总参考数≤5；每个素材单角色，按 character1…引用；输出 2–10 秒整数；可选原生音频 | 成本对照；不能替代用户最终指定的Wan3。旧协议适配保留 |
| 字节 Seedance 2.0 Mini | 火山方舟 API Key；2.x 开通条件包含账户余额>¥200、指定节省计划或有效资源包三选一，不能把可用文档等同于账户已开通 | 无视频输入 ¥23/百万视频 tokens，有视频输入 ¥14/百万；720P/16:9/5秒官方示例约 ¥2.48。代码向上取分预占 ¥2.49。视频参考有最低 token 规则，不能只比较单价 | 2.0 系列最多9图/3视频/3音频；支持有声视频。2.5 可30图/10视频/10音频、最长30秒但更贵。真人脸参考有专门授权/来源要求；并非任意人脸均可上传 | **对照**：保留 Mini 图片参考适配和 mock 测试；不为此充值 |
| 可灵 Kling 3.0 / Omni | 官方开发平台有 API Key 和资源包入口；当前文档支持 API Key，旧 AK/SK 方式并存。能否开通、套餐最低购买量须账户控制台核对 | 官方视频资源包 Units 计费。3.0 720P 无声 $0.084/秒、有声 $0.126/秒；Omni 无视频输入720P有声 $0.112/秒。5秒无声约 $0.42；不做未经核对的人民币换算 | Omni 图像/元素库支持身份参考；视频参考为单独模式，有声限制随输入类型变化。旧 Omni 接口文档中 3.0 支持3–15秒；不要混用新旧请求字段 | 调研候选；本轮不扩展代码。**4.0 在官方定价文档仍标 Coming Soon，不能据第三方宣传认定已开放** |
| 阿里 Wan 3.0 | 同属百炼，官方 API 文档与计费单独定义 | 北京刊例480P ¥0.30/秒、720P ¥0.60/秒、1080P ¥1.20/秒；页面有临时7折，预算按原价更稳妥 | 输入+输出视频秒数计费；不能把2.6的 reference_urls 原样挪到新版 | **最终主用**，已实现指定千问AI平台endpoint与media协议，详见专项文档 |

Seedance 2.0 Mini/Fast 的企业限时折扣活动截至 2026-10-07，**不使用已结束的四折价格做当前预算**。阿里免费额度有地域、有效期和账户条件；当前没有核对用户额度，不将免费额度算进预算。

## 官方来源与核对方法

- [阿里百炼模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)：北京与国际区价格不同；上表以北京为主。
- [Wan 2.6 参考生视频 API](https://help.aliyun.com/zh/model-studio/legacy-wan-reference-to-video-api-reference)：workspace endpoint、异步任务、reference_urls、音频与输入限制。结果 URL 和任务查询有效期均为24小时，需及时保存。
- [获取百炼 API Key](https://help.aliyun.com/zh/model-studio/get-api-key)：密钥与业务空间、地域必须匹配。
- [火山官方模型价格 Markdown](https://ark.volcengine.com/region:cn-beijing/docs/model-pricing.md)：已直接读取并核对模型行与720P示例；按 usage.completion_tokens 结算，公式为视频时长×输出宽×高×帧率/1024，含视频时需考虑输入时长及最低量。
- [火山创建视频任务](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)：开通条件、参考模态、角色素材要求及参数。
- [可灵官方价格 Markdown](https://kling.ai/document-api/pricing/base/video.md)：已直接读取。不要把4.0预览报价当作可调用模型；不要混用网站会员积分与API Units。
- [可灵快速开始](https://kling.ai/document-api/guides/get-started/quick-start)、[API更新](https://kling.ai/document-api/apiReference/updateNotice)、[Omni旧协议](https://kling.ai/document-api/api/video/o1/video-omni/legacy)：真实申请入口和版本差异。

## ComfyUI 是执行引擎，不等于免费供应商网关

官方 Partner Nodes 使用 Comfy Credits，当前官方支持页给出 **211 credits = 1 USD**，执行节点时扣除；Comfy API Key 是 Comfy 的登录凭据，不是阿里或可灵密钥。[官方积分说明](https://support.comfy.org/articles/1982697177-partner-nodes-pricing)。

BYOK 不能一概而论：当前 [Comfy Cloud 价格页](https://comfy.org/pricing/) 表示支持 Runway / Google Gemini 的 workspace BYOK，企业客户可申请其他供应商。这不证明普通本地 Wan / 可灵 / Seedance Partner Node 支持自己的供应商密钥。[Runway自己的Comfy指南](https://dev.runwayml.com/learn/build-with-comfyui)仍说明内置节点使用Comfy积分，说明文档和产品范围存在差异。对这三家的视频节点，本轮没有得到官方普遍 BYOK 的证据，应按节点和账户权限逐一核对。

本项目的 Wan/Seedance Python 适配器直接向官方 API 发送请求，使用用户自己的供应商密钥，费用走供应商账户；**不是 Comfy 积分转售**。ComfyUI 保持本机工作流引擎角色。当前没有把付费 API 封装成 Comfy 自定义节点，也不会放开任意付费节点来绕过预算锁。

## 真实试验前的最小准备

1. 用户在千问AI平台获取key，通过网页密码输入框写入仓库外私密文件（本地键名WAN3_API_KEY）；不能发到 Git、截图或导出 JSON。
2. 准备一组长期角色参考图，托管到供应商可访问的 HTTPS URL。每图单角色；当前适配器只允许图片参考，不接受输入视频或音频，避免遗漏输入秒数费用。
3. 网页里先保存分镜与参考图，再预览请求及估价。Wan3显式分辨率与音频，不使用供应商默认1080P设置；镜头结构通过提示词约束。
4. Wan3未来试验须由用户明确授权 **单个5秒、480P镜头，原价预占¥1.50（页面折后¥1.05），试验总上限另行确认**。本建议不等于已获花费授权。当前 `STUDIO_ENABLE_PAID_GENERATION=false`，不会请求生成。
5. 生成请求先落库，保存任务编号。超时/断线一律 unknown 并锁定；本地 UUID 不是供应商幂等保证，禁止自动重发。完成任务记录用量与输出链接，实际账单未知时保留 null。

## 本轮实现边界

已实现 Wan3主用 + Wan2.6 / Seedance Mini 对照的构建请求、校验、提交、查询和状态归一化；以 mock 传输测试字段契约。没有密钥，没有真实认证/生成/效果验收。网页区分“缺少配置”“配置存在但连接未验证”，不以配置文件存在伪造接通成功。当前输出媒体仍需自行下载留存，真实费用尚不自动回写。
