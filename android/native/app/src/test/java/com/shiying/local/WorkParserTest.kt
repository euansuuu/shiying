package com.shiying.local

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.File

class WorkParserTest {
    private fun video(vararg urls: String) = JSONObject().put("aweme_id","123").put("video",JSONObject().put("play_addr",JSONObject().put("url_list",org.json.JSONArray(urls.toList()))))

    @Test fun mobileWatermarkRouteUsesTheSameVideoOrdinaryPlaybackRoute() {
        val marked = "https://aweme.snssdk.com/aweme/v1/playwm/?video_id=example&ratio=720p&line=0"
        val work = WorkParser.parse(video(marked),"123","https://www.douyin.com/video/123","agent")
        assertEquals(listOf(marked.replace("/playwm/","/play/")),work.assets.single().urls)
        assertEquals("123:playback-v1",work.assets.single().key)
    }

    @Test fun signedCdnAddressesStayIntactAndExplicitWatermarkFallbacksAreExcluded() {
        val signed = "https://cdn.example/a%2Fb.mp4?signature=a%2Bb%3D&x-expires=123"
        val work = WorkParser.parse(video("https://www.douyin.com/aweme/v1/play/?video_id=x&watermark=1",signed),"123","https://www.douyin.com/video/123","agent")
        assertEquals(listOf(signed),work.assets.single().urls)
        for (marked in listOf("https://other.example/aweme/v1/playwm/?video_id=x","https://www.douyin.com/aweme/v1/play/?video_id=x&watermark=1")) {
            assertThrows(IllegalStateException::class.java) { WorkParser.parse(video(marked),"123","https://www.douyin.com/video/123","agent") }
        }
    }

    @Test fun watermarkChecksCoverRedirectsEncodedFlagsAndDuplicateParameters() {
        for (url in listOf("https://cdn.example/playwm/x", "https://cdn.example/x?watermark=0&watermark=1", "https://cdn.example/x?%77atermark=%31", "https://cdn.example/x?Watermark=true", "not a URI")) assertTrue(WorkParser.isWatermarked(url))
        assertFalse(WorkParser.isWatermarked("https://cdn.example/x?watermark=0&signature=a%2Fb"))
        assertThrows(IllegalStateException::class.java) { WorkParser.parse(video("https://aweme.snssdk.com/aweme/v1/playwm/?video_id=x&video_id=y"),"123","https://www.douyin.com/video/123","agent") }
    }
    @Test fun mobileShareWorkIdAndNavigationStayOnOfficialWorkPaths() {
        val source = "https://www.iesdouyin.com/share/video/123/?from_ssr=1&share_sign=example"
        assertEquals("123", WorkParser.workId(source))
        assertTrue(WorkParser.allowedNavigation(source))
        for (url in listOf("https://www.iesdouyin.com/anything/123/", "https://www.iesdouyin.com/passport/?modal_id=123", "https://www.iesdouyin.com.evil.com/share/video/123/", "https://user@www.iesdouyin.com/share/video/123/", "https://www.iesdouyin.com:444/share/video/123/", "http://www.iesdouyin.com/share/video/123/")) {
            assertEquals("", WorkParser.workId(url))
            assertFalse(WorkParser.allowedNavigation(url))
        }
    }
    @Test fun officialShortLinkIntermediateRedirectsToTheCanonicalWork() {
        assertEquals("https://www.douyin.com/note/7680473530756571377",WorkParser.canonicalRedirect("https://www.iesdouyin.com/share/note/7680473530756571377/?from=web"))
        assertEquals("https://www.douyin.com/note/123",WorkParser.canonicalRedirect("https://www.iesdouyin.com/share/slides/123/"))
        assertEquals("https://www.douyin.com/video/123",WorkParser.canonicalRedirect("https://www.iesdouyin.com/share/video/123/"))
        for (url in listOf("https://evil.com/share/video/123/","https://www.iesdouyin.com.evil.com/share/video/123/","https://www.iesdouyin.com/anything/123/","http://www.iesdouyin.com/share/video/123/")) assertEquals("",WorkParser.canonicalRedirect(url))
    }
    @Test fun recognizesModalRedirectOnlyOnARealWorkPage() {
        assertEquals("123",WorkParser.workId("https://www.douyin.com/?modal_id=123"))
        assertEquals("123",WorkParser.workId("https://www.douyin.com/user/MS4w?modal_id=123"))
        assertEquals("",WorkParser.workId("https://www.douyin.com/passport/web/login/?modal_id=123"))
        assertEquals("",WorkParser.workId("https://www.douyin.com/?modal_id=123&modal_id=456"))
        assertEquals("",WorkParser.workId("https://evil.com/?modal_id=123"))
    }
    @Test fun extractOnlySupportedCanonicalLinks() {
        assertEquals("https://v.douyin.com/ABC_123/", WorkParser.extract("复制 https://v.douyin.com/ABC_123/?secret=1 。"))
        assertEquals("https://www.douyin.com/note/123", WorkParser.extract("https://www.douyin.com/note/123?modal_id=456"))
        for (link in listOf("https://douyin.com.evil.com/video/123", "https://evil.com@douyin.com/video/123", "https://douyin.com:999/video/123", "https://www.douyin.com/user/123")) {
            assertThrows(IllegalStateException::class.java) { WorkParser.extract(link) }
        }
    }

    @Test fun albumWinsOverVideoAndPreservesMissingSlots() {
        val detail = JSONObject("""{"aweme_id":"123","desc":"文案","author":{"nickname":"作者"},"music":{},"video":{"play_addr":{"url_list":["https://cdn.example/cover.mp4"]}},"images":[{"uri":"a","url_list":["https://cdn.example/a.webp"],"video":{"id":"live"}},{"uri":null,"url_list":[]},{"image_id":"c","url_list":["javascript:alert(1)","http://cdn.example/a.png","https://x@y.com/a","https://cdn.example/c.png"]}]}""")
        val work = WorkParser.parse(detail, "123", "https://www.douyin.com/note/123", "agent")
        assertEquals("album", work.kind)
        assertEquals(listOf(1,2,3), work.assets.map { it.index })
        assertEquals("", work.assets[1].key)
        assertTrue(work.assets[1].urls.isEmpty())
        assertEquals(listOf("https://cdn.example/c.png"), work.assets[2].urls)
        assertTrue(work.notice.contains("实况"))
        assertTrue(work.notice.contains("配乐"))
        assertEquals("文案", work.caption)
    }

    @Test fun rejectsOtherWorksAndEmptyNotes() {
        val detail = JSONObject("""{"aweme_id":"123","video":{"play_addr":{"url_list":["https://cdn.example/a.mp4"]}}}""")
        assertThrows(IllegalArgumentException::class.java) { WorkParser.parse(detail,"124","https://www.douyin.com/video/124","agent") }
        assertThrows(IllegalArgumentException::class.java) { WorkParser.parse(detail,"123","https://www.douyin.com/note/123","agent") }
        assertEquals("video", WorkParser.parse(detail,"123","https://www.douyin.com/video/123","agent").kind)
    }

    @Test fun mp4MustContainCompleteBoxesAndMedia() {
        fun box(type: String, bytes: ByteArray): ByteArray = ByteArrayOutputStream().also { stream -> DataOutputStream(stream).use { it.writeInt(8+bytes.size);it.writeBytes(type);it.write(bytes) } }.toByteArray()
        val valid = box("ftyp",ByteArray(8))+box("moov",ByteArray(4))+box("mdat",ByteArray(10))
        val file = File.createTempFile("shiying-test", ".mp4")
        try {
            file.writeBytes(valid); assertTrue(MediaFiles.validMp4(file))
            file.writeBytes(valid.copyOf(valid.size-2)); assertFalse(MediaFiles.validMp4(file))
            file.writeText("<html>This is a verification page, not a video</html>"); assertFalse(MediaFiles.validMp4(file))
            file.writeBytes(box("ftyp",ByteArray(8))+box("moov",ByteArray(4))+box("mdat",ByteArray(0))); assertFalse(MediaFiles.validMp4(file))
        } finally { file.delete() }
    }
}
