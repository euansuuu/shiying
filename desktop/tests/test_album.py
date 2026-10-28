from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event
from unittest.mock import patch

from PySide6.QtCore import QBuffer, QCoreApplication, QIODevice
from PySide6.QtGui import QColor, QImage

from desktop.album_service import _checkpoint, _commit, download_album, read_image
from desktop.models import Cancelled, ImagesUnavailable, Job, ResolvedAlbum, ResolvedImage, SessionConfig
from desktop.resolver import work_from_detail
from desktop.storage import Store
from desktop.worker import DownloadWorker


def image_bytes(kind: str, color: str = "#218afa") -> bytes:
    image = QImage(32, 24, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, kind)
    return bytes(buffer.data())


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.partition("?")[0]
        self.server.seen.append((path, self.headers.get("Cookie", "")))
        status, body, content_type = self.server.routes.get(path, (404, b"", "text/plain"))
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if path != "/unknown":
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *args):
        pass


class AlbumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.bodies = {kind: image_bytes(kind) for kind in ("JPEG", "PNG", "WEBP")}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2)

    def setUp(self):
        self.server.seen = []
        self.server.routes = {
            "/jpg": (200, self.bodies["JPEG"], "image/jpeg"),
            "/png": (200, self.bodies["PNG"], "image/png"),
            "/webp": (200, self.bodies["WEBP"], "application/octet-stream"),
            "/unknown": (200, self.bodies["PNG"], "image/png"),
            "/html": (200, b"<html>login</html>", "text/html"),
            "/empty": (200, b"", "image/png"),
            "/broken": (200, self.bodies["PNG"][:-12], "image/png"),
            "/denied": (403, b"", "text/plain"),
        }

    def album(self, *paths, caption="一段正文 #图文"):
        images = []
        for index, item in enumerate(paths, 1):
            candidates = item if isinstance(item, tuple) else (item,)
            images.append(ResolvedImage(index, f"image-{index}", [self.base + path for path in candidates if path]))
        return ResolvedAlbum("123456", "图文标题", "作者", images, "https://www.douyin.com/note/123456?tracking=ignore",
                             "test-agent", [{"name": "sessionid", "value": "private-value", "domain": ".douyin.com", "path": "/", "secure": True}], caption)

    def fetch(self, album, root, **kwargs):
        return download_album(album, Path(root), "testjob", kwargs.pop("emit", lambda event: None), kwargs.pop("cancel", Event()), **kwargs)

    def manifest(self, result):
        return json.loads((Path(result["result_dir"]) / "manifest.json").read_text(encoding="utf-8"))

    def test_preserves_formats_order_caption_and_does_not_store_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            album = self.album("/jpg?sign=secret", "/webp", "/png")
            result = self.fetch(album, temporary, thumbnail_dir=Path(temporary) / "cache")
            self.assertEqual(result["status"], "completed")
            self.assertEqual((result["image_done"], result["image_total"]), (3, 3))
            root = Path(result["result_dir"])
            for filename, kind in [("001.jpg", "JPEG"), ("002.webp", "WEBP"), ("003.png", "PNG")]:
                self.assertEqual((root / filename).read_bytes(), self.bodies[kind])
            self.assertEqual(Path(result["caption_path"]).read_text(encoding="utf-8"), album.caption)
            self.assertTrue(Path(result["thumbnail_path"]).is_file())
            manifest = self.manifest(result)
            raw = json.dumps(manifest)
            self.assertNotIn("private-value", raw)
            self.assertNotIn("sign=secret", raw)
            self.assertNotIn("tracking=ignore", raw)
            self.assertTrue(all(not cookie for _, cookie in self.server.seen))
            self.assertFalse(list(root.glob("*.part")))

    def test_partial_download_keeps_slots_and_retry_only_fetches_failed_items(self):
        for failed in range(3):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as temporary:
                paths = ["/jpg", "/png", "/webp"]
                paths[failed] = "/html"
                album = self.album(*paths)
                first = self.fetch(album, temporary)
                self.assertEqual(first["status"], "partial")
                self.assertEqual((first["image_done"], first["image_failed"], first["image_total"]), (2, 1, 3))
                manifest = self.manifest(first)
                self.assertEqual(manifest["images"][failed]["index"], failed + 1)
                self.assertEqual(manifest["images"][failed]["status"], "failed")
                self.server.seen.clear()
                self.server.routes["/html"] = self.server.routes["/png"]
                second = self.fetch(album, temporary, previous_dir=first["result_dir"])
                self.assertEqual(second["status"], "completed")
                self.assertEqual(second["result_dir"], first["result_dir"])
                self.assertEqual([path for path, _ in self.server.seen], ["/html"])
                self.server.routes["/html"] = (200, b"<html>login</html>", "text/html")

    def test_cancellation_keeps_committed_images_and_can_continue(self):
        with tempfile.TemporaryDirectory() as temporary:
            cancel = Event()
            def progress(event):
                if event.get("image_done") == 1:
                    cancel.set()
            with self.assertRaises(Cancelled):
                self.fetch(self.album("/jpg", "/png"), temporary, cancel=cancel, emit=progress)
            directory = Path(temporary) / "123456"
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["images"][0]["status"], "completed")
            self.assertTrue((directory / "001.jpg").exists())
            self.assertFalse(list(directory.glob("*.part")))
            self.server.seen.clear()
            result = self.fetch(self.album("/jpg", "/png"), temporary, previous_dir=str(directory))
            self.assertEqual(result["status"], "completed")
            self.assertEqual([path for path, _ in self.server.seen], ["/png"])

    def test_external_directory_and_edited_image_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            external = Path(temporary) / "123456"
            external.mkdir()
            (external / "001.jpg").write_bytes(b"user-file")
            first = self.fetch(self.album("/png"), temporary)
            self.assertNotEqual(Path(first["result_dir"]), external)
            root = Path(first["result_dir"])
            edited = image_bytes("PNG", "#ff5500")
            (root / "001.png").write_bytes(edited)
            second = self.fetch(self.album("/png"), temporary, previous_dir=str(root))
            self.assertEqual(second["status"], "completed")
            self.assertEqual((root / "001.png").read_bytes(), edited)
            self.assertEqual((root / "001_2.png").read_bytes(), self.bodies["PNG"])
            self.assertEqual((external / "001.jpg").read_bytes(), b"user-file")

    def test_changed_or_unknown_image_identity_creates_a_new_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            album = self.album("/png")
            first = self.fetch(album, temporary)
            album.images[0].key = "changed-image"
            second = self.fetch(album, temporary, previous_dir=first["result_dir"])
            self.assertNotEqual(first["result_dir"], second["result_dir"])
            album.images[0].key = ""
            third = self.fetch(album, temporary, previous_dir=second["result_dir"])
            fourth = self.fetch(album, temporary, previous_dir=third["result_dir"])
            self.assertNotEqual(third["result_dir"], fourth["result_dir"])
            self.assertTrue((Path(first["result_dir"]) / "001.png").is_file())

    def test_manifest_cannot_reference_files_outside_the_album(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = self.fetch(self.album("/png"), temporary)
            outside = Path(temporary) / "outside.png"
            outside.write_bytes(b"keep-this-file")
            manifest = self.manifest(first)
            manifest["images"][0]["file"] = "../outside.png"
            (Path(first["result_dir"]) / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            second = self.fetch(self.album("/png"), temporary, previous_dir=first["result_dir"])
            self.assertEqual(second["status"], "completed")
            self.assertEqual(outside.read_bytes(), b"keep-this-file")

    def test_bad_content_missing_urls_and_unknown_length(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.fetch(self.album("/html", "/empty", "/broken", ""), temporary)
            self.assertEqual(result["status"], "failed")
            self.assertEqual((result["image_total"], result["image_failed"]), (4, 4))
            self.assertFalse(list(Path(result["result_dir"]).glob("[0-9]*.*")))
        with tempfile.TemporaryDirectory() as temporary:
            result = self.fetch(self.album("/unknown"), temporary)
            self.assertEqual(result["status"], "completed")

    def test_candidate_fallback_and_expired_addresses(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.fetch(self.album(("/denied", "/png")), temporary)
            self.assertEqual(result["status"], "completed")
            self.assertFalse(result["refresh_needed"])
        with tempfile.TemporaryDirectory() as temporary:
            result = self.fetch(self.album("/jpg", "/denied"), temporary)
            self.assertEqual(result["status"], "partial")
            self.assertTrue(result["refresh_needed"])

    def test_size_limit_rejects_image_without_final_file(self):
        with tempfile.TemporaryDirectory() as temporary, patch("desktop.album_service.MAX_IMAGE_BYTES", 10):
            result = self.fetch(self.album("/png"), temporary)
            self.assertEqual(result["status"], "failed")
            self.assertFalse(list(Path(result["result_dir"]).glob("*.png")))

    def test_caption_failure_is_partial_and_retry_does_not_redownload_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            def fail_caption(part, directory, stem, extension):
                if stem == "文案":
                    raise PermissionError()
                return _commit(part, directory, stem, extension)
            with patch("desktop.album_service._commit", side_effect=fail_caption):
                first = self.fetch(self.album("/png"), temporary)
            self.assertEqual(first["status"], "partial")
            self.assertEqual(first["image_done"], 1)
            self.assertIn("文案", first["image_errors"][0])
            manifest = self.manifest(first)
            manifest["caption"] = "被外部编辑的无效字段"
            (Path(first["result_dir"]) / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.server.seen.clear()
            second = self.fetch(self.album("/png"), temporary, previous_dir=first["result_dir"])
            self.assertEqual(second["status"], "completed")
            self.assertEqual(self.server.seen, [])
        with tempfile.TemporaryDirectory() as temporary:
            result = self.fetch(self.album("/png", caption=""), temporary)
            self.assertEqual(result["caption_path"], "")
            self.assertFalse(list(Path(result["result_dir"]).glob("*.txt")))

    def test_checkpoint_failure_reports_committed_files_and_stops(self):
        with tempfile.TemporaryDirectory() as temporary:
            events = []
            calls = 0
            def fail_later(directory, manifest, job_id):
                nonlocal calls
                calls += 1
                if calls > 1:
                    raise PermissionError()
                return _checkpoint(directory, manifest, job_id)
            with patch("desktop.album_service._checkpoint", side_effect=fail_later), self.assertRaises(OSError):
                self.fetch(self.album("/png", "/jpg"), temporary, emit=events.append)
            self.assertTrue(any(event.get("image_done") == 1 for event in events))
            self.assertEqual([path for path, _ in self.server.seen], ["/png"])
            self.assertTrue((Path(temporary) / "123456" / "001.png").is_file())

    def test_worker_refreshes_once_and_retains_successful_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            album = self.album("/jpg", "/denied")
            worker = DownloadWorker(Job("https://www.douyin.com/note/123456", temporary), SessionConfig(Path(temporary)))
            events = []
            worker.changed.connect(lambda job_id, event: events.append(event))
            with patch("desktop.worker.resolve_work", return_value=album) as resolver:
                worker.run()
            self.assertEqual(resolver.call_count, 2)
            self.assertEqual(events[-1]["status"], "partial")
            self.assertEqual(events[-1]["image_done"], 1)
            self.assertEqual([path for path, _ in self.server.seen].count("/jpg"), 1)


class AlbumModelTests(unittest.TestCase):
    def test_parser_prioritizes_images_and_preserves_missing_entries(self):
        detail = {"aweme_id": "123", "desc": "正文", "video": {"play_addr": {"url_list": ["https://example.com/audio"]}},
                  "images": [{"uri": "one", "url_list": ["https://example.com/1", "https://example.com/2"], "video": {}}, {}, None]}
        result = work_from_detail(detail, "https://www.douyin.com/note/123", "agent", [])
        self.assertIsInstance(result, ResolvedAlbum)
        self.assertEqual(len(result.images), 3)
        self.assertEqual(len(result.images[0].urls), 2)
        self.assertEqual(result.images[1].urls, [])
        self.assertEqual(result.images[2].index, 3)
        for images in (None, [], [{}]):
            detail["images"] = images
            with self.assertRaises(ImagesUnavailable):
                work_from_detail(detail, "https://www.douyin.com/note/123", "", [])

    def test_old_video_records_and_album_progress_survive_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary))
            legacy = {"id": "old", "url": "https://www.douyin.com/video/123", "output_dir": temporary,
                      "video_id": "123", "file_path": "123.mp4", "status": "completed"}
            store.connection.execute("INSERT INTO jobs VALUES (?, ?)", ("old", json.dumps(legacy)))
            album = Job("https://www.douyin.com/note/456", temporary, content_kind="album", status="downloading",
                        work_id="456", image_total=9, image_done=5, image_failed=1, result_dir=temporary)
            store.save(album)
            jobs = {job.id: job for job in store.recover()}
            self.assertEqual(jobs["old"].work_id, "123")
            self.assertEqual(jobs["old"].content_kind, "video")
            self.assertEqual(jobs[album.id].status, "interrupted")
            self.assertEqual(jobs[album.id].image_done, 5)
            store.close()
