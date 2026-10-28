package com.shiying.local

import android.content.Context
import android.os.Handler
import android.os.Looper
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.lang.ref.WeakReference
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicReference

class LocalEngine(private val app: ShiyingApplication) {
    val repository = Repository(app)
    val handler = Handler(Looper.getMainLooper())
    val io = Executors.newSingleThreadExecutor()
    @Volatile var activity: WeakReference<MainActivity>? = null
    @Volatile var plugin: WeakReference<ShiyingLocalPlugin>? = null
    @Volatile var activeId: String? = null
        private set
    @Volatile private var resolved: ResolvedWork? = null
    @Volatile private var transfer: MediaFiles? = null
    @Volatile private var transferRunning = false
    private var clearingSession = false
    private val stopReason = AtomicReference("")
    private var lastPublish = 0L
    var sharedText = ""

    fun publish(force: Boolean = true) {
        handler.post {
            val now = System.currentTimeMillis()
            if (force || now - lastPublish > 450) {
                lastPublish = now
                plugin?.get()?.changed(repository.snapshot())
            }
        }
    }

    fun add(text: String): String {
        require(text.length <= 32000) { "分享文字过长。" }
        val job = repository.create(WorkParser.extract(text))
        publish()
        handler.post { next() }
        return job.getString("id")
    }

    fun next() {
        if (activeId != null || clearingSession) return
        val foreground = activity?.get()?.takeIf { it.foreground } ?: return
        val job = repository.all().asReversed().firstOrNull { it.optString("status") == "queued" } ?: return
        activeId = job.getString("id")
        stopReason.set("")
        job.put("status", "resolving").put("message", "正在本机识别作品…").put("speed", 0)
        repository.save(job)
        publish()
        try {
            foreground.startResolution(job.getString("id"))
        } catch (_: Exception) { finishResolution(job.getString("id"), "failed", "无法启动本机解析，请更新系统 WebView 或重新打开拾影后重试。") }
    }

    fun resolutionStatus(id: String, status: String, message: String) {
        if (activeId != id) return
        val job = repository.get(id) ?: return
        job.put("status", status).put("message", message)
        repository.save(job)
        publish()
    }

    fun resolved(id: String, work: ResolvedWork) {
        if (activeId != id || stopReason.get().isNotBlank()) return
        val job = repository.get(id) ?: return
        val previous = job.optJSONArray("assets") ?: JSONArray()
        val same = previous.length() == work.assets.size && work.assets.all { asset ->
            val old = previous.optJSONObject(asset.index - 1)
            asset.key.isNotBlank() && old != null && old.optInt("index") == asset.index && old.optString("key") == asset.key
        }
        if (!same) {
            val assets = JSONArray()
            work.assets.forEach { asset -> assets.put(JSONObject().put("index", asset.index).put("key", asset.key).put("status", "pending")) }
            job.put("assets", assets).put("done", 0).put("failed", 0).put("bytes", 0).put("thumbnail", "")
                .put("group", "${work.id}_${System.currentTimeMillis()}")
        }
        job.put("workId", work.id).put("kind", work.kind).put("title", work.title).put("author", work.author)
            .put("caption", work.caption).put("notice", work.notice).put("source", work.referer).put("total", work.assets.size)
            .put("status", "downloading").put("message", "").put("current", 0).put("currentBytes", 0).put("currentTotal", 0)
        repository.save(job)
        resolved = work
        publish()
        try { TransferScheduler.schedule(app, id) }
        catch (_: Exception) { finishResolution(id, "interrupted", "系统未能启动下载，请返回应用重试并检查通知设置。") }
    }

    fun finishResolution(id: String, status: String, message: String) {
        if (activeId != id) return
        activity?.get()?.closeResolution(id)
        val job = repository.get(id)
        if (job != null) {
            job.put("status", if (status == "failed" && job.optInt("done") > 0) "partial" else status).put("message", message).put("speed", 0)
            repository.save(job)
        }
        activeId = null
        resolved = null
        publish()
        cleanupSession { handler.post { next() } }
    }

    fun action(id: String, action: String) {
        val job = repository.get(id) ?: error("未找到这个下载任务。")
        when (action) {
            "retry", "resolve" -> {
                if (activeId == id) return
                require(job.optString("status") !in Repository.ACTIVE) { "任务已在队列中。" }
                job.put("status", "queued").put("message", "").put("_refreshes", 0)
                repository.save(job)
                publish()
                handler.post { next() }
            }
            "cancel" -> {
                if (activeId == id) {
                    stop(id, "cancelled")
                    activity?.get()?.closeResolution(id)
                    if (resolved == null || !transferRunning) {
                        if (android.os.Build.VERSION.SDK_INT >= 34) app.getSystemService(android.app.job.JobScheduler::class.java).cancel(4107)
                        finishResolution(id, "cancelled", "任务已取消。")
                    }
                } else if (job.optString("status") in Repository.ACTIVE) {
                    job.put("status", "cancelled").put("message", "任务已取消。")
                    repository.save(job)
                    publish()
                }
            }
            else -> error("不支持的任务操作。")
        }
    }

    fun stop(id: String, reason: String) {
        if (activeId == id) {
            stopReason.compareAndSet("", reason)
            transfer?.cancel()
        }
    }

    fun executeTransfer(id: String, finished: () -> Unit): Boolean {
        val work = resolved
        val job = repository.get(id)
        if (transferRunning) return false
        if (activeId != id || work == null || job == null) {
            if (job != null && job.optString("status") in Repository.ACTIVE) {
                job.put("status", "interrupted").put("message", "下载会话已中断，请返回应用继续下载。")
                repository.save(job); publish()
            }
            return false
        }
        transferRunning = true
        io.execute {
            val media = MediaFiles(app) { stopReason.get().isNotBlank() }
            transfer = media
            val temporary = File(app.cacheDir, "$id.part")
            var needRefresh = false
            fun check() { if (stopReason.get().isNotBlank()) throw TransferStopped() }
            fun counts() {
                val entries = job.getJSONArray("assets")
                var done = 0; var failed = 0; var bytes = 0L
                for (index in 0 until entries.length()) {
                    val item = entries.getJSONObject(index)
                    if (item.optString("status") == "completed") { done++; bytes += item.optLong("size") }
                    if (item.optString("status") == "failed") failed++
                }
                job.put("done", done).put("failed", failed).put("bytes", bytes)
            }
            fun checkpoint(force: Boolean = false) {
                counts(); repository.save(job); publish(force)
                DownloadNotice.update(app, job)
            }
            try {
                val assets = job.getJSONArray("assets")
                for (index in 0 until assets.length()) {
                    check()
                    val entry = assets.getJSONObject(index)
                    if (entry.optBoolean("_pendingPublish")) {
                        val candidate = JSONObject(entry.toString()).put("status", "completed")
                        if (media.validSaved(candidate)) { media.finishPending(entry.getString("uri")); entry.put("status", "completed") }
                        else { media.discardPending(entry.optString("uri")); entry.put("status", "pending") }
                        entry.remove("_pendingPublish")
                    } else if (!media.validSaved(entry)) entry.put("status", "pending")
                }
                checkpoint(true)
                for (asset in work.assets) {
                    check()
                    val entry = assets.getJSONObject(asset.index - 1)
                    if (entry.optString("status") == "completed") continue
                    job.put("current", asset.index).put("currentBytes", 0).put("currentTotal", 0).put("speed", 0)
                    try {
                        val file = media.fetch(asset, work, temporary) { bytes, total, speed ->
                            job.put("currentBytes", bytes).put("currentTotal", total).put("speed", speed)
                            checkpoint()
                        }
                        check()
                        val uri = media.publish(temporary, file, work, job.getString("group"), asset.index) { pending ->
                            entry.put("uri", pending.toString()).put("mime", file.mime).put("size", file.size).put("sha256", file.sha256).put("_pendingPublish", true)
                            checkpoint()
                        }
                        entry.put("status", "completed").put("uri", uri.toString()).put("mime", file.mime).put("size", file.size).put("sha256", file.sha256).put("error", "")
                        entry.remove("_pendingPublish")
                        val thumbnail = media.thumbnail(temporary, id, asset.index, work.kind == "video")
                        entry.put("thumbnail", thumbnail)
                        if (job.optString("thumbnail").isBlank() && thumbnail.isNotBlank()) job.put("thumbnail", thumbnail)
                    } catch (exception: MediaUnavailable) {
                        entry.put("status", "failed").put("error", exception.message ?: "媒体下载失败。")
                        needRefresh = needRefresh || exception.expired
                    } catch (exception: IllegalArgumentException) {
                        entry.put("status", "failed").put("error", exception.message ?: "媒体校验失败。")
                    }
                    checkpoint(true)
                    temporary.delete()
                }
                counts()
                val complete = job.getInt("done") == work.assets.size
                job.put("status", if (complete) "completed" else if (job.optInt("done") > 0) "partial" else "failed")
                    .put("message", if (complete) "作品已保存到手机相册。" else if (needRefresh) "部分媒体地址不可用，请返回应用重新解析，已保存图片会保留。" else "部分媒体未完成，请查看失败原因后重试。")
            } catch (_: TransferStopped) {
                job.put("status", stopReason.get().ifBlank { "interrupted" }).put("message", if (work.kind == "album") "下载已停止，已保存图片保留，可继续下载。" else "下载已停止，可重新下载。")
            } catch (_: Exception) {
                counts()
                job.put("status", if (job.optInt("done") > 0) "partial" else "failed").put("message", "本地保存未完成，请检查网络、手机存储和相册文件是否可访问。")
            } finally {
                temporary.delete()
                transfer = null
                job.put("speed", 0).put("current", 0).put("currentBytes", 0).put("currentTotal", 0)
                counts()
                repository.save(job)
                handler.post {
                    activeId = null
                    resolved = null
                    transferRunning = false
                    if (needRefresh && stopReason.get().isBlank() && job.optInt("_refreshes") < 1 && activity?.get()?.foreground == true) {
                        job.put("status", "queued").put("_refreshes", job.optInt("_refreshes") + 1).put("message", "正在重新获取媒体地址，已保存图片会保留。")
                        repository.save(job)
                    }
                    finished()
                    publish()
                    cleanupSession { handler.post { next() } }
                }
            }
        }
        return true
    }

    fun cleanupSession(done: () -> Unit = {}) {
        if (!repository.remember() && activeId == null) {
            clearingSession = true
            app.clearCookies { clearingSession = false; done() }
        } else { android.webkit.CookieManager.getInstance().flush(); done() }
    }
    companion object { fun of(context: Context): LocalEngine = (context.applicationContext as ShiyingApplication).engine }
}
