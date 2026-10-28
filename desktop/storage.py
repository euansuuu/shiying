from __future__ import annotations

import ctypes
import http.cookiejar
import json
import os
import sqlite3
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

from .models import ACTIVE_STATES, Job


def app_data_dir() -> Path:
    path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    path.mkdir(parents=True, exist_ok=True)
    return path


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(directory / "jobs.sqlite3")
        self.connection.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        self.connection.commit()

    def save(self, job: Job) -> None:
        self.connection.execute(
            "INSERT INTO jobs(id, data) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (job.id, json.dumps(job.as_dict(), ensure_ascii=False)),
        )
        self.connection.commit()

    def load(self) -> list[Job]:
        rows = self.connection.execute("SELECT data FROM jobs ORDER BY rowid DESC").fetchall()
        jobs = []
        for row in rows:
            data = json.loads(row[0])
            legacy_id = data.pop("video_id", "")
            data.setdefault("work_id", legacy_id)
            data.setdefault("content_kind", "video" if data.get("file_path") else "unknown")
            if data.get("title") == "待解析的抖音视频":
                data["title"] = "待解析的抖音作品"
            jobs.append(Job(**data))
        return jobs

    def recover(self) -> list[Job]:
        jobs = self.load()
        for job in jobs:
            if job.status in ACTIVE_STATES:
                job.status = "interrupted"
                job.speed = 0
                job.message = "上次运行未完成，可点击重新下载。"
                self.save(job)
        return jobs

    def close(self) -> None:
        self.connection.close()


class Preferences:
    def __init__(self, directory: Path):
        self.settings = QSettings(str(directory / "settings.ini"), QSettings.Format.IniFormat)
        default = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)) / "拾影"
        self.output_dir = str(self.settings.value("output_dir", str(default)))
        self.channel = str(self.settings.value("channel", "msedge"))
        if self.channel not in {"msedge", "chrome"}:
            self.channel = "msedge"
        self.remember = self.settings.value("remember", True, type=bool)
        self.theme = str(self.settings.value("theme", "system"))
        if self.theme not in {"light", "dark", "system"}:
            self.theme = "system"

    def save(self) -> None:
        self.settings.setValue("output_dir", self.output_dir)
        self.settings.setValue("channel", self.channel)
        self.settings.setValue("remember", self.remember)
        self.settings.setValue("theme", self.theme)
        self.settings.sync()


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Cookie 安全存储目前仅支持 Windows。")
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = _Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob),
    ]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise RuntimeError("无法访问 Windows 加密 Cookie，请重新导入文件。")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


class CookieVault:
    def __init__(self, directory: Path):
        self.path = directory / "cookies.dpapi"

    def load(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            value = json.loads(_dpapi(self.path.read_bytes(), decrypt=True))
        except (OSError, ValueError, RuntimeError) as exc:
            raise RuntimeError("保存的 Cookie 无法读取，请重新导入。") from exc
        if not isinstance(value, list):
            raise RuntimeError("保存的 Cookie 格式无效，请重新导入。")
        return value

    def save(self, cookies: list[dict]) -> None:
        encrypted = _dpapi(json.dumps(cookies).encode("utf-8"))
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_bytes(encrypted)
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def import_cookies(path: Path) -> list[dict]:
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Cookie 文件过大，请选择 Netscape 格式的 cookies.txt。")
    jar = http.cookiejar.MozillaCookieJar(str(path))
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except (OSError, http.cookiejar.LoadError, ValueError) as exc:
        raise ValueError("无法读取，请选择 Netscape 格式的 cookies.txt。") from exc
    cookies = []
    for cookie in jar:
        domain = cookie.domain.lower()
        if domain.lstrip(".") != "douyin.com" and not domain.endswith(".douyin.com"):
            continue
        if not cookie.name or not isinstance(cookie.value, str):
            continue
        if cookie.expires not in (None, 0) and cookie.expires <= time.time():
            continue
        item = {
            "name": cookie.name, "value": cookie.value, "domain": cookie.domain,
            "path": cookie.path or "/", "secure": bool(cookie.secure),
            "httpOnly": cookie.has_nonstandard_attr("HTTPOnly") or cookie.has_nonstandard_attr("HttpOnly"),
        }
        if cookie.expires and cookie.expires > 0:
            item["expires"] = cookie.expires
        cookies.append(item)
    if not cookies:
        raise ValueError("文件中没有未过期的抖音 Cookie。")
    return cookies
