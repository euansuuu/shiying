package com.shiying.local

import android.graphics.Bitmap
import android.provider.MediaStore
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class LocalStorageTest {
    @Test fun publishAndVerifyOnlyOurNewTestImage() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        assertEquals("com.shiying.local.debug", context.packageName)
        val file = File.createTempFile("shiying-test", ".png", context.cacheDir)
        val bitmap = Bitmap.createBitmap(16,16,Bitmap.Config.ARGB_8888)
        bitmap.eraseColor(android.graphics.Color.BLUE)
        file.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG,100,it)) }
        bitmap.recycle()
        val media = MediaFiles(context) { false }
        val result = Fetched("image/png","png",file.length(),MediaFiles.digest(file))
        val work = ResolvedWork("123","album","test","test","","",emptyList(),"https://www.douyin.com/note/123","test")
        var created: android.net.Uri? = null
        try {
            val uri = media.publish(file,result,work,"test_${UUID.randomUUID()}",1) { created = it }
            context.contentResolver.query(uri,arrayOf(MediaStore.MediaColumns.IS_PENDING),null,null,null)!!.use { assertTrue(it.moveToFirst());assertEquals(0,it.getInt(0)) }
            val entry = JSONObject().put("status","completed").put("uri",uri.toString()).put("size",result.size).put("sha256",result.sha256)
            assertTrue(media.validSaved(entry))
            entry.put("sha256","invalid");assertFalse(media.validSaved(entry))
            entry.put("sha256",result.sha256)
            assertThrows(TransferStopped::class.java) { MediaFiles(context) { true }.validSaved(entry) }
            assertFalse(media.thumbnail(file,"test",1,false).isBlank())
        } finally {
            created?.let { context.contentResolver.delete(it,null,null) }
            file.delete()
            File(context.filesDir,"thumbnails/test-1.jpg").delete()
        }
    }

    @Test fun cancelledPublicationNeverLeavesAnImage() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val file = File.createTempFile("shiying-test", ".png", context.cacheDir).apply { writeBytes(ByteArray(32)) }
        val media = MediaFiles(context) { true }
        var created: android.net.Uri? = null
        try {
            assertThrows(TransferStopped::class.java) {
                media.publish(file,Fetched("image/png","png",32,""),ResolvedWork("123","album","test","test","","",emptyList(),"https://www.douyin.com/note/123","test"),"test_${UUID.randomUUID()}",1) { created = it }
            }
            val gone = try { context.contentResolver.query(created!!,arrayOf(MediaStore.MediaColumns._ID),null,null,null)?.use { !it.moveToFirst() } ?: true }
                catch (_: SecurityException) { true }
            assertTrue(gone)
        } finally { created?.let { runCatching { context.contentResolver.delete(it,null,null) } };file.delete() }
    }
}
