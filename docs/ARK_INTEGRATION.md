# 火山方舟模型接入

核对日期：2026-10-28。本次新增可选适配，保留原项目默认配置、历史图片、六镜审批和已接受首版视频，不自动恢复生成。

## 固定模型与已实现范围

| 用途 | 工作台选择 | 固定模型 ID | 协议 |
|---|---|---|---|
| 视频 | Seedance 2.5 | `doubao-seedance-2-5-260628` | `POST /api/v3/contents/generations/tasks`，保存返回 ID，查询原任务 |
| 图片 | Seedream 5.0 Flash | `doubao-seedream-5-0-flash-260915` | `POST /api/v3/images/generations`，同步单图，结果先持久化再缓存 |

固定使用北京官方地址 `https://ark.cn-beijing.volces.com`，支持直接 Model ID，不要求另建 Endpoint。

Seedance：4–30 秒整数时长；480p/720p/1080p；16:9、9:16、1:1；有声/无声；纯文本或最多30张HTTPS图片参考。显式指定 `omni_reference_task_type=reference`，避免被自动识别为编辑/延长而触发不同参数约束。优先引用当前分镜图片，其次使用参考图片列表。未开放视频/音频参考、首尾帧、自动时长、其他画幅，不等同于模型的完整能力。含真人人脸的参考素材受平台使用限制，不能从文件名判断是否合规。

Seedream：文本或最多3张HTTPS参考图，这是工作台子集；固定单张2K PNG、非流式，画幅由提示词明确描述，返回的实际尺寸以产物为准。Flash 的参数目录不支持组图开关，不能沿用其他版本的组图参数。不开放图层拆分、透明背景或多张输出。

## 成本预占与执行权限

Seedream 固定版本刊例价为 ¥0.12/输出张。Seedance 无输入视频时按视频 tokens 计费：480p/720p 为 ¥0.07/千tokens，1080p 为 ¥0.077/千tokens。适配器按该版本官方输出宽高 × 24fps × 时长 / 1024 估算 tokens，并为帧舍入预留1秒、金额向上取到分；`estimate_basis` 可审阅。这是保守预算估算，不是实际账单或供应商保证的价格上限，最终费用以平台结算为准。视频输入属于另一计费路径，本适配不开放，不能套用其较低费率。

接入、模型开通、密钥配置、切换下拉框都不等于生成授权。当前既有项目保持 paused；不会增加已批准模型范围。未来用户明确批准模型和预算后，可通过本机 CLI 的显式模型参数记录授权范围，例如：

```sh
python3 cli.py budgets authorize --image 10 --video 50 \
  --model doubao-seedream-5-0-flash-260915 \
  --model doubao-seedance-2-5-260628 \
  --source '填写本次用户明确预算与模型授权的来源'
```

该命令仅记录明确授权，**不会解除已暂停状态**；不要把示例当成许可直接执行。金额包含历史及未知/在途预占，图片和视频互不挪用。真实生成前仍需用户明确恢复执行。新 Seedance 请求还要求在实际模型/参考来源已选定后审阅批准：审批记录包含版本化参考URL、当前图片任务和图片哈希；更换实际参考不能复用旧绑定。旧版千问的审批哈希不重写，首版接受与历史保持有效；它们不自动成为新的方舟参考审批。

## 工作台与 CLI

“工具与设置”可选择 Seedance 2.5 / Seedream Flash；CLI 使用同一后端：

```sh
python3 cli.py provider configure --provider seedance25 --resolution 480p --ratio 9:16 --audio \
  --image-model doubao-seedream-5-0-flash-260915
python3 cli.py images preview SHOT_ID
python3 cli.py tasks preview SHOT_ID
```

切换只改变后续请求配置，不重生成历史，不默认扩大本项目授权。真实密钥继续在仓库外私密文件中保存为 `ARK_API_KEY`，不通过命令行明文参数、不回显、不写SQLite或导出。原有 Qwen Pro / Wan Prime 仍可选。

Seedream 没有异步任务ID：同步返回图像URL后先保存原结果，下载失败仅重试下载；页面显示“重试本地下载”。同步请求超时且未取得结果时保存 unknown 并阻止重提，不能拿本地UUID冒充供应商任务号。历史图片查询不能替换当前图片或清除新图审批。

Seedance 的查询、自动轮询、CLI与阶段推导均按供应商类型路由；终态失败不算完成，completed不等于质量通过。下载仅接受已允许的供应商域名，禁止重定向和带凭据URL，不向下载地址转发API Key。

## 验证与边界

- 单元/HTTP模拟测试覆盖请求参数、预占、同步持久化与缓存恢复、unknown防重、参考审批、暂停、类别预算和模型授权隔离、异步状态路由。
- 隔离浏览器测试覆盖模型选择、暂停保持、零网络预检、模拟同步图片回填和项目隔离。测试使用假密钥和临时数据库。
- **本轮没有提交真实方舟图片或视频生成请求**。管理侧登录/开通状态不能替代生成实测；本项目现有千问成片不能作为方舟效果证据。

官方接口依据：[创建视频生成任务](https://ark.volcengine.com/docs/create-video-generation-task-api)、[Seedream 5.0 专属能力](https://ark.volcengine.com/docs/seedream-5-0-pro)、[图片生成 API](https://ark.volcengine.com/docs/image-generation-api)。
