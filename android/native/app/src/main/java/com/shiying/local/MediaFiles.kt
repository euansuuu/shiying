package com.shiying.local

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.ThumbnailUtils
import android.net.Uri
import android.os.CancellationSignal
import android.provider.MediaStore
import android.util.Size
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.max

class TransferStopped : Exception()
class MediaUnavailable(val expired: Boolean, message: String) : Exception(message)
data class Fetched(val mime: String, val extension: String, val size: Long, val sha256: String)

class MediaFiles(private val context: Context, private val stopped: () -> Boolean) {
    private val connection = AtomicReference<HttpURLConnection?>()
    fun cancel() { connection.getAndSet(null)?.disconnect() }
    private fun check() { if (stopped()) throw TransferStopped() }

    fun fetch(asset: SourceAsset, work: ResolvedWork, temporary: File, progress: (Long, Long, Long) -> Unit): Fetched {
        var expired = false
        var failure = "页面未提供该媒体的可用地址。"
        for (candidate in asset.urls) {
            for (attempt in 0..1) {
                check()
                try {
                    var url = URL(candidate)
                    var redirects = 0
                    while (true) {
                        check()
                        require(url.protocol == "https" && url.userInfo == null && url.port in listOf(-1, 443)) { "媒体地址不符合安全要求。" }
                        require(work.kind != "video" || !WorkParser.isWatermarked(url.toString())) { "媒体跳转到了带水印资源，已停止保存。请重新解析。" }
                        val addresses = InetAddress.getAllByName(url.host)
                        require(addresses.none { it.isAnyLocalAddress || it.isLoopbackAddress || it.isSiteLocalAddress || it.isLinkLocalAddress || it.isMulticastAddress }) { "媒体地址不可用。" }
                        val current = url.openConnection() as HttpURLConnection
                        connection.set(current)
                        current.instanceFollowRedirects = false
                        current.connectTimeout = 10000
                        current.readTimeout = 15000
                        current.setRequestProperty("User-Agent", work.userAgent)
                        current.setRequestProperty("Referer", work.referer)
                        current.setRequestProperty("Accept-Encoding", "identity")
                        android.webkit.CookieManager.getInstance().getCookie(url.toString())?.takeIf { it.isNotBlank() }?.let { current.setRequestProperty("Cookie", it) }
                        val status = current.responseCode
                        if (status in listOf(301, 302, 303, 307, 308)) {
                            val location = current.getHeaderField("Location") ?: throw IOException()
                            current.disconnect()
                            require(++redirects <= 8) { "媒体地址跳转次数过多。" }
                            url = URL(url, location)
                            continue
                        }
                        if (status in listOf(401, 403, 410)) throw MediaUnavailable(true, "媒体地址不可用，请重新解析作品。")
                        if (status != 200) throw IOException()
                        val type = (current.contentType ?: "").substringBefore(';').lowercase()
                        require(type.isBlank() || type == "application/octet-stream" || type.startsWith(if (work.kind == "album") "image/" else "video/")) { "媒体地址返回了网页或错误内容。" }
                        val length = current.contentLengthLong.takeIf { it > 0 } ?: 0
                        val maximum = if (work.kind == "album") 50L * 1024 * 1024 else 8L * 1024 * 1024 * 1024
                        require(length <= maximum) { "文件超过支持大小。" }
                        if (length > 0) require(context.cacheDir.usableSpace > length * 2 + 10 * 1024 * 1024) { "手机可用空间不足，请清理空间后重试。" }
                        var count = 0L
                        val began = System.nanoTime()
                        var previous = began
                        progress(0, length, 0)
                        current.inputStream.use { input -> temporary.outputStream().use { output ->
                            val buffer = ByteArray(65536)
                            while (true) {
                                check()
                                val read = input.read(buffer)
                                if (read < 0) break
                                count += read
                                require(count <= maximum) { "文件超过支持大小。" }
                                output.write(buffer, 0, read)
                                val now = System.nanoTime()
                                if (now - previous > 400_000_000) {
                                    require(context.cacheDir.usableSpace > 10 * 1024 * 1024) { "手机可用空间不足。" }
                                    progress(count, length, (count * 1_000_000_000.0 / max(1L, now - began)).toLong())
                                    previous = now
                                }
                            }
                        } }
                        check()
                        require(count > 0 && (length == 0L || count == length)) { "媒体传输不完整，请重新下载。" }
                        val (mime, extension) = if (work.kind == "album") validateImage(temporary) else {
                            require(validMp4(temporary)) { "文件不是完整的 MP4 视频。" }
                            "video/mp4" to "mp4"
                        }
                        return Fetched(mime, extension, count, digest(temporary))
                    }
                } catch (exception: MediaUnavailable) {
                    expired = expired || exception.expired
                    failure = exception.message ?: "媒体地址不可用。"
                    break
                } catch (exception: IllegalArgumentException) {
                    failure = exception.message ?: "媒体内容校验失败。"
                    break
                } catch (_: IOException) {
                    failure = "媒体请求或文件写入失败，请检查网络与可用空间。"
                } finally {
                    connection.getAndSet(null)?.disconnect()
                }
            }
        }
        check()
        throw MediaUnavailable(expired, failure)
    }

    fun validSaved(asset: JSONObject): Boolean {
        if (asset.optString("status") != "completed") return false
        return try {
            val uri = ownMediaUri(asset.getString("uri"))
            context.contentResolver.openInputStream(uri)!!.use { input ->
                val hash = MessageDigest.getInstance("SHA-256")
                val buffer = ByteArray(65536)
                var count = 0L
                while (true) {
                    check()
                    val read = input.read(buffer)
                    if (read < 0) break
                    hash.update(buffer, 0, read)
                    count += read
                }
                count > 0 && count == asset.optLong("size") && hex(hash.digest()) == asset.optString("sha256")
            }
        } catch (exception: TransferStopped) { throw exception } catch (_: Exception) { false }
    }

    fun publish(file: File, fetched: Fetched, work: ResolvedWork, group: String, index: Int, pending: (Uri) -> Unit): Uri {
        val collection = if (work.kind == "album") MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY) else MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, if (work.kind == "album") "%03d.${fetched.extension}".format(index) else "${work.id}.mp4")
            put(MediaStore.MediaColumns.MIME_TYPE, fetched.mime)
            put(MediaStore.MediaColumns.RELATIVE_PATH, if (work.kind == "album") "Pictures/拾影/$group" else "Movies/拾影")
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val resolver = context.contentResolver
        val uri = resolver.insert(collection, values) ?: error("无法创建媒体文件，请检查手机存储。")
        try {
            pending(uri)
            resolver.openOutputStream(uri, "w")!!.use { output -> file.inputStream().use { input ->
                val buffer = ByteArray(65536)
                while (true) {
                    check()
                    val read = input.read(buffer)
                    if (read < 0) break
                    output.write(buffer, 0, read)
                }
            } }
            check()
            values.clear()
            values.put(MediaStore.MediaColumns.IS_PENDING, 0)
            require(resolver.update(uri, values, null, null) == 1) { "文件发布至相册失败。" }
            return uri
        } catch (exception: Exception) {
            resolver.delete(uri, null, null)
            throw exception
        }
    }

    fun finishPending(value: String) {
        context.contentResolver.update(ownMediaUri(value), ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }, null, null)
    }
    fun discardPending(value: String) {
        runCatching {
            val uri = ownMediaUri(value)
            val pending = context.contentResolver.query(uri, arrayOf(MediaStore.MediaColumns.IS_PENDING), null, null, null)?.use { it.moveToFirst() && it.getInt(0) == 1 } == true
            if (pending) context.contentResolver.delete(uri, null, null)
        }
    }

    fun thumbnail(file: File, jobId: String, index: Int, video: Boolean): String {
        return runCatching {
            val bitmap = if (video) ThumbnailUtils.createVideoThumbnail(file, Size(160, 200), CancellationSignal()) else {
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeFile(file.path, bounds)
                val options = BitmapFactory.Options().apply { inSampleSize = max(1, max(bounds.outWidth, bounds.outHeight) / 240) }
                BitmapFactory.decodeFile(file.path, options) ?: return ""
            }
            val scaled = Bitmap.createScaledBitmap(bitmap, max(1, (bitmap.width * minOf(1.0, 240.0 / max(bitmap.width, bitmap.height))).toInt()), max(1, (bitmap.height * minOf(1.0, 240.0 / max(bitmap.width, bitmap.height))).toInt()), true)
            val root = File(context.filesDir, "thumbnails").apply { mkdirs() }
            val target = File(root, "$jobId-$index.jpg")
            target.outputStream().use { require(scaled.compress(Bitmap.CompressFormat.JPEG, 85, it)) }
            if (scaled !== bitmap) scaled.recycle()
            bitmap.recycle()
            Uri.fromFile(target).toString()
        }.getOrDefault("")
    }

    companion object {
        fun ownMediaUri(value: String): Uri = Uri.parse(value).also {
            require(it.scheme == "content" && it.authority == "media" && (it.path?.contains("/images/media/") == true || it.path?.contains("/video/media/") == true)) { "媒体文件位置无效。" }
        }
        fun digest(file: File): String = file.inputStream().use { input ->
            val hash = MessageDigest.getInstance("SHA-256")
            val buffer = ByteArray(65536)
            while (true) { val count = input.read(buffer); if (count < 0) break; hash.update(buffer, 0, count) }
            hex(hash.digest())
        }
        private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it.toInt() and 255) }

        fun validMp4(file: File): Boolean = runCatching {
            if (file.length() < 32) return false
            RandomAccessFile(file, "r").use { input ->
                val boxes = mutableSetOf<String>()
                var position = 0L
                var count = 0
                while (position < input.length()) {
                    if (++count > 100000 || input.length() - position < 8) return false
                    input.seek(position)
                    var length = input.readInt().toLong() and 0xffffffffL
                    val type = ByteArray(4).also { input.readFully(it) }.toString(Charsets.US_ASCII)
                    var header = 8L
                    if (length == 1L) { length = input.readLong(); header = 16 }
                    else if (length == 0L) length = input.length() - position
                    if (length < header || length > input.length() - position || type == "mdat" && length == header) return false
                    boxes.add(type)
                    position += length
                }
                boxes.containsAll(setOf("ftyp", "moov", "mdat"))
            }
        }.getOrDefault(false)

        private fun validateImage(file: File): Pair<String, String> {
            require(file.length() in 1..(50L * 1024 * 1024)) { "图片为空或超过 50 MB。" }
            val header = ByteArray(12)
            val tail = ByteArray(12)
            RandomAccessFile(file, "r").use { input ->
                require(input.length() >= 12) { "图片文件不完整。" }
                input.readFully(header)
                input.seek(input.length() - 12)
                input.readFully(tail)
            }
            val format = when {
                header[0] == 0xff.toByte() && header[1] == 0xd8.toByte() && tail[10] == 0xff.toByte() && tail[11] == 0xd9.toByte() -> "image/jpeg" to "jpg"
                header.copyOfRange(0, 8).contentEquals(byteArrayOf(-119,80,78,71,13,10,26,10)) && tail.contentEquals(byteArrayOf(0,0,0,0,73,69,78,68,-82,66,96,-126)) -> "image/png" to "png"
                header.copyOfRange(0,4).toString(Charsets.US_ASCII) == "RIFF" && header.copyOfRange(8,12).toString(Charsets.US_ASCII) == "WEBP" -> {
                    val declared = (4..7).sumOf { (header[it].toLong() and 255) shl ((it - 4) * 8) }
                    require(declared + 8 == file.length()) { "WebP 图片传输不完整。" }
                    RandomAccessFile(file, "r").use { input ->
                        var at = 12L
                        while (at + 8 <= input.length()) {
                            input.seek(at)
                            val type = ByteArray(4).also { input.readFully(it) }.toString(Charsets.US_ASCII)
                            require(type !in setOf("ANIM", "ANMF")) { "暂只支持静态图片。" }
                            val sizeBytes = ByteArray(4).also { input.readFully(it) }
                            val length = (0..3).sumOf { (sizeBytes[it].toLong() and 255) shl (it * 8) }
                            require(length <= input.length() - at - 8) { "WebP 图片结构不完整。" }
                            at += 8 + length + length % 2
                        }
                    }
                    "image/webp" to "webp"
                }
                else -> throw IllegalArgumentException("暂只支持完整的静态 JPEG、PNG、WebP 图片。")
            }
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(file.path, bounds)
            require(bounds.outWidth > 0 && bounds.outHeight > 0 && bounds.outWidth.toLong() * bounds.outHeight <= 64_000_000) { "图片尺寸无效或超过解码范围。" }
            var sample = 1
            while (bounds.outWidth.toLong() * bounds.outHeight / sample / sample > 4_000_000) sample *= 2
            val decoded = BitmapFactory.decodeFile(file.path, BitmapFactory.Options().apply { inSampleSize = sample })
            require(decoded != null) { "图片解码校验失败。" }
            decoded.recycle()
            return format
        }
    }
}
