# 图片分镜与Wan3音频核对

2026-10-28。图片为分镜核心，文字是可编辑的画面/动作/对白说明。无图时显示真实空状态，不用CSS装饰冒充模型画面。

## 图片选择

本轮采用 Qwen Image3.0 标准版：同一模型支持生成/编辑，最多3张参考图，单次输出1张，原价输出¥0.18+输入参考每张¥0.02。Pro的1K输出¥0.25；万相2.7Image输出¥0.20且支持更多参考与顺序组图，可作后续对照。主张来自 [官方图片价格](https://help.aliyun.com/zh/model-studio/model-pricing) 与 [官方图像选择](https://platform.qianwenai.com/docs/developer-guides/getting-started/image-models)，不使用CLI误标的“CNY/1M tokens”作为图像计费依据。

[官方异步图像API](https://platform.qianwenai.com/docs/api-reference/image-generation/qwen-text-to-image-30-async)及已安装官方image skill的执行代码共同核对：`POST https://maas.qianwenaiapi.com/api/v1/services/aigc/image-generation/generation`，异步头，`input.messages`包含参考image对象和text对象，`parameters.size/n/prompt_extend/watermark`；保存task_id，`GET /tasks/{id}`只查询。图片编辑参考格式交叉核对 [官方编辑指南](https://platform.qianwenai.com/docs/developer-guides/image-generation/image-editing)。

模型图下载到忽略的assets项目子目录，SQLite存本地引用、供应商URL、任务ID、预占、用量、提交内容快照与来源版本。URL失效前下载，失败只重查/重下原结果，不重复付费生成。没有实际账单证据时actual_cost保持null。

## 有限授权

全局付费开关已经移除。授权文件位于仓库外私密目录，绑定具体数据库文件和项目ID，限定模型、有效期、任务次数及预算。unknown提交占用次数和预算。用户审阅图片前，视频次数可设为0，从后端拒绝视频提交。授权不自动扩大，不等于其他项目获准。

## Wan3音频

[Wan3官方接口](https://platform.qianwenai.com/docs/api-reference/video-generation/wan30-video/create-task)支持原生音画生成；字段为`parameters.audio`，默认true，false时无音轨。此字段不是Seedance的generate_audio。声音开关同价。可通过提示词描述对白与音效，但准确台词、同一声线和主体口型必须真实验收，不能以“模型支持”代替效果通过。

首/尾帧模式可输出声音，但不可混入reference_audio；使用参考音频时走全模态参考组合。真实成片必须用ffprobe检查音轨，并听验对白、声线和音效。若失败，再在授权预算下考虑独立TTS和混音，不自动花钱重试。
