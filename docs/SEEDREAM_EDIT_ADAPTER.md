# Seedream 框选编辑：默认路径与验收

状态：用户已选择 Seedream 直连编辑，现已接为正式“修复画面”的默认后端；**真实编辑API效果未验**。素材库/工作空间原有入口保留，本地模板保留原`/api/comfy/*`及显式backend=local非默认入口。允许重启8766加载代码，不解除项目暂停。本地SD1.5下载路线已取消，不下载权重、不购买Comfy Credits、不创建托管GPU。

## 已核实契约与实现

固定模型沿用`ark_provider.IMAGE_MODEL`：`doubao-seedream-5-0-flash-260915`，北京`POST /api/v3/images/generations`，既有`ARK_API_KEY`与安全transport。原图使用`image="data:image/png;base64,..."`，只在服务端读取当前项目受限素材并构造；不把localhost/media地址交云端，不公开文件目录、不创建公网图片托管服务。请求发送时完整原图会交给火山方舟处理；后续真实运行必须有对应图片/模型/预算/执行授权。

用户只提供原图框选和自然语言描述。后台用`floor(px/边长*1000+0.5)`并clamp到0–999生成`<bbox>x1 y1 x2 y2</bbox>`，对应官方示例；左上/右下顺序及坐标范围严格检查，过小到归一化后退化的框拒绝。普通描述不能插入`<...>`技术标记。默认2K PNG、url同步响应、watermark=true、stream=false、layer_decomposition=false；不传Flash不支持的组图开关，不暴露seed/ControlNet/内部采样参数。

首版只接受20MiB以内8bit非交错灰度/RGB/RGBA PNG，边长15–4096、最多16777216像素、宽高比1/16–16；这是工作台安全子集，官方输入支持更多格式及30MB上限。以PNG容器CRC、zlib像素长度和过滤标记校验文件，无新增Python依赖。2K长边可能2816px，已独立支持，不沿用本地模板的2048px边长限制。JPEG/WebP需另行受控解码/格式扩展，不能改后缀冒充支持。

**bbox只是空间引导。** 候选按API返回整图原字节归档，不裁切、不缩放、不合成；账本固定`outside_pixels_locked=false`。普通UI已将原先“保留其余画面”改成“尽量保留其余画面，候选可能改变框外内容”，并提供整图前后对比。没有声称框外像素不变，也未实现硬mask或边缘融合。如果未来做确定性合成，必须额外定义同尺寸/缩放/几何对齐规则、混合区域与边界接缝验收，不能直接复用模型bbox当硬mask。

## 持久化与预算

`SeedreamEditService`复用`RepairService`的SQLite事务、共享短锁、任务查询与安全原子归档。宿主传同一LOCK和current_project检查；网络POST与下载均在事务/锁外。provider=`seedream-edit`，kind/cost_category=image，进入image_tasks。当前刊例价输入图免费、输出每张¥0.12，单次预占¥0.12，不继承Comfy本机0元价格；实际结算字段保持None，不能用刊例价冒充账单。

begin：当前项目＋revision＋当前源图有效人工审批＋源文件SHA256＋暂停＋图片预算/模型范围全部校验，才归档不可变源图并写提交意图。保存request_model、完整非二进制请求参数、原图哈希/尺寸/归档路径、像素区域及归一化bbox、内容/审批/授权/价格快照、模板版本和完整实际payload摘要；base64原图不在SQLite重复保存，可从不可变源图重建。密钥只在内存headers中，不入任务、异常或导出。

execute：只领取submitting一次，以uploading状态落盘，再在锁外进行一次同步POST。重新核对原审批/图片、请求摘要、模型、预算和授权版本（排除自身预占，避免重复计费）。网络异常或超时为unknown，无异步任务ID，禁止重发。多图/数量异常保留unknown，不自动采用首图，并按实际返回条数增加保守预占等待核对。

成功取得唯一合法URL后先把结果持久化为completed，quality/review仍unreviewed，再下载。下载失败保留completed+download_error；poll只重下载原结果，不调用新生成。URL需HTTPS且在现有供应商域名范围，不向下载域名转发Ark密钥，禁止重定向。输出URL官方有效期24小时；过期后保留原失败记录，不静默重新生成。

采用：已归档候选＋候选哈希＋同一源图哈希和审批快照＋当前revision重新校验；人工采用保留原图/原审批历史，切换当前图片并清除批准，要求重新审阅。旧成片保持。晚到的并发下载在短事务内只能发布一次，不能覆盖已经采用的候选文件。

## 已完成的公共集成

1. 不改用户操作方式。现有画布框选已提交原图像素坐标`region={x,y,width,height}`和description，不再只把黑白mask文件传给本地模板；本地模板为开发者显式可选后端，原诊断入口保留其真实未就绪状态，普通默认编辑不显示本地强度参数。
2. 新`/api/repair/preflight`和`/api/repair/{begin,execute,poll,adopt}`默认选SeedreamEditService；后续任务按provider而非请求默认后端分派。旧`/api/comfy/*`仍为本地模板。素材库kind=asset_image优先走原素材服务，不被编辑适配器领取。seedream-edit没有异步prompt_id/reconcile或mask上传，轮询只恢复同步产物下载。
3. UI readiness只表示密钥配置可构造请求，`api_verified=false`、`quality_verified=false`；不将配置就绪等同于实测可用。继续以项目pause、图片授权和批准源图禁用提交。preflight分别返回配置ready和execution_allowed；submitting原意图的resumable_task_ids会排除自身预占后单独检查，避免剩余预算0导致原任务无法恢复。没有真实执行许可时保持禁用，不为演示解除暂停。
4. 公共图片重试/账本/候选渲染按provider分派。completed但没有candidate_local时只重下载，completed待审候选不能静默成为当前分镜；adopted才成为当前图。普通视图不展示坐标token、模型技术字段或密钥诊断。
5. 生成旧供应商结果“是否当前”判断必须把未采用的seedream-edit候选排除、已adopted候选纳入，避免旧下载覆盖新图。沿用项目修订版本与共享短锁，不能把网络调用包进全局锁。
6. begin签名：`begin(project_id,revision,shot_id,source_url,region,description,request_id)`；其余execute/poll/adopt签名与本地模板一致。候选尺寸读取实际结果，不假设2K恒为2048x2048，不承诺与原图同尺寸。

## 验证与来源

`python3 -m unittest discover -s tests -p 'test_seedream_edit.py' -v`

覆盖坐标边界、data URI、¥0.12图片预占、模型/暂停/预算门禁、源审批哈希、同步持久化在下载前、超时unknown防重、多图异常、下载恢复、密钥不泄露、跨项目/路径越界、长边2K输出、采用后审批失效与旧成片保留。全部用假密钥、mock transport和临时SQLite，不连接真实模型。

- [官方交互编辑指南](https://ark.volcengine.com/region:cn-beijing/docs/seedream-5-0-pro-editing-guide)：point/bbox、0–999、引用图次序、提示词与交互示例。
- [图片生成API](https://ark.volcengine.com/docs/image-generation-api)：image data URI、输入限制、Flash单图/非流式、size档位、layer_decomposition=false、PNG及同步响应、URL有效期。
- [模型价格](https://ark.volcengine.com/docs/model-pricing#457edfd0)：Flash输入免费、输出¥0.12/张；2026-10-29核对。

文档通过官方公开Markdown正文只读读取。arkcli状态命令在业务前触发旧状态迁移尝试并被沙箱阻止，未覆盖原配置；没有升级、登录或绕过该迁移写入，改用公开文档HTTP读取。

独立适配14项测试与正式HTTP集成测试通过；完整Python回归163项通过（后续恢复预占专项另验），现有分镜JS检查10项通过。浏览器已用正式普通视图和正式HTTP路由走通模拟编辑、整图对比、人工采用及审批失效；没有调用真实模型。可用`python3 tests/serve_seedream_edit_fixture.py`启动隔离复验环境，Ctrl-C清理临时数据库与端口。

最终集成验收：完整Python回归163项通过，最后的恢复预占/任务类型专项34项通过；分镜JS10项与密钥扫描通过。8766加载新代码后默认backend=seedream、ready=true（仅密钥配置）、execution_allowed=false、api_verified=false、quality_verified=false；本机模板ready=false。实际仍选中项目3，8镜、0图片/0视频、生成暂停，三项目原始状态哈希与重启前完全一致。
