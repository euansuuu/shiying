# 拾影 Android 本地版

独立安卓工程，最低 Android 10（API 29）。界面、解析、网页会话、下载和任务记录均在手机内运行，不依赖电脑、FastAPI 或第三方解析服务；访问抖音和下载资源仍需要联网。

## 安装

发布 APK：`releases/Shiying-0.1.5-android.apk`。复制到手机后打开安装，按手机提示允许当前文件管理器安装此应用。首次下载时可允许下载通知。解析时停留在拾影界面，不展示抖音完整网页，也不弹出网页登录。

后续更新直接打开新的正式 APK 覆盖安装，无需先卸载。正式版固定使用 `com.shiying.local` 和 `android/.signing/` 的同一发布签名，每次发布递增 versionCode；覆盖升级保留应用记录、设置和会话。若提示签名冲突或降级，不要通过卸载来强行更新，应先检查包名、发布密钥与版本号。

“拾影·测试版”使用独立的 `com.shiying.local.debug`，只供开发测试，与“拾影”正式版分别保存数据，无法相互覆盖。日常安装只使用 releases/ 中的正式 APK。旧测试包曾与正式包同名，可能导致误认为每次安装都会产生新软件。

## 使用

1. 复制抖音完整分享文字，在拾影点击“粘贴”，再点击“解析并下载”。也支持系统分享面板发送 `text/plain` 文本到拾影；抖音自身菜单是否列出该入口取决于其版本。
2. 任务卡显示本机解析状态，取得作品信息后自动展示标题、作者、类型与图文数量并开始下载。完整抖音页面由应用内部独立 WebView 处理，不显示网页或地址栏。解析前台累计最多等待 60 秒；切到后台暂停解析与计时，回到拾影继续。明确需要登录或验证时显示原因并结束解析，不自动打开网页登录。
3. 视频保存到 `Movies/拾影`，图文按顺序保存到 `Pictures/拾影/<作品分组>`。手机相册可查看保存结果。
4. 详情页可复制文案；“导出文件与文案”通过系统目录选择器复制媒体、文案和清单。导出不会移动相册原文件。
5. 图文部分失败时保留已完成项。重试会重新解析地址，核对图片标识、顺序和已保存文件的大小及 SHA-256，再补下缺失项。标识或顺序变化时创建新分组，保留旧文件。

支持浅色、暗色、跟随系统；主题和记录会在重启后保留。解析会话只属于拾影，不能复用手机上抖音 App 或 Chrome 的登录状态。设置中的“保留解析会话”延续已有会话保存偏好；关闭后，在任务结束和下次启动时清除会话。该开关不会自动登录或取得其他应用的凭据。卸载应用会删除应用内记录和会话，相册中已发布的媒体由系统管理。

## 与桌面端分开维护

| 目录 | 用途 |
| --- | --- |
| `android/src/` | 新安卓界面与本地插件类型 |
| `android/native/` | Kotlin 内核、原生工程、Gradle Wrapper |
| `android/native/app/src/main/assets/resolver.js` | 只识别目标作品的网页数据观察脚本 |
| `android/tests/` | 脚本测试，不连接真实网站 |
| `android/.signing/` | 本机发布密钥，已排除版本控制 |
| `android/releases/` | APK 和 SHA-256，已排除版本控制 |
| `desktop/` | 原 Windows 版，安卓开发不依赖此目录 |
| `mobile/`、`backend/` | 旧远程服务方案，不是此 APK 的运行依赖 |

## 本机构建

需要 Node.js 22、JDK 17 或 21、Android SDK Platform 35（基础包）、Build-Tools 35.0.0。仓库固定 Capacitor 7.6.8、AGP 8.7.2、Gradle 8.11.1，并对固定版本的 Capacitor 源码使用 Java 17 编译级别。

在项目根目录运行：

```powershell
.\android\build_android.ps1 -JavaHome 'C:\Environment\Java\jdk-17' -SdkRoot 'C:\path\to\Android\Sdk'
```

也可以设置 `JAVA_HOME`、`ANDROID_HOME` 后直接运行脚本。本工作区已安装的 SDK 会被自动识别。脚本执行 `npm ci`、解析脚本测试、TypeScript/Vite 构建、Capacitor 同步、Kotlin 单元测试、Android Lint、签名发布构建和签名验证，然后复制 APK 到 `android/releases/` 并输出 SHA-256。

首次构建会在 `.signing/` 创建本机 RSA 发布密钥及密码配置，后续构建复用。请将整个 `.signing/` 目录安全备份，勿提交或公开；丢失后无法以同一签名覆盖升级已安装版本。升级应用时还需递增 `native/app/build.gradle` 的 `versionCode` 和版本号。

Maven 使用阿里云公开 Google/Central 镜像并保留官方仓库回退；Gradle Wrapper 仍指向官方分发地址并固定 SHA-256。工作区的已校验本地 Gradle 可加速重复构建，其他机器可使用 Wrapper 下载。

## 检查与实机测试

```powershell
cd android
npm test
npm run sync
.\native\gradlew.bat -p native :app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest
```

调试包使用 `com.shiying.local.debug`，发布包使用 `com.shiying.local`，两者记录和登录状态分开。开发者可使用 SDK 的 ADB 安装调试包和测试包，再运行：

```powershell
adb shell am instrument -w -e class com.shiying.local.HiddenResolverTest,com.shiying.local.LocalStorageTest,com.shiying.local.UiSmokeTest com.shiying.local.debug.test/androidx.test.runner.AndroidJUnitRunner
```

测试手机需要解锁并保持拾影前台；测试过程中临时保持屏幕点亮。测试只清理自己创建的测试记录、图片。HiddenResolverTest 使用本地空白页检查解析视图被主界面覆盖、无障碍隔离、暂停与超时、取消和重试。真实网站下载测试另在 `RealDownloadTest`，必须显式传入 `-e share <作品链接>`；不会自动运行真实下载。真实下载不自动处理登录或验证码，受限作品会失败。实际验收结果见 `VALIDATION.md`。

## 实现与边界

- 界面资源随 APK 安装，没有远程 `server.url` 和服务地址配置。
- 外部作品网页使用主界面后方的独立 WebView，保持正常视口且不设 GONE，以允许页面执行；不接收焦点、不出现在无障碍树中，并取消网页 JavaScript 弹窗。只允许指定抖音 HTTPS 来源向受限消息接口返回目标作品数据，外部页面没有 Capacitor 文件操作权限。初始化数据读取与 fetch/XHR 观察均核对作品 ID，不收集页面上无关图片。
- Android 14 及以上用用户发起的数据传输 Job；Android 10–13 用前台下载服务。进度通知可取消。系统杀进程后标为中断，返回应用重新解析继续；不承诺被强制停止后继续后台运行。
- 原生 HTTPS 下载会按实际目标 URL 取 Cookie，重定向重新检查。临时下载完成后先校验，再用 MediaStore 的待发布机制写入相册，不申请全部文件或相册读取权限。
- 图文首版支持静态 JPEG/PNG/WebP；不保存实况视频和配乐，不生成合成视频。视频支持单个完整 MP4，不支持直播、分段流拼接或 DRM 内容。单图上限 50 MB，视频上限 8 GB。
- 页面数据结构、WebView 兼容性及抖音风控会变化；遇到无法取得数据的页面会在限时内显示失败，不会切换到远程解析服务。旧 WebView 无法提前注入脚本时尝试初始化数据；兼容性失败时可更新系统 WebView 后重试。视频使用官方手机分享页与手机浏览器 UA，保留短链重定向参数；直接视频链接转换为同作品的官方手机分享页并请求公开 SSR 数据。图文保留已验证的桌面页面解析，用户始终看到拾影移动界面。
- 长视频取消后会重新下载该视频；图文可以逐张补下。MP4 校验检查容器结构和长度，不等同于对整段视频逐帧解码验收。

## 0.1.3 变更

移除独立 ResolverActivity 和“前往网页检查”操作。解析、进度、错误与结果统一在拾影任务/详情界面显示；视频保存后展示封面，图文显示顺序与数量，完成状态显示大小。解析器保留来源、主框架、任务 ID、作品 ID 与媒体数据校验。修复不完整早期详情阻止后续完整数据被识别的问题。升级保留原任务、相册文件、主题和会话偏好，无数据库结构变更。

隐藏网页不会绕过平台登录、访问权限或安全验证；该版本支持可获取公开媒体数据的作品，不承诺所有公开链接均可免登录下载。

## 0.1.4 视频识别修复

修复短链跳到官方 iesdouyin 分享页后，被过早转换为桌面页并丢弃分享参数的问题。样例桌面页的 aweme 为空；手机分享页在保留参数（尤其 from_ssr）后提供 videoInfoRes，现复用已有目标作品匹配逻辑读取该结构。直接视频页链接使用同 ID 的官方手机分享页 `?from_ssr=1`；不会拷贝抖音 App 登录状态，不使用第三方解析服务。

官方手机分享页限定 HTTPS、精确域名与 video/note/slides 的数字作品路径；消息回调校验当前来源、主框架、任务 ID 和作品 ID。分享页尝试唤起其他应用时拦截该跳转，继续在拾影解析。图文仍转入原有已验证的图文页面流程。

另修复流式文本记录按 UTF-8 字节计长、与后续 JSON 记录之间没有换行时丢失数据的问题；仅跳过声明长度内的文本，不将文本中的伪记录当作作品。添加手机分享数据结构、来源边界与字节文本记录回归测试。

## 0.1.5 水印资源选源修复

手机分享页可能把带抖音标记和账号片尾的 playwm 地址放在 play_addr 中。现仅对实测确认的 aweme.snssdk.com 官方 playwm 路由请求同一视频 ID 的普通播放路由，保留查询字节；其他 CDN 签名地址不改写。保留 H.264 和码率列表中的播放候选，不采用 download_addr 或账号片尾资源；明确水印标记的候选及下载重定向会被拒绝。无法取得普通播放资源时显示失败，不自动保存已知水印版本。

升级后对旧视频记录点击“重新下载”，会重新保存普通播放版本；旧相册文件保留，避免删除用户文件。图文续传规则不变。作者原本嵌入画面的文字或标记保留；未知 CDN 的水印状态不能仅凭 URL 判断，不承诺任意作品都无水印。实际样例对比见 VALIDATION.md。
