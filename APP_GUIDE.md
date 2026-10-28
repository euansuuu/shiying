# 视频下载 App：安装、使用与部署

项目包含三种使用形态：

- `mobile/`：React PWA，可直接安装到 Android、iPhone 和电脑桌面。
- Capacitor：把同一套前端封装成 Android 原生工程。
- `backend/`：FastAPI + Playwright + yt-dlp Linux 下载后端。

## 1. 本地启动

### 启动后端

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\backend\requirements.txt
$env:BROWSER_CHANNEL="chrome"
$env:BROWSER_HEADLESS="false"
uvicorn backend.app.main:app --reload --port 8000
```

后端健康检查：<http://localhost:8000/health>。

### 启动 App

新开一个终端：

```powershell
cd .\mobile
npm install
npm run dev
```

浏览器打开 <http://localhost:5173>。查看带演示任务的原型页面可打开：

```text
http://localhost:5173/?demo=1
```

## 2. App 使用方式

1. 在抖音复制分享文本或分享链接。
2. 打开“视频下载”App。
3. 点击剪贴板按钮，或长按输入框粘贴。
4. 点击“解析视频”。
5. App 会依次显示等待、解析、获取浏览器会话和下载进度。
6. 任务完成后点击右侧下载按钮。

Android 安装 PWA 后，可以在抖音的系统分享面板里选择本 App；不支持分享目标的浏览器仍可使用复制粘贴。

## 3. 安装为手机 PWA

PWA 必须通过 HTTPS 部署，`localhost` 除外。

### Android Chrome

1. 用 Chrome 打开部署地址。
2. 点击右上角菜单。
3. 选择“安装应用”或“添加到主屏幕”。
4. 安装后会作为独立 App 启动。

### iPhone Safari

1. 用 Safari 打开部署地址。
2. 点击底部分享按钮。
3. 选择“添加到主屏幕”。
4. 从桌面图标启动。

## 4. 打包 Android APK

需要先安装 Android Studio、Android SDK 和 JDK 17，然后执行：

```powershell
cd .\mobile
Copy-Item .env.example .env
```

编辑 `.env`，填写线上后端地址：

```text
VITE_API_BASE_URL=https://video.example.com
```

创建并同步 Android 工程：

```powershell
npm install
npm run cap:add:android
npm run cap:sync
npm run cap:open:android
```

在 Android Studio 中：

1. 等待 Gradle 同步完成。
2. 调试包选择 `Build > Build APK(s)`。
3. 正式发布选择 `Build > Generate Signed App Bundle or APK`。
4. 使用自己的签名密钥生成 AAB/APK。

iOS 原生包需要 macOS、Xcode 和 Apple 开发者账号；PWA 不需要这些条件。

## 5. Linux Docker 部署

服务器建议：Ubuntu 22.04/24.04、2 核 CPU、4 GB 内存、20 GB 可用磁盘。

安装 Docker 后，将项目上传到服务器：

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

访问：

```text
http://服务器IP:8080
```

视频、任务数据库和浏览器 Profile 保存在 Docker 卷 `video_data` 中。默认浏览器并发为 1，避免多个任务同时占用同一 Profile。

## 6. 配置 HTTPS

生产环境必须使用域名和 HTTPS，否则手机不能可靠安装 PWA，也不能使用剪贴板等安全接口。

推荐在 Docker Compose 前增加 Caddy、Traefik 或宿主机 Nginx。宿主机 Nginx 示例：

```nginx
server {
    listen 80;
    server_name video.example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

然后使用 Certbot 申请证书：

```bash
sudo certbot --nginx -d video.example.com
```

## 7. 生产环境注意事项

- 当前版本是单节点 MVP，任务在后端进程内执行，适合个人或小规模使用。
- 多用户部署应把任务执行迁移到 Redis + ARQ/Celery Worker。
- 视频文件应迁移到 OSS/COS/S3，并返回短期签名地址。
- 增加登录鉴权、IP 限速、每日配额和文件自动过期清理。
- 只允许抖音域名，禁止把接口变成任意 URL 下载器。
- 云服务器机房 IP 可能触发抖音风控，应先验证目标服务器网络。
- 浏览器 cookies 和 Profile 属于敏感凭证，必须加密并禁止写入日志。
