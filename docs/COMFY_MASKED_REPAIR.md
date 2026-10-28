# 本机局部画面修复：可选模板与验证

状态：保留为非默认本机模板；普通镜头审阅“修复画面”默认已切换[Seedream编辑](SEEDREAM_EDIT_ADAPTER.md)。本模板仍保留正式HTTP路由和图片任务分派；**真实模型效果未验**。实际项目暂停、原成片与审批保持。未安装节点、下载权重或提交真实prompt；8766可为加载代码重启，8188不自动启动。

## 首模板

`masked-repair-sd15@1`：原图PNG＋同尺寸黑白遮罩＋局部描述，执行固定SD1.x潜空间遮罩修复；白色修改、黑色保留。8种核心节点，20步Euler/normal，CFG7，batch1。CheckpointLoaderSimple→CLIPTextEncode→VAEEncodeForInpaint→KSampler→VAEDecode→SaveImage。LoadImageMask固定red通道，避免alpha遮罩反向含义混淆。解码后将修改区域合成回原图，黑色区域RGBA像素保持原值；不能保证区域边缘自然或修改语义正确。

首版只接受8bit非交错灰度/RGB/RGBA PNG，64–2048像素、8的倍数，20MB以内。遮罩须不透明且同时含纯黑/纯白；不接受全白、全黑、灰阶/羽化、索引色、透明色块或动画。无需新增Python依赖。JPEG及画布绘制可后续扩展，不能谎称当前支持。

## 文件与依赖

- `comfy_templates.py`：版本化清单、固定图和参数校验；禁止用户传节点、模型路径或完整工作流。
- `comfy_assets.py`：项目路径限制、PNG完整性/解码限制、归档哈希和精确遮罩合成。
- `comfy_executor.py`：RepairService，直接使用现有state/revisions SQLite结构，任务进入`image_tasks`，外部调用费0但不等于设备成本0。
- `static/comfy-ui.js/css`：`ComfyRepairUI.mount(container,{state,api,refresh,ready,paused,approved})`，由普通视图的“修复画面”按需挂载，查询只恢复原任务；前台只选择镜头、拖动框选区域、描述修改和对比候选，不展示节点、模型路径、seed或机器prompt。支持键盘框选；遮罩在后台交互中生成，用户无需制作技术性遮罩文件。未就绪仅显示“局部修复暂不可用”，详细诊断由开发者接口承接。
- `tests/test_comfy_repair.py`：临时数据库、随机loopback端口、模拟权重和HTTP执行器；不连接真实ComfyUI。

宿主通过`STUDIO_COMFY_PROFILE`环境变量指向本机私有JSON档案（不入Git）；默认无档案，ready=false。必须提供经审阅的运维档案：`architecture=sd15`、`checkpoint_path`、`checkpoint_sha256`、`comfy_root`、`core_nodes_sha256`、`comfy_version`。它是宿主可信配置，不允许从网页请求赋值。权重须是兼容的SD1.x完整safetensors checkpoint，位于该ComfyUI的models/checkpoints目录；本轮没有选定/下载/验证实际模型。现有Z-Image的UNET/CLIP/VAE拆分链不能直接冒充该checkpoint。

预检校验本地文件摘要、执行器版本、节点输入契约、核心模块来源和模型枚举。这些校验不是远程执行器的密码学证明，也不能代替运行资源和实际效果验收；要求宿主配置指向同一个本机ComfyUI安装。自定义节点或monkey patch需要另行审阅，不能依靠object_info字符串证明安全。

本轮只读访问127.0.0.1:8188的system_stats和节点元信息，结果为Connection refused。真实模型/节点/性能均未确认，不自动启动服务。

## 已实现的公共集成

server.py在全局LOCK之外执行修复网络操作；RepairService的SQLite短事务与原HTTP写入口共享同一RLock。server.save对HTTP状态额外执行事务内版本比较并更新写入版本，拒绝陈旧快照覆盖。网络上传等待期间另一HTTP请求仍可保存项目标题；隔离测试验证任务编号和并行编辑同时保留。其他既有供应商提交仍沿用原串行处理，本次只迁移新增修复路径。

正式同源POST `/api/comfy/{action}`映射以下方法；preflight/diagnostics为GET：

| action | 方法与输入 |
| --- | --- |
| preflight | 产品用`public_preflight()`，只读；开发者才可用完整`preflight()`，不要暴露运维路径到产品UI |
| mask | base64严格解码并限制HTTP体积，`import_mask(project_id,revision,shot_id,bytes)`；暂停时允许本地准备素材，不生成 |
| begin | `begin(project_id,revision,shot_id,source_url,mask_url,values,request_id)` |
| execute | `execute(project_id,task_id)`，只领取一次已持久化意图 |
| poll | `poll(project_id,task_id)`，仅查询原编号或重归档 |
| adopt | `adopt(project_id,revision,task_id,candidate_sha256,source)`；人工明确点击，不自动调用 |
| reconcile | `reconcile(project_id,task_id,prompt_id)`；仅凭执行器原图摘要与studio_task_id证明后补关联，不能猜ID或重新生成 |

模块层每次绑定project_id，宿主入口和实际生成/采用门禁核对当前工作空间项目，拒绝旧页面跨项目操作，沿用Origin与revision检查。mask路由单独限制28MiB JSON体积，其余保留2MB上限；base64严格解码，原始PNG限制20MiB。

默认门禁用`generation_scope.is_paused/check`和`workflow_state.valid_approval`，费用类别固定image，模型授权标识`comfy-masked-repair-sd15-v1`。原有图片供应商授权不自动涵盖这个标识。首次执行需要独立、明确、有限授权；`budgets authorize --model comfy-masked-repair-sd15-v1 --local-repairs N`显式指定1–100次（还须沿用明确的图片/视频金额与source参数）。local_repair_grant记录原任务基线；未知/失败/完成均占本轮次数，明确rejected除外。模型范围未批准或次数不足即拒绝。预算编辑不自动恢复暂停，本轮未向实际项目写授权。execute重检授权时排除自身已预占任务，避免有限次数被重复计算；仍检查其他在途任务与原批准版本。

`/api/image/poll`在进入原全局锁处理前按provider分派修复任务；自动轮询包含archive_pending，查询不会交给Qwen/Seedream。`uploading/archive_pending`已加入公共图片重复门禁、扩额检查和预算live集合；`adopted`是已完成历史图像任务。旧供应商结果查询不会覆盖已采用的修复候选。普通视图只显示人话状态，完整模板/依赖诊断放开发者诊断页。

## 恢复与审核

提交意图与输入快照先落盘；再上传本机素材、请求prompt。已领取的上传任务重启后不能重新领取，须核对原请求；prompt结果不明确标unknown，不自动重发。已知ID恢复history/queue查询；history缺失且队列找不到时保留unknown。归档失败保持archive_pending，重试只GET原产物，不POST prompt。

候选归档完成不替换原图。人工采用保留历史原图和原审批快照，替换当前图片引用并清除当前批准，成片文件与既有视频记录不动。采用不是质量批准，须再次走现有分镜审阅。尚不实施删除、批量抽卡、自动质检通过或人物一致模板。

缓存为每个任务的不可替换输入快照与结果归档，没有跨任务自动复用；随机种子和依赖摘要记录在账本。暂不做跨请求去重缓存，以免跳过有限授权或复用未经确认的候选。

## 验证

`python3 -m unittest discover -s tests -p 'test_*.py' -q`

`node --test tests/storyboard_checks.test.js`

可复验的普通视图隔离环境：`python3 tests/serve_comfy_review_fixture.py`，只模拟生成，Ctrl-C自动关闭两临时服务并清理数据库。

覆盖preflight→批准/授权→持久化意图→一次提交→原ID查询恢复→候选缓存→人工采用及审批失效；暂停、额度、路径越界/符号链接、跨项目、陈旧版本、未知重复和归档失败只下载。模拟HTTP处理器尝试取得SQLite写事务，验证远程请求期间DB无写锁。模拟结果只证明软件契约，不证明真实生成质量。

浏览器已通过正式普通视图、正式修复HTTP端点与模拟执行器验证：框选＋描述→一次提交→原任务查询→候选对比→人工采用→“画面待确认”，完整模型/节点/prompt均不出现在普通视图。未就绪与无原图显示真实不可用状态。所有生成测试不连接实际工作台数据或真实模型。

最终验证：完整Python回归通过（补充有限次数授权后118项，含继承套件重复发现）；整理发现方式后局部修复专项35项全部通过。现有分镜JS检查10项通过。8766重启后API ready=false、quality_verified=false、generation_paused=true；仍选中项目3，三项目state原始JSON哈希逐一与重启前相同。
