# 本地音乐素材

工作空间和项目「工具与设置」中的「音乐素材」进入 `/music.html`。
点击启动后，工作室运行独立的 go-music-dl 服务，固定监听 `127.0.0.1:8767`。
搜索、试听、下载沿用上游界面；不自动选择歌曲，不自动混音或修改项目。
音乐可下载不代表获得发布授权。

## 本机安装

当前固定版本：上游 v1.1.3，macOS ARM64。
从 https://github.com/guohuiyuan/go-music-dl/releases/tag/v1.1.3 下载
`go-music-dl_darwin_arm64.tar.gz`，校验 SHA256：
`15f684d095f84350847cc4f35db2353400480c22cb87c83b75dd36fbbf66ce02`。
将 `music-dl`、LICENSE 放在 `data/music-service/`，保留可执行权限。
其他平台需下载相应发布包并核对该平台校验和。

运行目录、日志、歌曲、Cookie 与数据库全部在 Git 忽略的 `data/music-service/`。
默认歌曲目录为 `data/music-service/data/downloads`，用户可在上游设置里更改。
工作室不会把 MiniMax、方舟或千问密钥传给音乐进程。
上游 desktop 模式仅绑定回环地址，不带管理登录；请仅在自己的本机使用。
服务可通过页面再次启动；工作室重启会检测仍在运行的音乐进程。
上游 AGPL-3.0 代码作为独立发布程序运行，未复制到工作室源码中。

故障检查：`data/music-service/service.log`，以及 8767 端口是否被占用。
当前接入不提供开机自启动，不调用音乐项目的视频生成或远程签名服务。
