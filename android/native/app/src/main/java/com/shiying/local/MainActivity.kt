package com.shiying.local

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.View
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.getcapacitor.BridgeActivity
import java.lang.ref.WeakReference

class MainActivity : BridgeActivity() {
    @Volatile var foreground = false
    private var resolver: WorkResolver? = null
    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(ShiyingLocalPlugin::class.java)
        super.onCreate(savedInstanceState)
        val engine = LocalEngine.of(this)
        engine.activity = WeakReference(this)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val content = findViewById<View>(android.R.id.content)
        ViewCompat.setOnApplyWindowInsetsListener(content) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
        applyAppearance()
    }
    fun applyAppearance() {
        val theme = LocalEngine.of(this).repository.theme()
        val dark = theme == "dark" || theme == "system" && resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES
        val background = Color.parseColor(if (dark) "#0e1829" else "#f4f8fe")
        window.decorView.setBackgroundColor(background)
        bridge?.webView?.setBackgroundColor(background)
        WindowCompat.getInsetsController(window, window.decorView).apply { isAppearanceLightStatusBars = !dark; isAppearanceLightNavigationBars = !dark }
    }
    fun requestDownloadNotification() {
        val preferences = LocalEngine.of(this).repository.preferences
        if (Build.VERSION.SDK_INT >= 33 && !preferences.getBoolean("asked_notifications", false) && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            preferences.edit().putBoolean("asked_notifications", true).apply()
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 4108)
        }
    }
    fun startResolution(id: String) {
        resolver?.close()
        val next = WorkResolver(this, id)
        resolver = next
        next.start()
    }
    fun closeResolution(id: String) { resolver?.takeIf { it.jobId == id }?.close() }
    fun releaseResolver(value: WorkResolver) { if (resolver === value) resolver = null }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.action == Intent.ACTION_SEND && intent.type == "text/plain") {
            val text = intent.getStringExtra(Intent.EXTRA_TEXT)?.take(32000) ?: return
            val engine = LocalEngine.of(this)
            engine.sharedText = text
            engine.plugin?.get()?.shared(text)
            intent.removeExtra(Intent.EXTRA_TEXT)
        }
    }
    override fun onResume() {
        super.onResume(); foreground = true
        LocalEngine.of(this).activity = WeakReference(this)
        resolver?.resume()
        LocalEngine.of(this).handler.post { LocalEngine.of(this).next() }
    }
    override fun onPause() { foreground = false; resolver?.pause(); super.onPause() }
    override fun onDestroy() {
        val engine = LocalEngine.of(this)
        if (engine.activity?.get() === this) engine.activity = null
        resolver?.let { it.close(); engine.finishResolution(it.jobId, "interrupted", "解析已中断，返回拾影后可重试。") }
        super.onDestroy()
    }
    override fun onConfigurationChanged(newConfig: Configuration) { super.onConfigurationChanged(newConfig); applyAppearance() }
}
