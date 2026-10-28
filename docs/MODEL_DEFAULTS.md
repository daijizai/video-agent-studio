# 当前默认模型与报价边界

2026-10-28，用户明确选择图片 `qwen-image-3.0-pro`、视频 `wan3.0-video-prime` 为后续默认。标准版保留可选，历史任务按真实请求模型记录，不因切默认而重提或改写。

- [图片Pro官方页](https://www.qianwenai.com/models/qwen-image-3.0-pro)：1K输出¥0.25/张，2K输出¥0.50/张；输入参考每张¥0.02。按官方像素面积档位计价，不使用CLI偶尔误标的每百万token单位。支持的生成/编辑消息schema与异步API已核对；本轮停止后未追加Pro真实出图。标准版输出¥0.18，不能混用。
- [视频Prime官方页](https://www.qianwenai.com/models/wan3.0-video-prime)：480P/720P/1080P分别¥0.45/0.90/1.80每秒；30秒为¥13.50/27/54。图片参考不会增加输入视频秒数，视频参考则需另算，本适配器不开放未核价的参考视频输入。音频字段是audio，明确true时输出有声，开关同价。
- Prime模型与标准版在[官方Wan3 schema](https://platform.qianwenai.com/docs/api-reference/video-generation/wan30-video/create-task)中均有明确定义，使用同一视频合成接口；不是把模型名替换后仍按标准版收费估算。
- 图片Pro公开5RPM，标准版20RPM，使用单在途和平滑提交，不能把低累计生成量误当成不会限流的保证。

新项目默认值不自动分配金额授权。预算只绑定具体项目/数据库，图片和视频不互借。用户暂停后，预算和余额保留，切模型/改预算不恢复执行。当前原始首版为用户阶段性接受，未据此宣称逐字对白、同一声线和每项道具指标客观完美；不再为新增检查发起付费请求。

CLI：`provider configure --provider wan3-prime --image-model qwen-image-3.0-pro`。实际分辨率和声音以项目持久化配置/请求快照为准，默认选择不覆盖已提交任务。
