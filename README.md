# 拾影视频与图文下载

## Android 手机本地版

新安卓工程独立位于 `android/`，与 `desktop/` 分开维护。在拾影任务界面显示解析状态与作品信息，完整抖音网页仅在内部 WebView 处理；原生下载通过 MediaStore 保存到手机相册，不依赖远程解析服务。支持视频、图文、部分失败补下与浅色/暗色/跟随系统主题。

构建命令：`.\android\build_android.ps1`。APK 输出到 `android/releases/`；安装、签名备份和使用说明见 [android/README.md](./android/README.md)，实机验收见 [android/VALIDATION.md](./android/VALIDATION.md)。原 `mobile/` 和 `backend/` 保留为旧远程方案，不是新 APK 的运行依赖。

## Windows 桌面版

新增按“任务工作台”设计实现的 PySide6 桌面软件。运行方式、EXE 打包和使用说明见 [WINDOWS_GUIDE.md](./WINDOWS_GUIDE.md)。

Windows 1.3.0 支持自动识别视频与图文，图文按顺序保存 JPEG/PNG/WebP 图片、文案和结果清单，支持部分完成、只重试失败项与取消后继续。下载文件夹版见 `dist/1.3.0/Shiying/`，发布压缩包位于 `dist/Shiying-1.3.0-windows-x64.zip`。

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r desktop\requirements.txt
.\.venv\Scripts\python.exe -m desktop
~~~

项目现在包含：

- `mobile/`：按照产品原型实现的可安装 PWA，并提供 Capacitor Android 封装入口。
- `backend/`：面向 Linux 的 FastAPI、Playwright、yt-dlp 下载后端。
- `douyin_downloader.py`：保留的桌面命令行下载工具。
- `docker-compose.yml`：前后端一键部署配置。

完整的安装、使用、Android 打包和 Linux 部署步骤见 [APP_GUIDE.md](./APP_GUIDE.md)。

## 命令行下载器

基于 `yt-dlp` 的单视频下载脚本。默认先尝试不使用 cookies，并通过 `curl_cffi` 模拟浏览器网络指纹，以提高匿名请求的成功率；被抖音风控拦截时，可直接读取本机浏览器登录态，无需维护 `cookies.txt`。

## 安装

```powershell
python -m pip install -r requirements.txt
```

建议经常升级 `yt-dlp`，因为抖音页面和接口会变化：

```powershell
python -m pip install -U yt-dlp "curl-cffi>=0.11,<0.16"
```

## 使用

默认匿名下载，不读取 cookies：

```powershell
python douyin_downloader.py "0.74 复制打开抖音…… https://v.douyin.com/In8WtWqK4bY/"
```

指定保存目录：

```powershell
python douyin_downloader.py "https://v.douyin.com/In8WtWqK4bY/" -o D:\Videos
```

如果匿名请求被抖音风控拦截，可以直接读取本机浏览器登录态，无需手工导出 `cookies.txt`。先用对应浏览器打开一次抖音（不一定需要登录），然后执行：

```powershell
python douyin_downloader.py "分享文本或链接" --browser edge
```

也支持 `chrome`、`firefox`、`brave`、`chromium`、`opera` 和 `vivaldi`。读取失败时可关闭对应浏览器后重试。

Chrome/Edge 在 Windows 上运行时通常会锁定 Cookie 数据库。如果出现 `Could not copy Chrome cookie database`：

1. 完全退出 Chrome，包括系统托盘中的 Chrome 和后台进程。
2. 再执行下载命令；或者改用当前未运行的 Edge/Firefox。
3. 如果抖音打开在非默认配置中，可显式指定 Profile：

```powershell
python douyin_downloader.py "分享文本或链接" --browser chrome --browser-profile "Profile 1"
```

兼容原来的 cookies 文件方式：

```powershell
python douyin_downloader.py "分享文本或链接" --cookie-file .\cookies.txt
```

## 关于“完全免 cookies”

匿名模式确实不会加载 cookies，但无法保证在所有 IP、地区和时间都成功。抖音的服务端可能针对请求频率、IP、TLS 指纹或登录状态触发验证码/风控。可靠的优先级通常是：

1. 使用最新版 `yt-dlp` + `curl_cffi` 匿名下载。
2. 降低请求频率，避免代理或机房 IP。
3. 匿名模式失败时用 `--browser` 自动复用浏览器登录态。

不要把 cookies 提交到 Git，它相当于账号登录凭证。

## Chrome DPAPI 解密失败

新版 Chrome 可能启用 App-Bound Encryption，使 `yt-dlp` 无法直接解密日常浏览器的 cookies。出现 `Failed to decrypt with DPAPI` 时使用：

```powershell
python douyin_downloader.py "分享文本或链接" --browser-session chrome
```

程序会打开一个独立 Chrome 窗口约十秒，让浏览器自己完成抖音验证，再使用临时 cookies 下载。临时导出文件会在下载后删除；独立浏览器配置保存在项目的 `.browser-session` 目录并被 Git 忽略。
