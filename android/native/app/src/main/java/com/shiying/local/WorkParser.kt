package com.shiying.local

import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.net.URLDecoder

data class SourceAsset(val index: Int, val key: String, val urls: List<String>)
data class ResolvedWork(
    val id: String, val kind: String, val title: String, val author: String,
    val caption: String, val notice: String, val assets: List<SourceAsset>,
    val referer: String, val userAgent: String,
)

object WorkParser {
    private fun JSONObject.text(name: String): String = opt(name) as? String ?: ""
    private val hosts = setOf("douyin.com", "www.douyin.com", "v.douyin.com")
    private val idPath = Regex("/(?:video|note)/([0-9]{1,30})/?")
    private val shortPath = Regex("/[A-Za-z0-9_-]+/?")

    fun extract(text: String): String {
        for (match in Regex("https?://[^\\s<>\"“”]+", RegexOption.IGNORE_CASE).findAll(text)) {
            val raw = match.value.trimEnd('.', ',', '，', '。', ';', '；', '!', '！', '?', '？', ')', '）', ']', '】', '\'', '"')
            val uri = runCatching { URI(raw) }.getOrNull() ?: continue
            val host = uri.host?.lowercase() ?: continue
            if (host !in hosts || uri.userInfo != null || uri.port !in setOf(-1, 80, 443)) continue
            if (host == "v.douyin.com" && shortPath.matches(uri.path) || host != "v.douyin.com" && idPath.matches(uri.path)) {
                return "https://$host${uri.path}"
            }
        }
        error("未找到有效的抖音作品链接，请粘贴短链、视频页或图文页链接。")
    }

    fun workId(url: String): String {
        val uri = runCatching { URI(url) }.getOrNull() ?: return ""
        if (!safeHttps(uri)) return ""
        if (uri.host?.lowercase() == "www.iesdouyin.com") return workId(canonicalRedirect(url))
        if (uri.host?.lowercase() !in setOf("www.douyin.com", "douyin.com")) return ""
        idPath.matchEntire(uri.path ?: "")?.groupValues?.get(1)?.let { return it }
        if (uri.path !in setOf("", "/") && !Regex("/user/[A-Za-z0-9_-]+/?").matches(uri.path ?: "")) return ""
        val values = runCatching { (uri.rawQuery ?: "").split('&').map { it.split('=',limit=2) }
            .filter { URLDecoder.decode(it[0],"UTF-8") == "modal_id" }
            .map { URLDecoder.decode(it.getOrElse(1) { "" },"UTF-8") } }.getOrDefault(emptyList())
        return values.singleOrNull()?.takeIf { Regex("[0-9]{1,30}").matches(it) } ?: ""
    }

    fun canonicalRedirect(url: String): String {
        val uri = runCatching { URI(url) }.getOrNull() ?: return ""
        if (!safeHttps(uri) || uri.host?.lowercase() != "www.iesdouyin.com") return ""
        val path = Regex("/share/(video|note|slides)/([0-9]{1,30})/?").matchEntire(uri.path ?: "") ?: return ""
        return "https://www.douyin.com/${if (path.groupValues[1] == "video") "video" else "note"}/${path.groupValues[2]}"
    }

    fun allowedNavigation(url: String): Boolean {
        val uri = runCatching { URI(url) }.getOrNull() ?: return false
        val host = uri.host?.lowercase() ?: return false
        return safeHttps(uri) && (host == "douyin.com" || host.endsWith(".douyin.com") || host == "www.iesdouyin.com" && canonicalRedirect(url).isNotBlank())
    }
    private fun safeHttps(uri: URI) = uri.scheme == "https" && uri.userInfo == null && uri.port in setOf(-1,443)

    fun parse(detail: JSONObject, expected: String, referer: String, agent: String): ResolvedWork {
        val identifier = detail.text("aweme_id").ifBlank { detail.text("awemeId") }
        require(Regex("[0-9]{1,30}").matches(identifier) && identifier == expected) { "作品信息与当前链接不匹配，请重新解析。" }
        val caption = detail.text("desc")
        require(caption.length <= 32000) { "作品文案超过支持范围。" }
        val author = detail.optJSONObject("author")?.text("nickname")?.ifBlank { "未知作者" } ?: "未知作者"
        val images = detail.optJSONArray("images")
        val isNote = images != null && images.length() > 0 || URI(referer).path.startsWith("/note/") || detail.optInt("aweme_type") == 68
        if (isNote) {
            require(images != null && images.length() in 1..1000) { "已识别图文，尚未取得完整图片信息，请稍后重试。" }
            var live = false
            val assets = (0 until images.length()).map { index ->
                val image = images.optJSONObject(index) ?: JSONObject()
                if ((image.optJSONObject("video")?.length() ?: 0) > 0) live = true
                SourceAsset(index + 1, image.text("uri").ifBlank { image.text("image_id").ifBlank { image.text("imageId") } }, urls(image))
            }
            require(assets.any { it.urls.isNotEmpty() }) { "已识别图文，尚未取得可下载图片，请稍后重试。" }
            val notices = mutableListOf<String>()
            if (live) notices.add("本次仅保存静态图片，实况视频未保存。")
            if (detail.optJSONObject("music") != null) notices.add("图文配乐未单独保存。")
            return ResolvedWork(identifier, "album", caption.ifBlank { "未命名图文" }, author, caption, notices.joinToString(" "), assets, "https://www.douyin.com/note/$identifier", agent)
        }
        val video = detail.optJSONObject("video") ?: error("页面没有提供可下载的视频数据，暂不支持直播。")
        val address = video.optJSONObject("play_addr") ?: video.optJSONObject("playAddr") ?: error("未取得视频播放地址。")
        val candidates = urls(address).mapNotNull(::playbackUrl).distinct()
        check(candidates.isNotEmpty()) { "未取得普通播放地址，已阻止保存带水印资源。请稍后重新解析。" }
        // Older video assets may contain the platform's watermarked rendition; re-resolve without deleting gallery files.
        return ResolvedWork(identifier, "video", caption.ifBlank { "未命名视频" }, author, caption, "", listOf(SourceAsset(1, "$identifier:playback-v1", candidates)), "https://www.douyin.com/video/$identifier", agent)
    }

    private fun parameters(uri: URI, name: String): List<String> = (uri.rawQuery ?: "").split('&').map { it.split('=',limit=2) }
        .filter { URLDecoder.decode(it[0],"UTF-8").equals(name,ignoreCase=true) }
        .map { URLDecoder.decode(it.getOrElse(1) { "" },"UTF-8") }

    fun isWatermarked(url: String): Boolean = runCatching {
        val uri = URI(url)
        Regex("/playwm(?:/|$)",RegexOption.IGNORE_CASE).containsMatchIn(uri.path ?: "") ||
            parameters(uri,"watermark").any { it == "1" || it.equals("true",ignoreCase=true) }
    }.getOrDefault(true)

    private fun playbackUrl(value: String): String? {
        val uri = URI(value)
        // Verified mobile share route: change only the known service path, keeping the same video ID and query bytes.
        val ordinary = if (uri.host == "aweme.snssdk.com" && uri.path in setOf("/aweme/v1/playwm/","/aweme/v1/playwm") &&
            parameters(uri,"video_id").singleOrNull()?.matches(Regex("[A-Za-z0-9_-]{1,256}")) == true)
            value.replaceFirst("/aweme/v1/playwm","/aweme/v1/play") else value
        return ordinary.takeUnless(::isWatermarked)
    }

    private fun urls(item: JSONObject): List<String> {
        val values = item.optJSONArray("url_list") ?: item.optJSONArray("urlList") ?: JSONArray()
        return (0 until values.length()).mapNotNull { index ->
            val value = values.opt(index) as? String ?: return@mapNotNull null
            val uri = runCatching { URI(value) }.getOrNull() ?: return@mapNotNull null
            if (value.length <= 8192 && uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.userInfo == null && uri.port in setOf(-1, 443)) value else null
        }.distinct()
    }
}
