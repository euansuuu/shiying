from __future__ import annotations

import logging
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from .download_service import download_video
from .album_service import download_album
from .models import Cancelled, Deferred, JOB_EVENT_FIELDS, Job, MediaExpired, ResolvedAlbum, SessionConfig
from .resolver import resolve_work


class DownloadWorker(QObject):
    changed = Signal(str, object)
    finished = Signal()

    def __init__(self, job: Job, config: SessionConfig):
        super().__init__()
        self.job = job
        self.config = config
        self.cancel = Event()
        self.resume = Event()
        self.defer = Event()
        self.show_browser = Event()

    def emit(self, event: dict) -> None:
        event = {key: list(value) if key == "image_errors" else value for key, value in event.items()}
        for key, value in event.items():
            if key in JOB_EVENT_FIELDS:
                setattr(self.job, key, value)
        self.changed.emit(self.job.id, event)

    @Slot()
    def run(self) -> None:
        try:
            for attempt in range(2):
                work = resolve_work(
                    self.job.url, self.config, self.emit,
                    self.cancel, self.resume, self.defer, self.show_browser,
                )
                if isinstance(work, ResolvedAlbum):
                    self.emit({"title": work.title, "author": work.author, "work_id": work.work_id,
                               "content_kind": "album", "image_total": len(work.images), "notice": work.notice})
                    result = download_album(work, self.job.destination, self.job.id, self.emit, self.cancel,
                                            self.job.result_dir, self.config.data_dir / "thumbnails")
                    refresh = result.pop("refresh_needed", False)
                    if refresh and not attempt:
                        self.emit({key: value for key, value in result.items() if key not in {"status", "message"}})
                        self.emit({"status": "resolving", "message": "部分图片地址不可用，正在重新获取作品信息；已保存图片会保留。"})
                        continue
                    self.emit(result)
                    break
                self.emit({"title": work.title, "author": work.author, "work_id": work.video_id, "content_kind": "video",
                           "result_dir": "", "caption_path": "", "thumbnail_path": "", "notice": "", "image_total": 0,
                           "image_done": 0, "image_failed": 0, "image_errors": []})
                try:
                    path = download_video(work, self.job.destination, self.job.id, self.emit, self.cancel)
                    self.emit({
                        "status": "completed", "file_path": str(path), "speed": 0,
                        "downloaded": path.stat().st_size, "total": path.stat().st_size,
                        "message": "视频已保存到本机。",
                    })
                    break
                except MediaExpired:
                    if attempt:
                        raise RuntimeError("重新解析后视频地址仍不可用，请稍后重试。")
                    self.emit({"status": "resolving", "message": "视频地址过期，正在重新解析…"})
        except Cancelled:
            self.emit({"status": "cancelled", "speed": 0, "message": "下载已取消；已保存图片会保留，可继续下载。" if self.job.content_kind == "album" else "下载已取消，可重新下载。"})
        except Deferred:
            self.emit({"status": "deferred", "speed": 0, "message": "已暂缓处理，可点击重新解析。"})
        except (RuntimeError, OSError, ValueError) as exc:
            message = str(exc) if isinstance(exc, RuntimeError) else "本地文件操作失败，请检查保存目录、磁盘空间和文件权限。"
            partial = self.job.content_kind == "album" and self.job.image_done > 0
            event = {"status": "partial" if partial else "failed", "speed": 0, "message": message}
            if self.job.content_kind == "album":
                event["image_errors"] = self.job.image_errors + [message]
            self.emit(event)
        except Exception as exc:
            logging.getLogger("shiying").error("Task %s failed: %s", self.job.id, type(exc).__name__)
            self.emit({"status": "failed", "speed": 0, "message": f"发生未预期错误（{type(exc).__name__}），请重新下载。"})
        finally:
            self.finished.emit()
