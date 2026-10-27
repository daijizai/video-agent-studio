# 图片429限流：证据与边界

## 本次可证实的内容

- 错误码为 `Throttling.RateQuota`，HTTP429。官方调用日志显示拒绝响应很快、无用量条目；失败请求的具体requestId及时间保留在本机任务rejection_evidence，不公开用户账号日志。
- 本地记录在约3秒内发出3个图片创建请求，前两个已受理，第三个被拒；当时前两个尚未被查询为终态。不能据此确定供应商当时真实运行并发。
- 模型公开规格为20 RPM、10并发、异步队列200；CLI模型元数据仅显示RPM20。当前可见提交量并未达到20/分钟，因此不能断言“超过公开20 RPM”或“超过公开10并发”。
- `RateQuota`官方定义属于调用频率RPS/RPM限制，区别于余额/总额度耗尽。不能仅因429建议用户充值。
- 首次失败响应的详细message、Retry-After及限流头当时未保存，因此无法还原具体RPS窗口、账户共享流量、试用层/动态阈值或服务容量是否参与。没有找到证明图片GET任务查询与创建POST共用同一额度的明确文档；保持未知。

## 改进

- 图片创建采用单在途任务，创建请求至少间隔3.2秒，平滑到20RPM以下。这是保守措施，不宣称账号只有1并发。
- 查询只针对已有任务ID，8秒起步、错误指数退避至60秒，隐藏页面30秒，终态停止；无ID unknown不可自动重提。
- 新错误保留脱敏message、requestId及白名单Retry-After/X-RateLimit头，绝不保留Authorization、Cookie或APIKey。
- 只有明确429、无任务ID且已由官方调用日志核对“未受理、无用量”的请求可记为rejected，保留原请求和证据；不把超时unknown当作未收费。rejected不算已生成图片；没有自动扩大受理图片次数或预算。
- 不通过额外付费请求复现问题。必要时可携带requestId向官方支持查询实际触发维度，但发送支持工单需另获用户授权。

官方依据：[模型规格](https://www.qianwenai.com/models/qwen-image-3.0)、[错误码](https://help.aliyun.com/zh/model-studio/error-code)、[限流应对](https://help.aliyun.cn/zh/model-studio/rate-limiting-best-practices)。
