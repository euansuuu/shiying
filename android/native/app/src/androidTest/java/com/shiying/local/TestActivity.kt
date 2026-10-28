package com.shiying.local

import android.content.Intent
import android.os.SystemClock
import android.view.WindowManager
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage

internal fun launchTestActivity(intent: Intent): MainActivity {
    val instrumentation = InstrumentationRegistry.getInstrumentation()
    instrumentation.runOnMainSync { instrumentation.targetContext.startActivity(intent) }
    val deadline = SystemClock.elapsedRealtime() + 15000
    while (SystemClock.elapsedRealtime() < deadline) {
        var activity: MainActivity? = null
        instrumentation.runOnMainSync {
            activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED)
                .filterIsInstance<MainActivity>().firstOrNull { it.foreground }
            activity?.window?.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
        activity?.let { return it }
        SystemClock.sleep(100)
    }
    error("Unlock the phone and keep Shiying in the foreground before running device tests")
}
