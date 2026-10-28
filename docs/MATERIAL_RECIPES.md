# Skill创作交接与素材运行时合同

## 分工

创作方法独立维护在 [剧本/分镜](../skills/frame-screenplay/SKILL.md)、[角色资产](../skills/frame-character-assets/SKILL.md)、[物品资产](../skills/frame-object-assets/SKILL.md) 三个Skill。Codex读取相关Skill与项目材料，为项目写设计蓝图和当前视图提示。普通用户不填写脸型、衣料、参考数组或机器prompt。

`asset_templates.py` 是**薄运行时合同**：校验已交接数据、来源指纹、主体类型、单图/朝向/完整范围、母版阶段与模型映射。它不解释Skill正文、不从剧本猜脸型或衣服、不假装后端会像Codex一样创作，不新增付费文本推理。项目换题材或设计不需要修改Python。

公共职责和持久化规则见 [PRODUCTION_HANDOFF.md](PRODUCTION_HANDOFF.md)。这份文档描述代码接口，不替代三份创作Skill，也不把预算/审批门禁移入自然语言。

## 从项目设计到真实生成

1. Codex按相应Skill准备版本化 `design_profile`，通过 `assets/design` 交接为候选版本。
2. 界面显示可读设计、事实/创作选择/未知来源，机器提示不显示成表单。交接缺失时明确待制作助手准备，不由服务端编造外观。
3. 预览本批素材、视图、成本和已交接设计，确认后按原图片预算/暂停/模型范围执行。
4. 原图生成完成仍是候选；人工看图采用后才能作为后续母版或镜头参考。

已有导入/历史不会删除。新设计候选不自动采用、不覆盖批准引用；实际生成需要原项目的明确授权。

## 内部交接数据

`design_profile` 包含：

- `schema_version=1`、`design_version` 和 `subtype`（human / robot / animal / other；物品为object）。
- `fields`：每项 value、origin（story_fact/system_choice/unknown）、evidence。人类、机械角色、动物/其他角色和物品使用各自适用字段，不让机器人填人类发型、肤色或鞋服。
- `standard_setup`：id、background、lighting、scale，由Codex/Skill交接共同设置。
- `master_plan`：identity_tag、structure_tag、has_head、has_feet，按主体实际选。角色身份入口可为portrait或body_front，结构正面为body_front；物品为main。不机械要求所有角色先生成头像。
- `source`：skill_id、skill_version、skill_sha256、handoff_contract_sha256；后者绑定公共PRODUCTION_HANDOFF.md。可附文档摘要/章节；`references`记录明确读过的Skill目录内相对路径→sha256，至少包含本次使用的一份templates来源。
- `view_recipes`：本项目需要的视图描述与元数据，最多8项；不是默认生成全部图。

提交`assets/design`时，代码自动给当前项目/素材名称、简要设定、角色作用与外观变体盖上input_basis_hash。随后修改创作输入会使旧交接待更新，不会用旧prompt冒充新设计；只添加图片不改变该绑定。Codex可携带已有指纹作过期检查，无需普通用户计算。

内部字段键：human使用identity/age/appearance/face_outline/face_features/hair/body/outerwear/innerwear/lowerwear/footwear/clothing_materials/body_proportions/accessories/project_style；robot使用identity/service_age/chassis/head_shell/sensors/joints/body_proportions/manipulators/surface_materials/markings/project_style；animal/other使用identity/body_plan/covering/distinctive_features/appendages/body_proportions/project_style；object使用identity/shape/material/structure/color/wear/project_style。每项有value、origin、evidence。

代码校验标识、来源、长度与结构，不自动证明故事事实分类或提示语义正确。Codex需按Skill检查创作内容；`unknown` 不会被后端自动填成人类属性。缺少适用设计/配方时，生成被阻止，界面提示由制作助手交接。

单个视图交接字段：

```json
{
  "id": "project-view-recipe-id",
  "version": "draft-1",
  "prompt": "由Codex按相应Skill编写的当前单一视图描述",
  "part": "full_body",
  "direction": "front",
  "single_image": true,
  "single_subject": true,
  "neutral_pose": true,
  "head_visible": true,
  "feet_visible": true,
  "complete_subject": true,
  "contains_hands": false,
  "setup_id": "project-standard-setup-id"
}
```

字段按类型适用；物品的 `contains_hands=false` 是排除持有人，角色的双手是主体自身结构。视图标签和朝向使用现有portrait/head_front/head_side/head_back/body_front/body_side/body_back/three_quarter及main/front/side/back/detail，侧面定义为右侧90度，背面为180度。全身必须声明完整主体，并保留该主体实际存在的头/足；无足动物不被强制添加脚。

提示正文最多4000字符，只消费交接的当前视图，不复制整份剧本/手册。运行时另加最小单图和完整主体约束，不在Python里维护脸型、配色、服装等创作词库。

## Skill与配方来源核对

代码只对仓库内固定的 `skills/frame-character-assets/SKILL.md` 或 `skills/frame-object-assets/SKILL.md` 及声明的 `references/`、`templates/` Markdown/JSON核对字节指纹与metadata版本。它不执行文档，也不请求外部地址。

绝对路径、`..`、符号链接、错误类型/版本/指纹或过大来源文件拒绝。不存在或变化的规范需由Codex重新读取、更新交接，再明确审阅；服务端不能自行“理解新规范”后修改项目。Skill名/版本/hash与当前配方填充值进入请求来源快照。

`parse_design_markdown` 只是给Codex读取明确指定旧设计文档的来源适配器：保留章节、事实/选择注记与摘要，始终 ready=false，不把一段旧Markdown自动当作完整可生成交接。私人蓝图、交接文件和原图不进Git。

## 不能仅靠Skill文字的门禁

- 单图、单主体、正确朝向、共同标准设置与中性姿态由代码验证声明；Qwen n=1、Seedream唯一返回图、实际参数/下载格式另由代码保证。模板声明不等于实际图片已符合。
- 先人工采用身份/结构正面。人类以头像为身份入口时，全身正面需要身份图；侧背需要身份＋结构正面。机器人等可明确以完整结构正面同时担当身份和结构基准，不虚构额外头像。引用去重但保留明确原图/版本。
- 身份/结构母版不与其后续扩展在同一素材批次混跑；缺已审阅母版时前后端都阻止。头部和全身分别保存独立文件，拼版不能冒充参考母版。
- 物品主图先采用，再补必要角度/细节。外观身份不读镜头中的数量、持有人、位置或画外状态。
- 设计、交接来源、配方或实际模型映射变动使旧预览/未执行计划失效。现有单在途、先持久化、unknown锁、原编号查询、下载恢复与分类预算保持。

当前镜头可选视图必须符合当前交接与审阅。仅有身份图不宣称整套多视图可复用；基础就绪和正侧背审阅分别标记。人工采用不是三维几何、精确色值或每帧身份的保证。

## 请求快照与历史

`production_contract` 记录已交接蓝图及design_hash/source_signature、视图模板/version/hash、共同设置、Skill与文件摘要、明确采用原图/版本和当时审阅记录、逻辑模型映射与真实适配器参数结构指纹。规范化payload指纹与可复原图片清单继续记录。

Qwen沿用真实尺寸/messages/Base64/异步契约；Seedream沿用2K/PNG/URL同步契约。不虚构“三视图”模型字段或3D锁定能力。每个模型的原参数验证、图片预算、项目/模型范围、暂停、未知提交锁仍在执行代码。

已真实提交的任务只查原编号，原请求、原图、批准和首版历史不重算/改写。不迁移老数据或把Skill改版自动作用为新批准。旧引用保留；随后新请求若规范过期则要求显式重审/更新，而非静默换成最新版。

## 验证

```sh
python3 -m unittest discover -s tests -p test_asset_templates.py -v
python3 tests/browser_asset_templates.py
```

测试Skill和交接仅在临时目录中合成，不改实际三个Skill。覆盖缺失交接不猜外观、来源/版本/路径、适用主体字段、非人完整正面入口、单图/中性/完整范围、母版阶段、项目隔离、上下文不倾倒、指纹变化、历史不改写及暂停零预算/零真实模型请求。
