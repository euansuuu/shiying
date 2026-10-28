from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEventLoop, QThread, QTimer

from desktop.models import Cancelled, Deferred, Job, MediaExpired, ResolvedVideo, SessionConfig
from desktop.worker import DownloadWorker


class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_worker_completes_in_a_thread_and_shuts_it_down(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / "123.mp4"
            path.write_bytes(b"test")
            video = ResolvedVideo("123", "标题", "作者", ["https://example.com/video"], "", "", [])
            worker = DownloadWorker(Job("https://www.douyin.com/video/123", temporary), SessionConfig(directory))
            thread = QThread()
            events = []
            worker.changed.connect(lambda job_id, event: events.append(event))
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            loop = QEventLoop()
            thread.finished.connect(loop.quit)
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            with patch("desktop.worker.resolve_work", return_value=video), patch("desktop.worker.download_video", return_value=path):
                thread.start()
                timer.start(5000)
                loop.exec()
            timer.stop()
            self.assertFalse(thread.isRunning(), "Worker thread did not stop")
            self.assertEqual(events[-1]["status"], "completed")
            self.assertEqual(events[-1]["file_path"], str(path))
            thread.deleteLater()
            self.app.processEvents()

    def test_cancel_and_defer_are_distinct_terminal_states(self):
        with tempfile.TemporaryDirectory() as temporary:
            for error, status in [(Cancelled(), "cancelled"), (Deferred(), "deferred")]:
                events = []
                worker = DownloadWorker(Job("https://v.douyin.com/abc/", temporary), SessionConfig(Path(temporary)))
                worker.changed.connect(lambda job_id, event: events.append(event))
                with patch("desktop.worker.resolve_work", side_effect=error):
                    worker.run()
                self.assertEqual(events[-1]["status"], status)

    def test_expired_media_is_only_reparsed_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            events = []
            worker = DownloadWorker(Job("https://v.douyin.com/abc/", temporary), SessionConfig(Path(temporary)))
            worker.changed.connect(lambda job_id, event: events.append(event))
            video = ResolvedVideo("123", "title", "author", [], "", "", [])
            with patch("desktop.worker.resolve_work", return_value=video) as resolver, patch(
                "desktop.worker.download_video", side_effect=MediaExpired()
            ):
                worker.run()
            self.assertEqual(resolver.call_count, 2)
            self.assertEqual(events[-1]["status"], "failed")
