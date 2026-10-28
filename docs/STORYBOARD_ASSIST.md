# 故事审阅与内部一致性契约

## 用户流程

普通用户看剧本、人物设定、镜头画面、故事意图和成片，并留下自然语言反馈。维护角色、场景和道具一致性是制作系统与 Agent 的默认职责，不要求用户理解参考用途、负面词、结构字段或请求参数。

- 剧本页仅编辑作品名、本集标题与正文；保存时不发送隐藏的 `continuity` / `project_brief`，因此不会用空字符串覆盖它们。
- 分镜页保留图片放大、生成状态、估价、镜头名称/停留时长、故事意图、画面确认和反馈。`story_intent` 是用户故事要求，不从机器 prompt 回填，不自动编译或替换机器提示。
- 保存反馈只更新 `review`，不撤销当前审批，也不自动发起修复。检查镜头衔接只读草稿，不保存、不调用模型。
- 修改故事意图后重新审阅受影响镜头。具体人物/脚本修改仍按原有内容哈希使有关审批失效。
- 普通页不显示参考 URL、图片/视频 prompt、完整创作 JSON、原始请求或工作流。设置仍保留模型、密钥写入、画幅/音频、预算；不回显密钥。

设置 → **进入开发者诊断** 是独立 `#diagnostics` 页面，默认不在普通制作导航中。机器规则、原提示、参考列表、辅助结构表单、零网络 payload 预览、原始任务账本、ComfyUI API 工作流以及版本审计只在明确进入后显示。返回分镜即恢复普通视图。数据库、项目导出与 CLI 的内部字段继续保留。这是信息架构分离，不是多用户权限或秘密隔离边界。

这不是 ComfyUI 执行封装，也不是新的生成器；模板执行、遮罩修复和供应商适配属于其他模块。

## 内部字段（可选，不迁移旧数据）

沿用 `shot.creative_details`，保留已有 camera/action/neighbors 等内容：

```json
{
  "action_chain": {
    "start": "坐姿",
    "trigger": "听见敲门声",
    "steps": ["抬眼", "望向门口"],
    "end": "坐姿",
    "incoming_transition": ""
  },
  "prop_states": [{
    "asset_id": "P01-v1",
    "start": {"location": "托盘", "holder": "", "count": 1, "visible": "visible"},
    "end": {"location": "托盘", "holder": "", "count": 1, "visible": "offscreen"},
    "transition": "",
    "incoming_transition": ""
  }],
  "reference_bindings": [{
    "reference_index": 1,
    "url": "https://example.com/reference.png",
    "purpose": "人物身份",
    "preserve": ["脸型", "服装"],
    "asset_version": "C01-v1",
    "source_task_id": "source-task-or-hash"
  }]
}
```

数量空白保存为 null/未知，0 表示明确为零；可见性为 `unknown`、`visible`、`offscreen`。画外/遮挡不能推导数量为零、消失或位置变化。`holder` 可写角色 ID/持有手；相同含义应使用相同值，规则不做同义词语义推断。

参考用途同时绑定序号与确切 URL；链接/顺序变化后旧说明不自动套到新图。资产版本/来源任务是显式记录，不凭用户填入的文字冒充已批准母版。Agent 仍须核对实际资产。更换短期签名 URL 会要求重新确认，当前不把不同 URL 自动判断为相同图片。

诊断编辑只更新内部元数据，不自动改图片或视频 prompt。图片仍描述单一静态瞬间；视频 prompt 表达时间中的变化。静物允许起止相同、无 trigger 和 steps。没有参考图就无需虚构参考描述。诊断表单选填，未操作时不写入新结构。

## 可解释预检

`static/storyboard-checks.js` 为无网络、无状态修改的纯规则模块，输出 shot_id、field、code、evidence、suggestion、related_shot_id，所有发现都为待核对提示：

- 同一资产的数量、位置、持有人变化但无镜内过渡；相邻镜头 end/start 不一致但无入镜前过渡。
- 明确的整段状态词对（坐姿/站姿、门关闭/门打开、静止/行走）在相邻起止间不一致。自由描述不作全面语义理解。
- 参考图有链接但用途缺失或绑定已过期。
- 图片提示出现动作先后、多镜头或时间段线索。画面内钟表时间（如23:53）本身不是时序过载。
- 部分结构/自由文本的“全程静止”与动作关键词线索。描述可能指不同主体，不能自动判断哪份正确。
- 道具 ID 缺失/重复、数量格式异常。

诊断页显示完整证据、字段与可聚焦链接；普通页只把与当前镜头相关、需要用户判断的道具/状态/动作问题转换为短句。缺少参考用途、图片时序或内部格式问题不会要求普通用户填写技术表单。规则发现并不表示画面已发生该问题；无发现也不表示语义、画面或质量已通过。静默改写、自动审批、自动重试均不存在。

## 审批与任务快照

`storyboard_contract.py` 计算独立 version=1 的参考/辅助字段绑定。新 `record_approval` 附加 `storyboard_binding_version` 和 `storyboard_binding_hash`；原内容哈希算法仅在镜头明确存在 `story_intent` 时加入它，保留无该字段的历史结果。

- 历史记录无新绑定且镜头无新辅助字段，继续使用旧审批；不批量补写或清空六镜/成片接受记录。
- 添加/修改内部字段或参考图时，只撤销发生有效变化的镜头审批；预检、进入页面、隐藏表单、反馈保存都不撤销审批。
- 有新辅助字段却仅持旧审批，不视为继承有效审批。
- 新参考/结构绑定参与 `valid_approval` 及单镜/整片 `task_matches`；改后重新批准不能把旧请求的视频当成新内容生成结果。
- 原 `content_snapshot` 已深拷贝完整 shot，因此保留内部结构、意图与审批绑定；实际供应商 payload 仍使用显式 prompt，不偷偷附加元数据。
- generation pause、预算、供应商防重及未知提交规则保持不变。

## 验证

```sh
node --test tests/storyboard_checks.test.js
python3 -m unittest discover -s tests -p 'test_storyboard*.py' -v
python3 tests/browser_storyboard_public.py
python3 tests/browser_storyboard_assist.py
```

浏览器测试使用复制的静态文件、临时 SQLite、临时私密路径和随机 loopback 端口；不启动8766、不写实际项目、不真实调用模型。普通视图测试验证无机器表单/字符串泄漏、保存隐藏数据无损、脚本与人物可编辑、反馈与预检不变审批、故事意图保存重载、项目隔离、375px/横屏布局。诊断视图测试验证选填结构、键盘展开、字段定位、保存重载、内部与原 prompt 分离。其他现有浏览器测试按新的意图输入/独立诊断入口回归。

## 参考与许可边界

设计参考 [Wayhhow/ai-video-shot-prompt-skill](https://github.com/Wayhhow/ai-video-shot-prompt-skill) 的基础设定/氛围画质/画面内容框架、动作因果和参考图描述思路；其方法来源见 [CREDITS](https://github.com/Wayhhow/ai-video-shot-prompt-skill/blob/main/CREDITS.md) 中 Mx-Shell 的公开创作分享。

本实现自行编写，不复制第三方大段代码或模板，不安装/执行该 Skill。原仓库 [MIT License](https://github.com/Wayhhow/ai-video-shot-prompt-skill/blob/main/LICENSE) 要求复制或实质改编其软件/文档时保留版权与许可声明；该许可不覆盖原视频、人物或素材的所有权。没有将其授权套用为本项目整体许可证。

不强制超写实词、统一负面词、设备名称或固定分镜比例。不采用 README 缺少配套实验依据的改善百分比；关键词出现不能代表质量通过。
