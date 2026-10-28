# 拾影 Android 本地版方案

日期：2026-10-23。状态：已按此方案在独立 `android/` 目录实现本地版并生成签名 APK；实际测试范围见 [android/VALIDATION.md](./android/VALIDATION.md)。以下保留架构取舍，构建与使用以 [android/README.md](./android/README.md) 为准。

> 0.1.4 实现更新：用户停留在拾影任务界面，完整作品网页只由内部 WebView 解析。视频使用官方手机分享页并保留 SSR 参数，图文延续已验证的桌面数据解析；不提供人工登录页。解析前台累计超时 60 秒，后台暂停；受限时显示失败。下文保留最初方案的取舍，当前使用方式以 android/README.md 为准。

## 1. 结论

可以开发直接安装到安卓手机的 APK，把作品解析、登录会话、媒体下载、任务记录与文件保存放在手机本地。使用时无需部署后端、保持电脑开机或配置解析服务地址；下载仍需联网访问抖音页面和媒体资源。

针对当前仓库，优先建议保留 mobile/ 的 React + Capacitor 界面，在 APK 中增加 Kotlin 本地解析与下载内核。纯 Kotlin + Compose 也是可行路线，但需要重建现有移动界面；它不会消除抖音网页在 WebView 中的兼容问题。

平台提供所需构件，不等于已经证明目标作品可在安卓下载。首要验证项是：真实手机的应用内 WebView 能否打开作品、完成人工验证，并取得与作品 ID 匹配的媒体信息。

## 2. 当前项目与目标的差异

| 部分 | 当前 Windows 1.3.0 | 当前 mobile/ | 安卓本地版 |
| --- | --- | --- | --- |
| 界面 | PySide6 原生窗口 | React 页面 + Capacitor 配置 | APK 内置 React 资源，延续拾影图标与蓝青主题 |
| 解析 | Playwright 控制本机 Edge/Chrome | 调用后端创建任务 | Kotlin 管理专用 WebView，会话和识别在手机完成 |
| 下载 | Python requests 写本机文件 | 后端下载后再提供文件链接 | 原生 HTTP 下载到手机，进度由本地事件返回 |
| 验证 | 独立浏览器窗口 | 现有移动端没有等价的本地处理流程 | 应用内显示网页，用户手动完成后继续 |
| 记录 | SQLite + 文件结果清单 | 后端任务列表与轮询 | 本地数据库记录任务、图片结果与 content URI |
| 服务依赖 | 不需要自建远程服务 | 依赖 FastAPI 服务 | 不需要自建或第三方解析服务 |

代码依据：mobile/src/api.ts 调用 /api/v1/jobs；App.tsx 查询后端进度，并在设置中显示“远程服务”。Capacitor 配置本身只负责封装，不能使这些后端调用自动变为本地下载。

Windows 的作品识别规则、图文顺序、部分完成与补下规则可以沿用，但 Python 下载实现、Playwright 启动、Windows DPAPI 和文件路径操作需要重新适配。[Playwright 的 Android 自动化](https://playwright.dev/docs/api/class-android)依赖 ADB 等开发环境，不适合作为用户独立安装 APK 的运行方式。

## 3. 路线比较

以下投入和取舍为结合本项目的工程判断，不是实测性能结论。

| 路线 | 能否满足手机独立使用 | 复用情况 | 取舍 |
| --- | --- | --- | --- |
| 当前 PWA / 直接封装当前 mobile/ | 当前实现不能满足 | 界面基本不变 | 仍依赖后端，需要替换解析与下载链路 |
| Capacitor + Kotlin 本地内核 | 可以按此目标开发，网站兼容需验证 | 保留 React 界面和移动端构建入口 | 当前仓库优先选择；需要编写原生插件和专用网页界面 |
| Kotlin + Compose 全原生 | 可以按此目标开发，网站兼容需验证 | 复用品牌、规则和测试案例，界面重写 | 只维护 Android 时可考虑；系统能力接入直接，但首期界面工作更多 |
| 手机打包 Python / yt-dlp | 不能直接复用现有 Windows 流程 | 可复用部分 Python 逻辑 | 浏览器、会话、后台任务和文件保存仍需适配，首期收益有限 |
| 手机内运行本地 HTTP 后端 | 理论上可设计 | 较多后端代码可复用 | 多一套运行时与生命周期管理，不作为首版方案 |

推荐的 Capacitor 路线并不需要远程网页托管：构建后的页面资源复制进安卓工程，再通过原生插件调用 Kotlin。[Capacitor 构建流程](https://capacitorjs.com/docs/v7/basics/workflow)、[Android 插件指南](https://capacitorjs.com/docs/v7/plugins/android)支持这一组合。现有项目使用 v7，开发时应保持 Core、Android 与 CLI 版本匹配，不以升级框架为前置目标。

## 4. 本地工作流程

1. 用户粘贴完整分享文字，或从安卓系统分享面板选择“拾影”。只提取并校验抖音作品链接，不自动读取其他应用数据。[Android 分享接收机制](https://developer.android.com/develop/ui/compose/sharing/receive)支持接收分享文本；抖音自身菜单能否直接列出拾影需要实机确认，复制粘贴始终作为入口。
2. Kotlin 创建本地任务，打开专用的“作品解析”网页界面。保留取消、返回任务、继续解析与清除会话操作。
3. 从作品页面初始化数据，或页面自身取得的详情/作品列表 JSON 中，寻找匹配作品 ID 的详情；类型、图片顺序和无地址槽位沿用 Windows 规则。
4. 遇到登录或验证时显示网页，由用户手动处理；未取得信息不能直接断言是验证码。验证后重新检查，超时允许取消或稍后处理。
5. 拿到可用资源后，原生 HTTP 客户端从源站下载。浏览器 User-Agent、Referer 和必要 Cookie 按目标 URL 使用；媒体地址和 Cookie 不出现在任务日志或持久结果清单中。
6. 校验内容、保存结果，更新本地记录与通知。图文单张失败继续后续图片；重试时校验成功文件，只补下失败、缺失或损坏项。

### WebView 解析需要单独验证

WebViewClient.shouldInterceptRequest 是请求处理入口，不能直接等同于 Windows 的 page.on("response")。不能仅凭看到图片 URL 就认为已经拿到完整图文，也不能抓全页 img 标签凑数量。

候选实现：优先读取目标作品的结构化初始化数据；需要监听网页请求时，在受支持的 WebView 中使用 document-start 脚本观察页面的 fetch/XHR 返回数据，并通过受限消息接口提交作品信息。注入前做 AndroidX WebView feature 检测；不支持时明确提示或使用已验证的初始化数据读取分支，不能假装解析成功。

消息接口限定实际需要的抖音 HTTPS origin，校验 sourceOrigin、主框架、任务 ID、作品 ID、结构及大小。用于显示抖音页面的 WebView 与用于显示拾影界面的 Capacitor WebView 分开；外部网页不获得通用文件操作或完整 Capacitor 插件权限。[WebViewCompat 官方 API](https://developer.android.com/reference/androidx/webkit/WebViewCompat)提供文档开始注入、来源限制与消息回调。

此处的脚本观察是待验证的设计，可能受页面实现、Service Worker、跨域/不透明响应或页面防护影响。初始化数据和网络观察均无法取得目标详情时，给出本地解析失败提示，不暗中改用远程解析。

### 登录会话

专用 WebView 的会话留在应用沙箱。不能把手机上已登录抖音 App 或外部 Chrome 当成本应用已登录；首次需要时在拾影网页界面内处理。

使用 CookieManager 按实际请求 URL 获取本应用 WebView 的 Cookie，跨域重定向重新检查，不把拼好的抖音 Cookie 头直接传给其他媒体域。会话清除覆盖专用网页会话和本地临时凭据。[CookieManager 官方 API](https://developer.android.com/reference/android/webkit/CookieManager)描述的是应用 WebView 的 Cookie 管理。

### 后台执行

作品网页解析和人工验证在前台界面进行。取得资源后，下载交给安卓原生任务，并提供可见通知与取消操作；关闭 React 页面不应直接销毁下载任务。

当前实现中，Android 14 及以上对用户主动触发的长传输采用 UIDT Job；Android 10–13 使用原生前台下载服务，不额外引入 WorkManager。任务可能被系统停止，保存进度后由用户返回应用重新解析继续，不能承诺无限后台常驻。地址失效或需要重新验证时提示用户回到应用；不在锁屏后台强行启动验证界面。[UIDT 及兼容方案](https://developer.android.com/develop/background-work/background-tasks/uidt)、[传输任务选择](https://developer.android.com/develop/background-work/background-tasks/data-transfer-options)。

## 5. 文件与手机使用体验

建议首版以 Android 10 / API 29 及以上为兼容基线；这是方案选择，不代表低版本在技术上完全不可支持。系统 WebView 还需要满足所用特性的实际能力检查。

默认以“手机相册可见”为目标：视频写入 MediaStore.Video，图片写入 MediaStore.Images；建议位置分别为 Movies/拾影 和 Pictures/拾影/作品ID，图片仍按 001、002 等原顺序命名。正文和结果清单保存在本地任务数据中，可查看、复制；用户需要完整文件夹时，通过系统文件选择器导出图片、文案.txt 和 manifest.json。导出是复制结果，不重复联网下载。

Android 10 及以上仅操作应用创建的 MediaStore 媒体通常不需要额外存储权限；写入期间使用 pending 状态，校验完成后发布。自选目录导出走 SAF，保存授权的 content URI，不照搬 Windows 绝对路径。不要求“所有文件访问”权限。[MediaStore](https://developer.android.com/training/data-storage/shared/media)、[SAF](https://developer.android.com/training/data-storage/shared/documents-files)。

系统相册的展示、排序和文件管理器行为可能因手机而异；任务内显示的图片原顺序作为依据。卸载应用会移除本地任务数据库和应用会话，已经发布到共享存储的媒体可保留；重新安装后不能承诺无需授权即可自动认领全部旧结果。

界面延续 Windows 的品牌、蓝青配色，以及浅色、暗色、跟随系统设置，改为适合手机的“下载 / 记录 / 设置”底部导航。图文状态保留“已保存 X/N 张”“部分完成”“重试失败项”“继续下载”。图文首版仍只保存静态图片与正文，不增加实况、配乐保存或主页批量采集。

## 6. 开发顺序与验收门槛

| 阶段 | 交付内容 | 必须满足的条件 |
| --- | --- | --- |
| 本机解析验证 | 小型安卓测试包：专用 WebView、目标作品数据获取、本地保存一个视频和一组图文 | 在真实手机上验证短链、视频页、图文页和人工验证；不能只看页面显示成功 |
| 本地内核接入 | 替换 mobile/ 后端 API；本地数据库、原生下载任务、媒体存储与原生进度事件 | 后端不运行时完成全过程，APK 内无运行时解析服务地址要求 |
| 产品功能补齐 | 拾影品牌主题、系统分享、队列、取消继续、图文补下、文案与导出 | 失败、断网、目录授权失效、磁盘不足、进程退出后不丢失已保存结果 |
| 发布验收 | 签名 APK、安装与升级说明、测试报告 | 真机 Wi-Fi/移动网络、锁屏/切后台、代表性 Android 版本；升级保留数据 |

安卓构建需要开发电脑上的 JDK、Android SDK 与 Gradle；这些不是手机用户的运行依赖。用户拿到签名 APK 后按系统安装提示安装，手机端无需 Python、Node、ADB、Root 或单独后台服务。后续 APK 更新需保管同一套签名密钥。[Android 应用签名](https://developer.android.com/studio/publish/app-signing)。

不预估固定开发天数或 APK 体积：先用真实手机验证 WebView 解析通路，再据结果确定适配工作。只会展示界面的 APK、电脑浏览器成功下载、或模拟器运行正常，都不能单独视为安卓本地下载验收通过。

## 7. 本次完成与未验证项

已实现独立安卓界面、本地 Kotlin 内核、专用解析网页、本地任务记录、原生传输、相册保存、导出和签名打包。没有把 Windows 的 Playwright 或远程 FastAPI 打包进 APK。PGEM10 / Android 16 上已验证安装、分享文本、主题切换、媒体写入和取消清理。

真实图文测试暴露的窗口初始化崩溃和官方短链中转拦截问题已修复，并补充短链动态作品 ID 和 modal_id 的回归检查。修复后的完整网站下载与其他系统版本验收仍以测试报告记录为准；不能用编译成功替代下载验收。无远程服务意味着没有自建服务运维负担，但源站网页变化时仍可能需要更新 APK 中的解析实现。
