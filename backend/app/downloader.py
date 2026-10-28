from __future__ import annotations

import http.cookiejar
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import yt_dlp
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from yt_dlp.utils import DownloadError

from .config import Settings


ProgressCallback = Callable[[str, int], None]


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    title: str
    author: str | None
    thumbnail_url: str | None
    duration: float | None
    resolution: str | None
    extension: str


class InvalidLinkError(ValueError):
    pass


class BrowserSessionError(RuntimeError):
    pass


def _extract_url(text: str) -> str:
    from douyin_downloader import extract_douyin_url

    try:
        return extract_douyin_url(text)
    except ValueError as exc:
        raise InvalidLinkError(str(exc)) from exc


def _cookie_from_playwright(cookie: dict[str, Any]) -> http.cookiejar.Cookie:
    expires = cookie.get("expires")
    expires = int(expires) if expires and expires > 0 else None
    return http.cookiejar.Cookie(
        version=0,
        name=cookie["name"],
        value=cookie["value"],
        port=None,
        port_specified=False,
        domain=cookie["domain"],
        domain_specified=True,
        domain_initial_dot=cookie["domain"].startswith("."),
        path=cookie.get("path") or "/",
        path_specified=True,
        secure=bool(cookie.get("secure")),
        expires=expires,
        discard=expires is None,
        comment=None,
        comment_url=None,
        rest={"HttpOnly": None} if cookie.get("httpOnly") else {},
        rfc2109=False,
    )


class PlaywrightCookieProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    @contextmanager
    def acquire(self, url: str) -> Iterator[Path]:
        self.settings.browser_profile_dir.mkdir(parents=True, exist_ok=True)
        launch_options: dict[str, Any] = {
            "user_data_dir": str(self.settings.browser_profile_dir),
            "headless": self.settings.browser_headless,
            "locale": "zh-CN",
        }
        if self.settings.browser_channel:
            launch_options["channel"] = self.settings.browser_channel

        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(**launch_options)
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(
                        "https://www.douyin.com/",
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )
                    page.wait_for_timeout(4_000)
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    page.wait_for_timeout(5_000)
                    cookies = context.cookies(["https://www.douyin.com/"])
                finally:
                    context.close()
        except PlaywrightError as exc:
            raise BrowserSessionError(f"浏览器会话失败：{exc}") from exc

        if not cookies:
            raise BrowserSessionError("浏览器没有生成抖音验证 cookies")

        jar = http.cookiejar.MozillaCookieJar()
        for cookie in cookies:
            jar.set_cookie(_cookie_from_playwright(cookie))
        handle, name = tempfile.mkstemp(prefix="douyin-server-", suffix=".cookies.txt")
        os.close(handle)
        path = Path(name)
        jar.filename = str(path)
        jar.save(ignore_discard=True, ignore_expires=True)
        try:
            yield path
        finally:
            path.unlink(missing_ok=True)


class VideoDownloader:
    def __init__(self, settings: Settings):
        self.cookie_provider = PlaywrightCookieProvider(settings)

    def download(
        self,
        share_text: str,
        quality: str,
        output_dir: Path,
        progress: ProgressCallback,
    ) -> DownloadResult:
        url = _extract_url(share_text)
        output_dir.mkdir(parents=True, exist_ok=True)
        progress("resolving", 5)
        try:
            return self._download_once(url, quality, output_dir, progress, None)
        except DownloadError as exc:
            message = str(exc).lower()
            if "fresh cookies" not in message and "cookies" not in message:
                raise

        progress("acquiring_session", 12)
        with self.cookie_provider.acquire(url) as cookie_file:
            return self._download_once(url, quality, output_dir, progress, cookie_file)

    def _download_once(
        self,
        url: str,
        quality: str,
        output_dir: Path,
        progress: ProgressCallback,
        cookie_file: Path | None,
    ) -> DownloadResult:
        format_selector = {
            "best": "bv*+ba/b",
            "1080p": "bv*[height<=1080]+ba/b[height<=1080]",
            "720p": "bv*[height<=720]+ba/b[height<=720]",
        }[quality]

        def hook(data: dict[str, Any]) -> None:
            if data.get("status") != "downloading":
                return
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            percent = int(downloaded * 100 / total) if total else 0
            progress("downloading", max(15, min(95, percent)))

        options: dict[str, Any] = {
            "outtmpl": str(output_dir / "%(title)s [%(id)s].%(ext)s"),
            "format": format_selector,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "windowsfilenames": os.name == "nt",
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 25,
            "progress_hooks": [hook],
            "http_headers": {
                "Referer": "https://www.douyin.com/",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        }
        if cookie_file:
            options["cookiefile"] = str(cookie_file)
        try:
            import yt_dlp.networking._curlcffi  # noqa: F401
            from yt_dlp.networking.impersonate import ImpersonateTarget
        except ImportError:
            pass
        else:
            options["impersonate"] = ImpersonateTarget(client="chrome")

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise DownloadError("没有返回视频信息")
            requested = info.get("requested_downloads") or []
            path = Path(
                requested[0].get("filepath")
                if requested and requested[0].get("filepath")
                else ydl.prepare_filename(info)
            )
            if not path.exists() and path.suffix != ".mp4":
                merged = path.with_suffix(".mp4")
                if merged.exists():
                    path = merged

        height = info.get("height")
        width = info.get("width")
        resolution = f"{width}×{height}" if width and height else None
        return DownloadResult(
            path=path,
            title=info.get("title") or "未命名视频",
            author=info.get("uploader") or None,
            thumbnail_url=info.get("thumbnail") or None,
            duration=info.get("duration"),
            resolution=resolution,
            extension=path.suffix.lstrip(".") or "mp4",
        )
