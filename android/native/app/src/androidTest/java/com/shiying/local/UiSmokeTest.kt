package com.shiying.local

import android.content.Intent
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONTokener
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

@RunWith(AndroidJUnit4::class)
class UiSmokeTest {
    @Test fun sharedTextAndThemeChoicesReachTheNativeApp() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val activity = launchTestActivity(Intent(context, MainActivity::class.java)
            .setAction(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT,"分享 https://www.douyin.com/note/123")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        fun evaluate(script: String): String {
            val latch = CountDownLatch(1)
            val result = AtomicReference("")
            instrumentation.runOnMainSync { activity.bridge.webView.evaluateJavascript(script) { result.set(it);latch.countDown() } }
            assertTrue("WebView callback timed out",latch.await(8,TimeUnit.SECONDS))
            return JSONTokener(result.get()).nextValue().toString()
        }
        fun awaitValue(script: String, expected: String) {
            val deadline = SystemClock.elapsedRealtime()+15000
            while (SystemClock.elapsedRealtime() < deadline) {
                if (evaluate(script) == expected) return
                SystemClock.sleep(100)
            }
            assertEquals(expected,evaluate(script))
        }
        awaitValue("document.querySelector('textarea')?.value || ''","分享 https://www.douyin.com/note/123")
        assertEquals("true",evaluate("!document.querySelector('.primary').disabled"))
        val engine = LocalEngine.of(context)
        val fixture = engine.repository.create("https://www.douyin.com/video/123")
            .put("status","completed").put("kind","video").put("title","测试：旧版视频重试")
        engine.repository.save(fixture); engine.publish()
        try {
            awaitValue("Array.from(document.querySelectorAll('.job-title')).some(e=>e.textContent==='测试：旧版视频重试').toString()","true")
            evaluate("Array.from(document.querySelectorAll('.job-title')).find(e=>e.textContent==='测试：旧版视频重试').click();true")
            awaitValue("Array.from(document.querySelectorAll('button')).some(e=>e.textContent==='重新下载').toString()","true")
            assertEquals("true",evaluate("document.documentElement.scrollWidth <= innerWidth"))
            evaluate("document.querySelector('.header button').click();true")
            awaitValue("!!document.querySelector('.composer')","true")
        } finally {
            engine.repository.writableDatabase.delete("jobs","id=?",arrayOf(fixture.getString("id")))
            engine.publish()
        }
        evaluate("document.querySelectorAll('.bottom-nav button')[2].click();true")
        awaitValue("document.querySelectorAll('.theme-picker button').length.toString()","3")
        for ((index,theme) in listOf("light","dark","system").withIndex()) {
            evaluate("document.querySelectorAll('.theme-picker button')[$index].click();true")
            awaitValue("document.documentElement.dataset.theme","$theme")
            assertEquals(theme,LocalEngine.of(context).repository.theme())
        }
        assertEquals("true",evaluate("document.documentElement.scrollWidth <= innerWidth"))
        evaluate("document.querySelectorAll('.bottom-nav button')[0].click();true")
        instrumentation.runOnMainSync { activity.window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
    }
}
