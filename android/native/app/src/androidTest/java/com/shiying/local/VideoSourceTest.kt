package com.shiying.local

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class VideoSourceTest {
    @Test fun retryReplacesLegacyAssetReferenceBeforeAnyTransfer() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        assertEquals("com.shiying.local.debug",context.packageName)
        val activity = launchTestActivity(Intent(context,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        val engine = LocalEngine.of(context)
        var id = ""
        try {
            instrumentation.runOnMainSync {
                assertNull(engine.activeId)
                id = engine.add("https://www.douyin.com/video/123")
                engine.next()
                activity.closeResolution(id)
                val old = JSONObject().put("index",1).put("key","123").put("status","completed").put("uri","content://media/external/video/media/0")
                engine.repository.save(engine.repository.get(id)!!.put("assets",JSONArray().put(old)))
                val detail=JSONObject("""{"aweme_id":"123","video":{"play_addr":{"url_list":["https://cdn.example/test.mp4"]}}}""")
                engine.resolved(id,WorkParser.parse(detail,"123","https://www.douyin.com/video/123","test"))
                val asset=engine.repository.get(id)!!.getJSONArray("assets").getJSONObject(0)
                assertEquals("123:playback-v1",asset.getString("key"))
                assertEquals("pending",asset.getString("status"))
                assertFalse(asset.has("uri"))
                engine.action(id,"cancel")
            }
        } finally {
            instrumentation.runOnMainSync {
                if (id.isNotBlank()) {
                    engine.action(id,"cancel")
                    engine.repository.writableDatabase.delete("jobs","id=?",arrayOf(id))
                }
                activity.window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
        }
    }
}
