package com.shiying.local

import android.annotation.SuppressLint
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import org.json.JSONObject
import org.json.JSONTokener

/** Keeps the external page underneath the opaque app UI, without exposing its controls or bridge. */
class WorkResolver(private val activity: MainActivity, val jobId: String) {
    private val engine = LocalEngine.of(activity)
    private val web = WebView(activity)
    private val handler = Handler(Looper.getMainLooper())
    private val mobileAgent = WebSettings.getDefaultUserAgent(activity).replace("; wv", "").replace(" Version/4.0", "")
    private val desktopAgent: String get() {
        val version = Regex("Chrome/([0-9]+)").find(mobileAgent)?.groupValues?.get(1) ?: "130"
        return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/$version.0.0.0 Safari/537.36"
    }
    private var expected = ""
    private var source = ""
    private var script = ""
    private var complete = false
    private var running = false
    private var remaining = 60000L
    private var deadline = 0L
    private var slow = false
    private val poll = object : Runnable {
        override fun run() {
            if (complete || !running) return
            if (engine.activeId != jobId) { close(); return }
            val left = deadline - SystemClock.elapsedRealtime()
            if (left <= 0) { fail("解析超时，暂未获取到可下载的作品信息。请检查网络或确认作品仍可公开访问后重试。"); return }
            if (!slow && left < 40000) {
                slow = true
                engine.resolutionStatus(jobId, "resolving", "仍在获取作品信息，请保持拾影在前台，可随时取消。")
            }
            if (trusted(web.url)) {
                val expression = "(()=>{window.__shiyingTargetId=" + JSONObject.quote(expected) + ";const detail=" + script + ";return {detail,blocked:detail?'':window.__shiyingBlockReason?.()||''};})()"
                web.evaluateJavascript(expression) { raw ->
                    if (!complete && running && trusted(web.url)) runCatching {
                        if (raw.length <= 2000000 && raw != "null") {
                            val value = JSONTokener(raw).nextValue() as? JSONObject ?: return@runCatching
                            value.optJSONObject("detail")?.let { receive(it) }
                            if (!complete) when (value.optString("blocked")) {
                                "login" -> fail("当前作品需要登录，暂无法直接下载。")
                                "verification" -> fail("当前访问需要安全验证，暂无法直接下载。请稍后重试。")
                            }
                        }
                    }
                }
            }
            handler.postDelayed(this, 750)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    fun start() {
        val job = engine.repository.get(jobId) ?: error("未找到下载任务。")
        source = job.getString("source")
        expected = job.optString("workId")
        if (BuildConfig.DEBUG) WebView.setWebContentsDebuggingEnabled(true)
        script = activity.assets.open("resolver.js").bufferedReader().use { it.readText() }.trim().removeSuffix(";")
            .replace("__JOB_ID__", JSONObject.quote(jobId)).replace("__EXPECTED_ID__", JSONObject.quote(expected))
        web.settings.apply {
            javaScriptEnabled = true; domStorageEnabled = true; allowFileAccess = false; allowContentAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW; setSupportMultipleWindows(false)
            mediaPlaybackRequiresUserGesture = true
            useWideViewPort = true; loadWithOverviewMode = true
            userAgentString = if (Uri.parse(source).path?.startsWith("/note/") == true) desktopAgent else mobileAgent
        }
        web.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        web.isFocusable = false
        web.isFocusableInTouchMode = false
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false)
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (complete) return true
                if (!request.isForMainFrame) return false
                val url = request.url.toString()
                // Public share pages may try to open Douyin; keep parsing locally without launching another app.
                if (request.url.scheme !in setOf("https", "http")) return true
                if (followShareRedirect(url)) return true
                if (!WorkParser.allowedNavigation(url)) { fail("作品跳转到不支持的地址，暂无法解析。"); return true }
                return false
            }
            override fun onPageStarted(view: WebView, url: String, favicon: android.graphics.Bitmap?) {
                if (complete || followShareRedirect(url)) return
                val path = Uri.parse(url).path ?: ""
                if (Regex("/(?:passport|login)(?:/|$)").containsMatchIn(path)) { fail("当前作品需要登录，暂无法直接下载。"); return }
                val identifier = WorkParser.workId(url)
                if (identifier.isNotBlank()) {
                    if (expected.isNotBlank() && expected != identifier) { fail("作品跳转与当前链接不匹配，请重新添加链接。"); return }
                    expected = identifier
                }
            }
            override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, response: android.webkit.WebResourceResponse) {
                if (request.isForMainFrame) fail(when (response.statusCode) {
                    401 -> "当前作品需要登录，暂无法直接下载。"
                    403 -> "当前作品访问受限，暂无法直接下载。"
                    else -> "作品加载失败（${response.statusCode}），请稍后重试。"
                })
            }
            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) fail("作品加载失败，请检查手机网络后重试。")
            }
            override fun onRenderProcessGone(view: WebView, detail: android.webkit.RenderProcessGoneDetail): Boolean {
                fail("系统网页组件已停止，请重新解析。")
                return true
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(consoleMessage: ConsoleMessage): Boolean = true
            override fun onJsAlert(view: WebView, url: String, message: String, result: android.webkit.JsResult): Boolean { result.cancel(); return true }
            override fun onJsConfirm(view: WebView, url: String, message: String, result: android.webkit.JsResult): Boolean { result.cancel(); return true }
            override fun onJsPrompt(view: WebView, url: String, message: String, defaultValue: String, result: android.webkit.JsPromptResult): Boolean { result.cancel(); return true }
        }
        if (WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            WebViewCompat.addWebMessageListener(web, "ShiyingResult", setOf("https://www.douyin.com", "https://douyin.com", "https://www.iesdouyin.com")) { _, message, origin, mainFrame, _ ->
                if (running && mainFrame && origin.scheme == "https" && origin.host == Uri.parse(web.url ?: "").host && trusted(web.url)) runCatching {
                    val raw = message.data ?: return@runCatching
                    if (raw.length <= 2000000) {
                        val envelope = JSONObject(raw)
                        if (envelope.optString("jobId") == jobId) envelope.optJSONObject("detail")?.let { receive(it) }
                    }
                }
            }
        }
        if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            WebViewCompat.addDocumentStartJavaScript(web, script, setOf("https://www.douyin.com", "https://douyin.com", "https://www.iesdouyin.com"))
        }
        // Keep a real viewport and normal visibility so page scripts can run; the app WebView fully covers it.
        val content = activity.findViewById<ViewGroup>(android.R.id.content)
        content.addView(web, 0, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        resume()
        val initial = if (expected.isNotBlank() && Uri.parse(source).path?.startsWith("/video/") == true)
            "https://www.iesdouyin.com/share/video/$expected/?from_ssr=1" else source
        if (engine.repository.remember()) web.loadUrl(initial) else (activity.application as ShiyingApplication).clearCookies { if (!complete) web.loadUrl(initial) }
    }

    private fun followShareRedirect(url: String): Boolean {
        val target = WorkParser.canonicalRedirect(url)
        if (target.isBlank()) return false
        val identifier = WorkParser.workId(target)
        if (expected.isNotBlank() && expected != identifier) { fail("作品跳转与当前链接不匹配，请重新添加链接。"); return true }
        expected = identifier
        if (Uri.parse(target).path?.startsWith("/video/") == true) {
            web.settings.userAgentString = mobileAgent
            // Preserve the official redirect query: removing from_ssr can leave videoInfoRes empty.
            if (Uri.parse(url).getQueryParameter("from_ssr") == null) {
                web.loadUrl(Uri.parse(url).buildUpon().appendQueryParameter("from_ssr", "1").build().toString())
                return true
            }
            return false
        }
        web.settings.userAgentString = desktopAgent
        web.loadUrl(target)
        return true
    }
    private fun trusted(url: String?): Boolean {
        val uri = runCatching { Uri.parse(url ?: "") }.getOrNull() ?: return false
        return uri.scheme == "https" && uri.host in setOf("www.douyin.com", "douyin.com", "www.iesdouyin.com") && expected.isNotBlank() && WorkParser.workId(url ?: "") == expected
    }
    private fun receive(candidate: JSONObject) {
        if (complete || engine.activeId != jobId || expected.isBlank()) return
        val work = try { WorkParser.parse(candidate, expected, web.url ?: source, web.settings.userAgentString) }
            catch (exception: IllegalStateException) { fail(exception.message ?: "未取得可下载的作品信息。"); return }
            catch (_: Exception) { return }
        close()
        engine.resolved(jobId, work)
    }
    private fun fail(message: String) {
        if (complete) return
        close()
        engine.finishResolution(jobId, "failed", message)
    }
    fun resume() {
        if (complete || running) return
        running = true
        deadline = SystemClock.elapsedRealtime() + remaining
        web.onResume()
        engine.resolutionStatus(jobId, "resolving", if (slow) "仍在获取作品信息，请保持拾影在前台，可随时取消。" else "正在本机识别作品…")
        handler.post(poll)
    }
    fun pause() {
        if (complete || !running) return
        running = false
        remaining = (deadline - SystemClock.elapsedRealtime()).coerceAtLeast(0)
        handler.removeCallbacks(poll)
        web.onPause()
        engine.resolutionStatus(jobId, "resolving", "解析已暂停，返回拾影后继续。")
    }
    fun close() {
        if (complete) return
        complete = true; running = false
        handler.removeCallbacks(poll)
        (web.parent as? ViewGroup)?.removeView(web)
        web.stopLoading(); web.destroy()
        activity.releaseResolver(this)
    }
}
