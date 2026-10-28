package com.shiying.local

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

class Repository(context: Context) : SQLiteOpenHelper(context, "shiying.sqlite3", null, 1) {
    val preferences = context.getSharedPreferences("local", Context.MODE_PRIVATE)
    override fun onCreate(db: SQLiteDatabase) { db.execSQL("CREATE TABLE jobs(id TEXT PRIMARY KEY, created INTEGER NOT NULL, data TEXT NOT NULL)") }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    @Synchronized fun all(): List<JSONObject> = readableDatabase.rawQuery("SELECT data FROM jobs ORDER BY created DESC", null).use { cursor ->
        buildList { while (cursor.moveToNext()) add(JSONObject(cursor.getString(0))) }
    }
    @Synchronized fun get(id: String): JSONObject? = readableDatabase.rawQuery("SELECT data FROM jobs WHERE id=?", arrayOf(id)).use { if (it.moveToFirst()) JSONObject(it.getString(0)) else null }
    @Synchronized fun save(job: JSONObject) {
        val values = ContentValues().apply { put("id", job.getString("id")); put("created", job.getLong("createdAt")); put("data", job.toString()) }
        writableDatabase.insertWithOnConflict("jobs", null, values, SQLiteDatabase.CONFLICT_REPLACE)
    }
    fun recover() { all().filter { it.optString("status") in ACTIVE }.forEach { it.put("status", "interrupted").put("speed", 0).put("message", "上次任务已中断；已保存文件保留，可继续下载。"); save(it) } }
    fun snapshot(): JSONObject = JSONObject().put("jobs", JSONArray(all())).put("theme", theme()).put("remember", remember()).put("sharedText", "")
    fun theme(): String = preferences.getString("theme", "system") ?: "system"
    fun remember(): Boolean = preferences.getBoolean("remember", true)

    fun create(source: String): JSONObject {
        val id = WorkParser.workId(source)
        require(all().none { it.optString("status") in ACTIVE && (it.optString("source") == source || id.isNotEmpty() && it.optString("workId") == id) }) { "这个作品已经在下载队列中。" }
        val job = JSONObject().put("id", UUID.randomUUID().toString()).put("createdAt", System.currentTimeMillis()).put("source", source)
            .put("workId", id).put("kind", "unknown").put("title", "待解析的抖音作品").put("author", "").put("caption", "")
            .put("status", "queued").put("message", "").put("notice", "").put("assets", JSONArray())
        for (name in listOf("total", "done", "failed", "bytes", "currentBytes", "currentTotal", "current", "speed")) job.put(name, 0)
        save(job)
        return job
    }
    companion object { val ACTIVE = setOf("queued", "resolving", "verification", "downloading") }
}
