from __future__ import annotations

import os
import struct
import time
from pathlib import Path
from threading import Event
from typing import Callable
from urllib.parse import urlsplit

import requests

from .models import Cancelled, MediaExpired, ResolvedAlbum, ResolvedVideo


def media_session(work: ResolvedVideo | ResolvedAlbum) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": work.user_agent, "Referer": work.referer, "Accept-Encoding": "identity"})
    for cookie in work.cookies:
        session.cookies.set(
            cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie.get("path") or "/",
            secure=bool(cookie.get("secure")), expires=int(cookie["expires"]) if cookie.get("expires", -1) > 0 else None,
        )
    return session


def validate_mp4(path: Path) -> bool:
    """Check container boundaries, not just a MIME type or a file extension."""
    size = path.stat().st_size
    if size < 32:
        return False
    boxes = set()
    with path.open("rb") as source:
        position = 0
        count = 0
        while position < size:
            count += 1
            if count > 100000:
                return False
            source.seek(position)
            header = source.read(8)
            if len(header) != 8:
                return False
            length, kind = struct.unpack(">I4s", header)
            header_size = 8
            if length == 1:
                extended = source.read(8)
                if len(extended) != 8:
                    return False
                length = struct.unpack(">Q", extended)[0]
                header_size = 16
            elif length == 0:
                length = size - position
            if length < header_size or position + length > size:
                return False
            if kind == b"mdat" and length == header_size:
                return False
            boxes.add(kind)
            position += length
    return {b"ftyp", b"moov", b"mdat"}.issubset(boxes)


def download_video(
    video: ResolvedVideo, output_dir: Path, job_id: str,
    emit: Callable[[dict], None], cancel: Event,
) -> Path:
    def check() -> None:
        if cancel.is_set():
            raise Cancelled()

    check()
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"{video.video_id}.mp4"
    if filename.exists():
        if filename.is_file() and validate_mp4(filename):
            emit({"message": "该视频已存在，已复用本地文件。", "downloaded": filename.stat().st_size})
            return filename
        raise RuntimeError("同名文件不完整或格式异常，请先将其移走，再重新下载。")
    part = output_dir / f".{video.video_id}.{job_id}.mp4.part"
    expired = False
    failure = "没有可用的视频地址，请稍后重试。"
    with media_session(video) as session:
        try:
            for url in video.urls:
                if urlsplit(url).scheme not in {"http", "https"}:
                    continue
                for attempt in range(2):
                    check()
                    try:
                        with session.get(url, stream=True, timeout=(10, 15)) as response:
                            check()
                            if response.status_code in {401, 403, 410}:
                                expired = True
                                failure = "视频地址已失效，正在尝试其他地址。"
                                break
                            response.raise_for_status()
                            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                            if content_type and not (content_type.startswith("video/") or content_type == "application/octet-stream"):
                                failure = "视频地址返回了网页或错误信息，未保存为视频。"
                                break
                            raw_total = response.headers.get("Content-Length", "")
                            total = int(raw_total) if raw_total.isdigit() else None
                            if response.headers.get("Content-Encoding", "identity") != "identity":
                                total = None
                            downloaded = 0
                            start = time.monotonic()
                            last_update = start
                            emit({"status": "downloading", "downloaded": 0, "total": total, "speed": 0, "message": ""})
                            with part.open("wb") as target:
                                for chunk in response.iter_content(64 * 1024):
                                    check()
                                    if not chunk:
                                        continue
                                    target.write(chunk)
                                    downloaded += len(chunk)
                                    now = time.monotonic()
                                    if now - last_update >= 0.15:
                                        emit({
                                            "downloaded": downloaded, "total": total,
                                            "speed": downloaded / max(now - start, 0.001),
                                        })
                                        last_update = now
                            check()
                            if total is not None and downloaded != total:
                                failure = "文件传输不完整，请重试。"
                                continue
                            emit({"status": "finalizing", "downloaded": downloaded, "total": downloaded, "speed": 0})
                            if not validate_mp4(part):
                                failure = "下载内容不是完整的 MP4 视频，未生成最终文件。"
                                break
                            check()
                            # Windows rename fails if a file appeared during this download.
                            os.rename(part, filename)
                            return filename
                    except requests.RequestException as exc:
                        if cancel.is_set():
                            raise Cancelled() from exc
                        failure = "网络请求失败，请检查网络后重新下载。"
                        if attempt == 0 and not cancel.wait(0.5):
                            continue
            check()
            if expired:
                raise MediaExpired("视频地址失效，需要重新解析。")
            raise RuntimeError(failure)
        finally:
            part.unlink(missing_ok=True)
