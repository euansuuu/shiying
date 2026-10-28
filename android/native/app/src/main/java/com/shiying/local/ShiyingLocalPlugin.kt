package com.shiying.local

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.Settings
import androidx.activity.result.ActivityResult
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.ActivityCallback
import com.getcapacitor.annotation.CapacitorPlugin
import org.json.JSONArray
import org.json.JSONObject
import java.lang.ref.WeakReference

@CapacitorPlugin(name = "ShiyingLocal")
class ShiyingLocalPlugin : Plugin() {
    private val engine get() = LocalEngine.of(context)
    override fun load() { engine.plugin = WeakReference(this) }
    fun changed(value: JSONObject) { notifyListeners("changed", JSObject(value.toString())) }
    fun shared(text: String) { notifyListeners("shared", JSObject().put("text", text), true) }
    private fun safe(call: PluginCall, action: () -> Unit) {
        try { action() }
        catch (exception: IllegalArgumentException) { call.reject(exception.message ?: "操作参数无效。") }
        catch (exception: IllegalStateException) { call.reject(exception.message ?: "当前无法执行此操作。") }
        catch (_: Exception) { call.reject("本地操作未完成，请检查可用空间或重试。") }
    }
    @PluginMethod fun snapshot(call: PluginCall) = safe(call) {
        val result = engine.repository.snapshot().put("sharedText", engine.sharedText)
        engine.sharedText = ""
        call.resolve(JSObject(result.toString()))
    }
    @PluginMethod fun add(call: PluginCall) = safe(call) {
        val id = engine.add(call.getString("text") ?: "")
        engine.handler.post { (activity as? MainActivity)?.requestDownloadNotification() }
        call.resolve(JSObject().put("id", id))
    }
    @PluginMethod fun action(call: PluginCall) { engine.handler.post { safe(call) {
        val id = call.getString("id") ?: error("缺少任务标识。")
        val action = call.getString("action") ?: error("缺少操作类型。")
        val job = engine.repository.get(id) ?: error("未找到任务。")
        when (action) {
            "open" -> {
                val entries = job.getJSONArray("assets")
                val entry = (0 until entries.length()).map { entries.getJSONObject(it) }.firstOrNull { it.optString("status") == "completed" } ?: error("尚无已保存文件。")
                val uri = MediaFiles.ownMediaUri(entry.getString("uri"))
                val open = Intent(Intent.ACTION_VIEW).setDataAndType(uri, entry.getString("mime")).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                open.clipData = ClipData.newRawUri("拾影作品", uri)
                activity.startActivity(open)
                call.resolve()
            }
            "export" -> {
                require(job.optInt("done") > 0) { "尚无可导出的文件。" }
                val choose = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION).putExtra(Intent.EXTRA_LOCAL_ONLY, true)
                startActivityForResult(call, choose, "exportLocation")
            }
            else -> { engine.action(id, action); call.resolve() }
        }
    } } }
    @ActivityCallback private fun exportLocation(call: PluginCall?, result: ActivityResult) {
        if (call == null) return
        val tree = result.data?.data
        if (result.resultCode != Activity.RESULT_OK || tree == null) { call.resolve(); return }
        val id = call.getString("id") ?: run { call.reject("任务已失效。"); return }
        engine.io.execute {
            safe(call) {
                val job = engine.repository.get(id) ?: error("未找到任务。")
                val resolver = context.contentResolver
                val root = DocumentsContract.buildDocumentUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree))
                val directory = DocumentsContract.createDocument(resolver, root, DocumentsContract.Document.MIME_TYPE_DIR, "拾影_${job.optString("workId")}_${System.currentTimeMillis()}") ?: error("无法创建导出目录。")
                val exported = JSONArray()
                val entries = job.getJSONArray("assets")
                for (index in 0 until entries.length()) {
                    val entry = entries.getJSONObject(index)
                    val info = JSONObject().put("index", entry.optInt("index")).put("key", entry.optString("key")).put("status", entry.optString("status")).put("error", entry.optString("error"))
                    if (entry.optString("status") == "completed") {
                        val mime = entry.getString("mime")
                        val extension = when (mime) { "image/jpeg" -> "jpg"; "image/png" -> "png"; "image/webp" -> "webp"; "video/mp4" -> "mp4"; else -> error("文件格式无效。") }
                        val name = if (job.optString("kind") == "video") "${job.optString("workId")}.$extension" else "%03d.$extension".format(index + 1)
                        val output = DocumentsContract.createDocument(resolver, directory, mime, name) ?: error("无法导出媒体文件。")
                        resolver.openInputStream(MediaFiles.ownMediaUri(entry.getString("uri")))!!.use { input -> resolver.openOutputStream(output, "w")!!.use { input.copyTo(it, 65536) } }
                        info.put("file", name).put("size", entry.optLong("size")).put("sha256", entry.optString("sha256"))
                    }
                    exported.put(info)
                }
                fun text(name: String, mime: String, contents: String) {
                    val output = DocumentsContract.createDocument(resolver, directory, mime, name) ?: error("无法导出文案或清单。")
                    resolver.openOutputStream(output, "w")!!.bufferedWriter(Charsets.UTF_8).use { it.write(contents) }
                }
                if (job.optString("caption").isNotBlank()) text("文案.txt", "text/plain", job.getString("caption"))
                val manifest = JSONObject().put("application", "Shiying Android").put("version", 1).put("work_id", job.optString("workId"))
                    .put("source", job.optString("source")).put("title", job.optString("title")).put("author", job.optString("author"))
                    .put("notice", job.optString("notice")).put("images", exported)
                text("manifest.json", "application/json", manifest.toString(2))
                call.resolve()
                engine.handler.post { android.widget.Toast.makeText(context, "文件与文案已导出。", android.widget.Toast.LENGTH_LONG).show() }
            }
        }
    }
    @PluginMethod fun preferences(call: PluginCall) = safe(call) {
        val edit = engine.repository.preferences.edit()
        call.getString("theme")?.let { require(it in setOf("light", "dark", "system")); edit.putString("theme", it) }
        call.getBoolean("remember")?.let { edit.putBoolean("remember", it) }
        edit.apply()
        engine.handler.post { (activity as? MainActivity)?.applyAppearance(); if (engine.activeId == null) engine.cleanupSession() }
        engine.publish()
        call.resolve()
    }
    @PluginMethod fun clearSession(call: PluginCall) = safe(call) {
        require(engine.activeId == null) { "请先完成或取消当前任务，再清除解析会话。" }
        engine.handler.post { (context.applicationContext as ShiyingApplication).clearCookies { call.resolve() } }
    }
    @PluginMethod fun paste(call: PluginCall) {
        engine.handler.post { safe(call) {
            val clipboard = context.getSystemService(ClipboardManager::class.java)
            val text = clipboard.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(context)?.toString() ?: ""
            require(text.isNotBlank()) { "剪贴板中没有分享文字，请复制抖音作品链接。" }
            call.resolve(JSObject().put("text", text.take(32000)))
        } }
    }
    @PluginMethod fun copyCaption(call: PluginCall) = safe(call) {
        val job = engine.repository.get(call.getString("id") ?: "") ?: error("未找到任务。")
        engine.handler.post { context.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("作品文案", job.optString("caption"))); call.resolve() }
    }
    @PluginMethod fun notifications(call: PluginCall) { engine.handler.post { safe(call) {
        activity.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName))
        call.resolve()
    } } }
}
