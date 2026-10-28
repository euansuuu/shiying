package com.shiying.local

import android.app.Application
import android.webkit.CookieManager
import android.webkit.WebStorage

class ShiyingApplication : Application() {
    lateinit var engine: LocalEngine
    override fun onCreate() {
        super.onCreate()
        engine = LocalEngine(this)
        engine.repository.recover()
        if (!engine.repository.remember()) clearCookies {}
    }
    fun clearCookies(done: () -> Unit) {
        CookieManager.getInstance().removeAllCookies { CookieManager.getInstance().flush(); WebStorage.getInstance().deleteAllData(); done() }
    }
}
