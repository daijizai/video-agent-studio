# 本机 FFmpeg 安装与验证

日期：2026-10-28。用户已明确授权安装。

无 Homebrew；系统 `/usr/local/bin` 由 root 管理，不可写。工具安装到已在 PATH 中的用户目录 `~/.local/bin`，没有修改系统目录或 shell 配置。

- FFmpeg：npm `ffmpeg-static@5.3.0` 提供的 FFmpeg 6.0、arm64 构建。
- FFprobe：npm `@ffprobe-installer/darwin-arm64@5.0.1` 提供的原生 arm64 构建。
- npm 注册表完整性校验自动进行。这是已验证可用版本，不宣称是 FFmpeg 最新版本。
- 二进制不进入仓库，不在仓库中再分发附带编解码库。

验证包括 `ffmpeg -version`、`ffprobe -version`、两个合成色卡+音轨镜头、实际运行 `assemble.py` 拼接及烧录SRT、用 ffprobe 检查输出时长与音视频流。测试材料位于系统临时目录，不是AI生成，也不代表模型效果。
