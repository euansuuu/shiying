package com.shiying.local

import android.content.Intent
import android.media.MediaMetadataRetriever
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class RealDownloadTest {
    @Test fun downloadRequestedPublicWork() {
        val share = InstrumentationRegistry.getArguments().getString("share")
        assumeTrue("Explicit share argument is required for this network test", !share.isNullOrBlank())
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        assertEquals("com.shiying.local.debug",context.packageName)
        val activity = launchTestActivity(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        val engine = LocalEngine.of(context)
        var id = ""
        instrumentation.runOnMainSync { id = engine.add(share!!) }
        val deadline = SystemClock.elapsedRealtime()+230000
        var stayedInApp = true
        while (SystemClock.elapsedRealtime() < deadline) {
            val status = engine.repository.get(id)?.optString("status")
            if (status != null && status !in Repository.ACTIVE) break
            instrumentation.runOnMainSync {
                stayedInApp = stayedInApp && ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).all { it === activity }
            }
            SystemClock.sleep(300)
        }
        val job = engine.repository.get(id)!!
        val report = JSONObject().put("workId",job.optString("workId")).put("status",job.optString("status"))
            .put("kind",job.optString("kind")).put("total",job.optInt("total")).put("done",job.optInt("done")).put("bytes",job.optLong("bytes"))
            .put("message",job.optString("message")).put("stayedInApp",stayedInApp)
        val assets = JSONArray()
        val media = MediaFiles(context) { false }
        for (index in 0 until job.getJSONArray("assets").length()) {
            val entry = job.getJSONArray("assets").getJSONObject(index)
            assets.put(JSONObject().put("index",index+1).put("mime",entry.optString("mime")).put("size",entry.optLong("size")).put("sha256",entry.optString("sha256")).put("valid",media.validSaved(entry)).put("error",entry.optString("error")))
        }
        report.put("assets",assets)
        if (job.optString("status") == "completed" && job.optString("kind") == "video") {
            val retriever = MediaMetadataRetriever()
            try {
                retriever.setDataSource(context, MediaFiles.ownMediaUri(job.getJSONArray("assets").getJSONObject(0).getString("uri")))
                val video = JSONObject()
                    .put("durationMs", retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0)
                    .put("width", retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0)
                    .put("height", retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull() ?: 0)
                val frame = retriever.getFrameAtTime(0, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)
                video.put("decodedFrame", frame != null)
                frame?.recycle()
                if (InstrumentationRegistry.getArguments().getString("captureFrames") == "true") {
                    val root = File(context.filesDir,"real-download-frames").apply { mkdirs() }
                    val duration = video.getLong("durationMs")
                    for ((index,position) in listOf(0L,2000L,duration/2,(duration-1500).coerceAtLeast(0)).withIndex()) {
                        val sample = retriever.getFrameAtTime(position*1000,MediaMetadataRetriever.OPTION_CLOSEST) ?: error("Frame decode failed")
                        File(root,"frame-$index.jpg").outputStream().use { assertTrue(sample.compress(android.graphics.Bitmap.CompressFormat.JPEG,90,it)) }
                        sample.recycle()
                    }
                }
                report.put("video", video)
            } finally { retriever.release() }
        }
        File(context.filesDir,"real-download-report.json").writeText(report.toString(2))
        instrumentation.runOnMainSync { activity.window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
        assertTrue("Parsing must not open another activity",stayedInApp)
        assertEquals(report.toString(),"completed",job.optString("status"))
        assertTrue(job.optInt("done") > 0)
        for (index in 0 until assets.length()) assertTrue(assets.getJSONObject(index).getBoolean("valid"))
        InstrumentationRegistry.getArguments().getString("expectedSha256")?.let { assertEquals(it,assets.getJSONObject(0).getString("sha256")) }
        report.optJSONObject("video")?.let {
            assertTrue(it.optLong("durationMs") > 0)
            assertTrue(it.optInt("width") > 0 && it.optInt("height") > 0)
            assertTrue(it.getBoolean("decodedFrame"))
        }
    }
}
