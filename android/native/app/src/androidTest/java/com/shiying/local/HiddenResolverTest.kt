package com.shiying.local

import android.content.Intent
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import org.json.JSONTokener
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

@RunWith(AndroidJUnit4::class)
class HiddenResolverTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private fun evaluate(web: WebView, script: String): String {
        val latch = CountDownLatch(1)
        val result = AtomicReference("")
        instrumentation.runOnMainSync { web.evaluateJavascript(script) { result.set(it); latch.countDown() } }
        assertTrue(latch.await(8, TimeUnit.SECONDS))
        return JSONTokener(result.get()).nextValue().toString()
    }
    private fun awaitValue(check: () -> Boolean) {
        val deadline = SystemClock.elapsedRealtime() + 15000
        while (SystemClock.elapsedRealtime() < deadline) { if (check()) return; SystemClock.sleep(100) }
        assertTrue("Condition timed out", check())
    }
    @Test fun parsingStaysBehindTheAppAndCancelRemovesIt() {
        val context = instrumentation.targetContext
        val activity = launchTestActivity(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        val engine = LocalEngine.of(context)
        engine.repository.all().filter { it.optString("source") == "https://www.douyin.com/note/987654321" }.forEach {
            instrumentation.runOnMainSync { engine.action(it.getString("id"), "cancel") }
            engine.repository.writableDatabase.delete("jobs", "id=?", arrayOf(it.getString("id")))
        }
        awaitValue { evaluate(activity.bridge.webView, "!!document.querySelector('.composer')") == "true" }
        var id = ""
        lateinit var web: WebView
        lateinit var resolver: WorkResolver
        instrumentation.runOnMainSync {
            assertNull(engine.activeId)
            id = engine.add("https://www.douyin.com/note/987654321")
            engine.next()
            resolver = MainActivity::class.java.getDeclaredField("resolver").apply { isAccessible = true }.get(activity) as WorkResolver
            val content = activity.findViewById<ViewGroup>(android.R.id.content)
            web = content.getChildAt(0) as WebView
            assertNotSame(activity.bridge.webView, web)
            assertEquals(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS, web.importantForAccessibility)
            assertFalse(web.isFocusable)
            // A local blank fixture keeps this test independent of the external site's availability.
            web.webViewClient = WebViewClient()
            web.stopLoading()
            web.settings.blockNetworkLoads = true
            web.loadDataWithBaseURL("https://www.douyin.com/note/987654321", "<html><body>fixture</body></html>", "text/html", "UTF-8", null)
            assertTrue(ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).contains(activity))
        }
        try {
            awaitValue { evaluate(activity.bridge.webView, "!!document.querySelector('.parsing-state')") == "true" }
            assertEquals("true", evaluate(activity.bridge.webView, "document.documentElement.scrollWidth <= innerWidth"))
            instrumentation.runOnMainSync {
                assertTrue(web.isAttachedToWindow)
                assertTrue(web.width > 0 && web.height > 0)
                resolver.pause()
                assertTrue(engine.repository.get(id)!!.getString("message").contains("暂停"))
                WorkResolver::class.java.getDeclaredField("remaining").apply { isAccessible = true }.setLong(resolver, 150)
            }
            SystemClock.sleep(400)
            assertEquals("resolving", engine.repository.get(id)!!.getString("status"))
            instrumentation.runOnMainSync { resolver.resume() }
            awaitValue { engine.repository.get(id)!!.optString("status") == "failed" }
            assertTrue(engine.repository.get(id)!!.getString("message").contains("超时"))
            instrumentation.runOnMainSync {
                assertNull(web.parent)
                engine.action(id, "retry")
                engine.next()
                assertEquals(id, engine.activeId)
                engine.action(id, "cancel")
                assertNull(engine.activeId)
                assertNull(MainActivity::class.java.getDeclaredField("resolver").apply { isAccessible = true }.get(activity))
            }
            assertEquals("cancelled", engine.repository.get(id)!!.optString("status"))
            awaitValue { evaluate(activity.bridge.webView, "!document.querySelector('.parsing-state') && !document.body.innerText.includes('前往网页检查')") == "true" }
        } finally {
            instrumentation.runOnMainSync {
                if (engine.activeId == id) engine.action(id, "cancel")
                activity.window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            engine.repository.writableDatabase.delete("jobs", "id=?", arrayOf(id))
            engine.publish()
        }
    }
}
