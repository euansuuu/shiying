from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4


ACTIVE_STATES = {"queued", "resolving", "verification", "downloading", "finalizing"}
STATUS_LABELS = {
    "queued": "等待中", "resolving": "解析中", "verification": "等待浏览器验证",
    "downloading": "下载中", "finalizing": "校验保存中", "completed": "已完成",
    "failed": "下载失败", "cancelled": "已取消", "interrupted": "已中断",
    "deferred": "等待手动处理",
    "partial": "部分完成",
}


def extract_url(text: str) -> str:
    urls = re.findall(r"https?://[^\s<>\"“”]+", text, re.IGNORECASE)
    for raw in urls:
        url = raw.rstrip(".,，。;；!！?？)）]】'\"")
        try:
            parsed = urlsplit(url)
            if parsed.username or parsed.password or parsed.port not in (None, 80, 443):
                continue
            if parsed.hostname == "v.douyin.com" and re.fullmatch(r"/[A-Za-z0-9_-]+/?", parsed.path):
                return url
            if parsed.hostname in {"douyin.com", "www.douyin.com"}:
                if re.fullmatch(r"/(?:video|note)/\d+/?", parsed.path):
                    return url
        except ValueError:
            continue
    raise ValueError("未找到有效的抖音作品链接，请粘贴短链、视频页或图文页链接。")


def work_id_from_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.hostname not in {"douyin.com", "www.douyin.com"}:
        return ""
    match = re.fullmatch(r"/(?:video|note)/(\d+)/?", parsed.path)
    return match.group(1) if match else ""


@dataclass
class Job:
    url: str
    output_dir: str
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    status: str = "queued"
    title: str = "待解析的抖音作品"
    author: str = ""
    work_id: str = ""
    content_kind: str = "unknown"
    file_path: str = ""
    result_dir: str = ""
    caption_path: str = ""
    thumbnail_path: str = ""
    image_total: int = 0
    image_done: int = 0
    image_failed: int = 0
    current_image: int = 0
    image_bytes: int = 0
    image_size: int | None = None
    image_errors: list[str] = field(default_factory=list)
    notice: str = ""
    downloaded: int = 0
    total: int | None = None
    speed: float = 0
    message: str = ""
    remaining: int = 0

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def destination(self) -> Path:
        return Path(self.output_dir).expanduser().resolve()


JOB_EVENT_FIELDS = set(Job.__dataclass_fields__) - {"url", "output_dir", "id", "created_at"}


@dataclass
class SessionConfig:
    data_dir: Path
    channel: str = "msedge"
    remember: bool = True
    cookies: list[dict] = field(default_factory=list)
    headless: bool = False
    resolve_timeout: float = 20
    verification_timeout: float = 180


@dataclass
class ResolvedVideo:
    video_id: str
    title: str
    author: str
    urls: list[str]
    referer: str
    user_agent: str
    cookies: list[dict]


@dataclass
class ResolvedImage:
    index: int
    key: str
    urls: list[str]


@dataclass
class ResolvedAlbum:
    work_id: str
    title: str
    author: str
    images: list[ResolvedImage]
    referer: str
    user_agent: str
    cookies: list[dict]
    caption: str = ""
    notice: str = ""


class ImagesUnavailable(RuntimeError):
    pass


class Cancelled(Exception):
    pass


class Deferred(Exception):
    pass


class MediaExpired(RuntimeError):
    pass
