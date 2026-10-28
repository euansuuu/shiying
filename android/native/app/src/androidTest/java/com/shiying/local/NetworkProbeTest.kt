package com.shiying.local

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

@RunWith(AndroidJUnit4::class)
class NetworkProbeTest {
    private val agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"

    private fun probe(start: String, dump: Boolean) {
        var url = start
        repeat(8) { step ->
            val connection = runCatching { URL(url).openConnection() as HttpURLConnection }.getOrNull() ?: return@repeat
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 10000
            connection.readTimeout = 15000
            connection.setRequestProperty("User-Agent", agent)
            connection.setRequestProperty("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            connection.setRequestProperty("Accept-Language", "zh-CN,zh;q=0.9")
            val status = runCatching { connection.responseCode }.getOrElse { exception ->
                Log.i("ShiyingProbe", "[$step] $url -> ERR ${exception.javaClass.simpleName}: ${exception.message}")
                connection.disconnect(); return@repeat
            }
            val location = connection.getHeaderField("Location")
            val type = connection.contentType
            Log.i("ShiyingProbe", "[$step] $url -> $status type=$type location=$location")
            for (name in listOf("set-cookie", "location", "content-length")) {
                val values = connection.headerFields[name] ?: continue
                Log.i("ShiyingProbe", "  $name=${values.joinToString(" | ").take(600)}")
            }
            if (status in 300..399 && !location.isNullOrBlank()) {
                url = runCatching { URL(URL(url), location).toString() }.getOrNull() ?: return
                connection.disconnect()
                return@repeat
            }
            if (status == 200) {
                val body = runCatching { connection.inputStream.bufferedReader().use { reader -> reader.readText() } }.getOrDefault("")
                Log.i("ShiyingProbe", "[$step] body length=${body.length} head=${body.take(200).replace("\n", " ")}")
                if (dump) {
                    val target = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir, "probe-${start.hashCode()}-$step.html")
                    target.writeText(body)
                    Log.i("ShiyingProbe", "  dumped ${target.absolutePath}")
                }
            }
            connection.disconnect()
            return
        }
    }

    @Test
    fun probeRedirects() {
        probe("https://www.douyin.com/video/7300000000000000000", true)
        probe("https://www.douyin.com/", false)
    }
}
