from __future__ import annotations

import json
import os
import struct
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event

from desktop.download_service import download_video, validate_mp4
from desktop.models import Cancelled, Job, MediaExpired, ResolvedVideo, extract_url, work_id_from_url
from desktop.resolver import detail_from_payload, video_from_detail
from desktop.storage import CookieVault, Store, import_cookies


def mp4_bytes(size: int = 160000) -> bytes:
    def box(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I4s", len(data) + 8, kind) + data
    return box(b"ftyp", b"isom\0\0\0\0isom") + box(b"moov", b"") + box(b"mdat", b"x" * size)


class LinkTests(unittest.TestCase):
    def test_extracts_supported_links_from_share_text(self):
        self.assertEqual(extract_url("复制 https://v.douyin.com/AbC_12-x/。"), "https://v.douyin.com/AbC_12-x/")
        self.assertEqual(extract_url("https://www.douyin.com/video/123?from=web"), "https://www.douyin.com/video/123?from=web")
        self.assertEqual(extract_url("复制 https://www.douyin.com/note/123。"), "https://www.douyin.com/note/123")
        self.assertEqual(work_id_from_url("https://www.douyin.com/note/123?x=1"), "123")

    def test_rejects_lookalike_domains_and_unsupported_content(self):
        for url in [
            "https://v.douyin.com.evil.test/abc/", "https://douyin.com@evil.test/video/123",
            "https://www.douyin.com/user/123", "file:///video/123", "没有链接",
            "https://www.douyin.com:444/video/123",
            "https://www.douyin.com/note/../123", "https://www.douyin.com/note/not-an-id",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                extract_url(url)

    def test_only_accepts_the_requested_video(self):
        good = {"aweme_id": "123", "video": {"play_addr": {"url_list": ["https://example.com/a.mp4"]}}}
        payload = {"recommendation": {"aweme_id": "999", "video": {}}, "data": [good]}
        self.assertEqual(detail_from_payload(payload, "123"), good)
        self.assertIsNone(detail_from_payload(payload, "456"))
        self.assertIsNone(detail_from_payload(payload, ""))
        result = video_from_detail(good, "https://www.douyin.com/video/123", "test-agent", [])
        self.assertEqual(result.video_id, "123")
        self.assertEqual(result.urls, ["https://example.com/a.mp4"])

    def test_invalid_details_do_not_produce_a_download(self):
        for detail in [
            {"aweme_id": "../bad", "video": {}}, {"aweme_id": "123", "images": []},
            {"aweme_id": "123", "video": {"play_addr": []}},
            {"aweme_id": "123", "video": {"play_addr": {"url_list": "https://example.com"}}},
        ]:
            with self.subTest(detail=detail), self.assertRaises(RuntimeError):
                video_from_detail(detail, "", "", [])


class StorageTests(unittest.TestCase):
    def test_recovers_unfinished_jobs_without_losing_completed_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            store = Store(directory)
            pending = Job("https://v.douyin.com/abc/", temporary, status="downloading", downloaded=42)
            completed = Job("https://v.douyin.com/xyz/", temporary, status="completed", title="中文标题")
            store.save(pending)
            store.save(completed)
            store.close()
            store = Store(directory)
            recovered = {job.id: job for job in store.recover()}
            self.assertEqual(recovered[pending.id].status, "interrupted")
            self.assertEqual(recovered[pending.id].downloaded, 42)
            self.assertEqual(recovered[completed.id].title, "中文标题")
            self.assertEqual(recovered[completed.id].status, "completed")
            store.close()

    def test_cookie_import_filters_domain_and_expiry_and_preserves_session_cookies(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cookies.txt"
            future = int(time.time()) + 3600
            path.write_text(
                "# Netscape HTTP Cookie File\n"
                f"#HttpOnly_.douyin.com\tTRUE\t/\tTRUE\t{future}\tsessionid\tprivate-value\n"
                ".douyin.com\tTRUE\t/\tFALSE\t0\tbrowser_session\ttemporary-value\n"
                ".douyin.com\tTRUE\t/\tFALSE\t1\texpired\told\n"
                f".evil.test\tTRUE\t/\tFALSE\t{future}\tforeign\tother\n",
                encoding="utf-8",
            )
            cookies = import_cookies(path)
            self.assertEqual({cookie["name"] for cookie in cookies}, {"sessionid", "browser_session"})
            self.assertTrue(next(cookie for cookie in cookies if cookie["name"] == "sessionid")["httpOnly"])
            self.assertNotIn("expires", next(cookie for cookie in cookies if cookie["name"] == "browser_session"))

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_cookie_vault_is_encrypted_and_corruption_does_not_expose_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = CookieVault(Path(temporary))
            cookies = [{"name": "sessionid", "value": "private-value"}]
            vault.save(cookies)
            self.assertNotIn(b"private-value", vault.path.read_bytes())
            self.assertEqual(vault.load(), cookies)
            vault.path.write_bytes(b"invalid")
            with self.assertRaisesRegex(RuntimeError, "重新导入"):
                vault.load()
            vault.clear()
            self.assertFalse(vault.path.exists())


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.seen.append((self.path, self.headers.get("Cookie", "")))
        if self.path == "/denied":
            self.send_response(403)
            self.end_headers()
            return
        body = b"<html>blocked</html>" if self.path == "/html" else self.server.body
        if self.path == "/broken":
            body = body[:-25]
        self.send_response(200)
        self.send_header("Content-Type", "text/html" if self.path == "/html" else "application/octet-stream")
        if self.path != "/unknown-length":
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            if self.path == "/slow":
                for index in range(0, len(body), 65536):
                    self.wfile.write(body[index:index + 65536])
                    self.wfile.flush()
                    time.sleep(0.2)
            else:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *args):
        pass


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.server.body = mp4_bytes()
        cls.server.seen = []
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2)

    def video(self, *paths):
        return ResolvedVideo(
            "123456", "测试视频", "作者", [self.base + path for path in paths],
            "https://www.douyin.com/video/123456", "test-agent",
            [{"name": "sessionid", "value": "private-value", "domain": ".douyin.com", "path": "/", "secure": True}],
        )

    def test_streams_a_valid_mp4_and_does_not_leak_douyin_cookies(self):
        with tempfile.TemporaryDirectory() as temporary:
            events = []
            path = download_video(self.video("/good"), Path(temporary), "one", events.append, Event())
            self.assertTrue(validate_mp4(path))
            self.assertEqual(path.read_bytes(), self.server.body)
            self.assertFalse(list(Path(temporary).glob("*.part")))
            self.assertEqual(self.server.seen[-1][1], "")
            self.assertTrue(any(event.get("status") == "finalizing" for event in events))

    def test_html_and_broken_candidates_fall_back_without_creating_fake_mp4(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = download_video(self.video("/html", "/broken", "/good"), Path(temporary), "two", lambda e: None, Event())
            self.assertTrue(validate_mp4(path))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(RuntimeError):
                download_video(self.video("/html", "/broken"), Path(temporary), "bad", lambda e: None, Event())
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_unknown_length_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            events = []
            path = download_video(self.video("/unknown-length"), Path(temporary), "three", events.append, Event())
            self.assertTrue(validate_mp4(path))
            first = next(event for event in events if event.get("status") == "downloading")
            self.assertIsNone(first["total"])

    def test_cancellation_removes_the_part_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            cancel = Event()
            def progress(event):
                if event.get("downloaded", 0) > 0:
                    cancel.set()
            with self.assertRaises(Cancelled):
                download_video(self.video("/slow"), Path(temporary), "cancel", progress, cancel)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_existing_valid_file_is_reused_and_invalid_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "123456.mp4"
            path.write_bytes(self.server.body)
            video = self.video("/denied")
            self.assertEqual(download_video(video, Path(temporary), "reuse", lambda e: None, Event()), path)
            path.write_bytes(b"this file belongs to the user")
            with self.assertRaisesRegex(RuntimeError, "同名文件"):
                download_video(video, Path(temporary), "keep", lambda e: None, Event())
            self.assertEqual(path.read_bytes(), b"this file belongs to the user")

    def test_expired_media_signals_a_reparse(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(MediaExpired):
                download_video(self.video("/denied"), Path(temporary), "expired", lambda e: None, Event())
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_container_validation_rejects_truncation_and_empty_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.mp4"
            for body in [b"", b"<html>wrong</html>", self.server.body[:-1], mp4_bytes(0)]:
                path.write_bytes(body)
                self.assertFalse(validate_mp4(path))
