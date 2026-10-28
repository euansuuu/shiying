from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import uuid4

import requests
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader

from .download_service import media_session
from .models import Cancelled, ResolvedAlbum, ResolvedImage


MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 64_000_000
IMAGE_EXTENSIONS = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}


def read_image(path: Path) -> tuple[str, QImage]:
    if not 0 < path.stat().st_size <= MAX_IMAGE_BYTES:
        raise RuntimeError("图片为空或超过 50 MB 大小限制。")
    reader = QImageReader(str(path))
    reader.setDecideFormatFromContent(True)
    size = reader.size()
    if size.width() <= 0 or size.height() <= 0 or size.width() * size.height() > MAX_IMAGE_PIXELS:
        raise RuntimeError("图片尺寸无效或超过解码范围。")
    kind = bytes(reader.format()).decode("ascii", errors="ignore").lower()
    if kind not in IMAGE_EXTENSIONS or reader.imageCount() > 1:
        raise RuntimeError("暂只支持静态 JPEG、PNG、WebP 图片。")
    with path.open("rb") as stream:
        header = stream.read(12)
        stream.seek(max(0, path.stat().st_size - 12))
        tail = stream.read()
    if (kind in {"jpeg", "jpg"} and not tail.endswith(b"\xff\xd9")
            or kind == "png" and not tail.endswith(b"\0\0\0\0IEND\xaeB`\x82")
            or kind == "webp" and (header[:4] != b"RIFF" or int.from_bytes(header[4:8], "little") + 8 != path.stat().st_size)):
        raise RuntimeError("图片文件不完整，未保存为成功结果。")
    image = reader.read()
    if image.isNull():
        raise RuntimeError("图片解码失败，未保存为成功结果。")
    return IMAGE_EXTENSIONS[kind], image


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _local_file(directory: Path, name: object, pattern: str) -> Path | None:
    if not isinstance(name, str) or not re.fullmatch(pattern, name):
        return None
    path = directory / name
    return path if path.resolve().parent == directory.resolve() and not path.is_symlink() else None


def _load_manifest(directory: Path) -> dict | None:
    path = directory / "manifest.json"
    try:
        if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("application") == "Shiying" and value.get("version") == 1:
            return value
    except (OSError, ValueError):
        pass
    return None


def _matches(manifest: dict | None, album: ResolvedAlbum) -> bool:
    if not manifest or manifest.get("work_id") != album.work_id:
        return False
    previous = manifest.get("images")
    return (isinstance(previous, list) and len(previous) == len(album.images)
            and all(image.key and isinstance(old, dict) and old.get("key") == image.key and old.get("index") == image.index
                    for image, old in zip(album.images, previous)))


def _select_directory(album: ResolvedAlbum, root: Path, previous: str) -> tuple[Path, dict]:
    root.mkdir(parents=True, exist_ok=True)
    candidates = [Path(previous)] if previous else []
    candidates.extend(root / (album.work_id if index == 0 else f"{album.work_id}_{index + 1}") for index in range(1000))
    for directory in candidates:
        if directory.resolve().parent != root.resolve() or directory.is_symlink():
            continue
        if directory.exists():
            manifest = _load_manifest(directory)
            if _matches(manifest, album):
                return directory, manifest
            continue
        try:
            directory.mkdir()
        except FileExistsError:
            continue
        return directory, {
            "application": "Shiying", "version": 1, "work_id": album.work_id,
            "source": f"https://www.douyin.com/note/{album.work_id}",
            "title": album.title, "author": album.author, "notice": album.notice,
            "images": [{"index": image.index, "key": image.key, "status": "pending"} for image in album.images],
        }
    raise RuntimeError("无法创建安全的图文目录，请更换保存位置。")


def _checkpoint(directory: Path, manifest: dict, job_id: str) -> None:
    temporary = directory / f".{job_id}.manifest.part"
    if temporary.is_symlink():
        raise RuntimeError("临时清单路径异常，请更换保存目录。")
    try:
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, directory / "manifest.json")
    finally:
        temporary.unlink(missing_ok=True)


def _commit(part: Path, directory: Path, stem: str, extension: str) -> Path:
    for suffix in range(1000):
        name = f"{stem}{'_' + str(suffix + 1) if suffix else ''}.{extension}"
        target = directory / name
        if target.exists() or target.is_symlink():
            continue
        try:
            if os.name == "nt":
                os.rename(part, target)
            else:
                os.link(part, target)
                part.unlink()
            return target
        except FileExistsError:
            continue
    raise RuntimeError("同名文件过多，请更换保存目录。")


def _valid_saved(directory: Path, entry: dict) -> bool:
    path = _local_file(directory, entry.get("file"), r"\d{3,}(?:_\d+)?\.(?:jpg|png|webp)")
    try:
        if (entry.get("status") != "completed" or not path or not path.is_file()
                or path.stat().st_size != entry.get("size") or _digest(path) != entry.get("sha256")):
            return False
        read_image(path)
        return True
    except (OSError, RuntimeError):
        return False


def _fetch_image(asset: ResolvedImage, session: requests.Session, part: Path,
                 emit: Callable[[dict], None], cancel: Event) -> tuple[str, QImage, bool]:
    expired = False
    failure = "页面未提供该图片的可用地址。"
    for url in asset.urls:
        for attempt in range(2):
            if cancel.is_set():
                raise Cancelled()
            try:
                with session.get(url, stream=True, timeout=(10, 15)) as response:
                    if response.status_code in {401, 403, 410}:
                        expired = True
                        failure = "图片地址不可用，请重新获取作品信息。"
                        break
                    response.raise_for_status()
                    kind = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    if kind and not (kind.startswith("image/") or kind == "application/octet-stream"):
                        failure = "地址返回了网页或错误内容。"
                        break
                    length = response.headers.get("Content-Length", "")
                    total = int(length) if length.isdigit() and response.headers.get("Content-Encoding", "identity") == "identity" else None
                    if total is not None and total > MAX_IMAGE_BYTES:
                        failure = "图片超过 50 MB 大小限制。"
                        break
                    count = 0
                    start = last = time.monotonic()
                    emit({"current_image": asset.index, "image_bytes": 0, "image_size": total, "speed": 0})
                    with part.open("wb") as output:
                        for chunk in response.iter_content(64 * 1024):
                            if cancel.is_set():
                                raise Cancelled()
                            if not chunk:
                                continue
                            count += len(chunk)
                            if count > MAX_IMAGE_BYTES:
                                raise RuntimeError("图片超过 50 MB 大小限制。")
                            output.write(chunk)
                            now = time.monotonic()
                            if now - last >= 0.15:
                                emit({"image_bytes": count, "speed": count / max(now - start, 0.001)})
                                last = now
                    if total is not None and count != total:
                        failure = "图片传输不完整。"
                        continue
                    extension, image = read_image(part)
                    return extension, image, False
            except requests.RequestException:
                failure = "图片网络请求失败。"
                if not attempt and not cancel.wait(0.3):
                    continue
            except RuntimeError as exc:
                failure = str(exc)
                break
    if cancel.is_set():
        raise Cancelled()
    return failure, QImage(), expired


def download_album(album: ResolvedAlbum, output_dir: Path, job_id: str,
                   emit: Callable[[dict], None], cancel: Event,
                   previous_dir: str = "", thumbnail_dir: Path | None = None) -> dict:
    if not album.work_id.isdigit() or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id):
        raise RuntimeError("作品或任务标识无效。")
    if not album.images or len(album.images) > 1000 or [image.index for image in album.images] != list(range(1, len(album.images) + 1)):
        raise RuntimeError("图片清单无效。")
    if cancel.is_set():
        raise Cancelled()
    QImageReader.setAllocationLimit(256)
    directory, manifest = _select_directory(album, output_dir, previous_dir)
    entries = manifest["images"]
    manifest.update({"title": album.title, "author": album.author, "notice": album.notice})
    thumbnail = ""
    for entry in entries:
        if not _valid_saved(directory, entry):
            entry.update({"status": "pending", "error": "", "expired": False})

    def progress() -> dict:
        completed = [entry for entry in entries if entry["status"] == "completed"]
        errors = [f"第 {entry['index']} 张：{entry.get('error') or '未完成'}" for entry in entries if entry["status"] == "failed"]
        result = {"content_kind": "album", "result_dir": str(directory), "file_path": "", "image_total": len(entries),
                  "image_done": len(completed), "image_failed": len(errors), "image_errors": errors,
                  "downloaded": sum(entry.get("size", 0) for entry in completed), "total": None, "notice": album.notice,
                  "thumbnail_path": thumbnail}
        emit(result)
        return result

    def preview(path: Path, image: QImage | None = None) -> None:
        nonlocal thumbnail
        if thumbnail or thumbnail_dir is None:
            return
        try:
            if image is None:
                _, image = read_image(path)
            thumbnail_dir.mkdir(parents=True, exist_ok=True)
            target = thumbnail_dir / f"{job_id}.png"
            if image.scaled(QSize(92, 128), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation).save(str(target), "PNG"):
                thumbnail = str(target)
        except (OSError, RuntimeError):
            pass

    part = directory / f".{job_id}.image.part"
    if part.is_symlink():
        raise RuntimeError("临时图片路径异常，请更换保存目录。")
    try:
        _checkpoint(directory, manifest, job_id)
        emit({"status": "downloading", "current_image": 0, "image_bytes": 0, "image_size": None, "caption_path": "", "speed": 0, "message": ""})
        progress()
        with media_session(album) as session:
            for asset, entry in zip(album.images, entries):
                if cancel.is_set():
                    raise Cancelled()
                if entry["status"] == "completed":
                    preview(directory / entry["file"])
                    progress()
                    continue
                extension, image, expired = _fetch_image(asset, session, part, emit, cancel)
                if image.isNull():
                    entry.update({"status": "failed", "error": extension, "expired": expired})
                else:
                    if cancel.is_set():
                        raise Cancelled()
                    path = _commit(part, directory, f"{asset.index:03d}", extension)
                    entry.update({"status": "completed", "file": path.name, "size": path.stat().st_size,
                                  "sha256": _digest(path), "error": "", "expired": False})
                    preview(path, image)
                progress()
                _checkpoint(directory, manifest, job_id)
        caption_path = ""
        caption_error = ""
        if album.caption:
            try:
                previous = manifest.get("caption") or {}
                if not isinstance(previous, dict):
                    previous = {}
                old = _local_file(directory, previous.get("file"), r"文案(?:_\d+)?\.txt")
                desired = hashlib.sha256(album.caption.encode("utf-8")).hexdigest()
                if old and old.is_file() and _digest(old) == desired:
                    caption_path = str(old)
                else:
                    part.write_text(album.caption, encoding="utf-8")
                    caption_path = str(_commit(part, directory, "文案", "txt"))
                manifest["caption"] = {"file": Path(caption_path).name, "sha256": desired, "status": "completed"}
            except OSError:
                caption_error = "图片已保存，文案写入失败，请检查目录权限或磁盘空间。"
                manifest["caption"] = {"status": "failed", "error": caption_error}
        if not album.caption:
            manifest.pop("caption", None)
        result = dict(progress())
        result["image_errors"] = list(result["image_errors"])
        if caption_error:
            result["image_errors"].append("文案：" + caption_error)
        complete = result["image_done"] == len(entries) and not caption_error
        result.update({"status": "completed" if complete else "partial" if result["image_done"] else "failed",
                       "caption_path": caption_path, "current_image": 0, "image_bytes": 0, "image_size": None, "speed": 0,
                       "refresh_needed": any(entry.get("expired") and entry["status"] != "completed" for entry in entries),
                       "message": "图片已按原顺序保存到本机。" if complete else caption_error or "部分图片未完成，已保存的图片会保留。" if result["image_done"] else "未能保存图片，请查看失败原因后重试。"})
        _checkpoint(directory, manifest, job_id)
        return result
    except (Cancelled, OSError):
        progress()
        try:
            _checkpoint(directory, manifest, job_id)
        except OSError:
            pass
        raise
    finally:
        part.unlink(missing_ok=True)
