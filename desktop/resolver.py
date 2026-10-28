from __future__ import annotations

import json
import tempfile
import time
from contextlib import nullcontext
from pathlib import Path
from threading import Event
from typing import Callable
from urllib.parse import unquote, urlsplit

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import TimeoutError as BrowserTimeout
from playwright.sync_api import sync_playwright

from .models import (
    Cancelled, Deferred, ImagesUnavailable, ResolvedAlbum, ResolvedImage,
    ResolvedVideo, SessionConfig, work_id_from_url,
)


def detail_from_payload(payload: object, expected_id: str) -> dict | None:
    if not expected_id:
        return None
    stack = [payload]
    visited = 0
    while stack and visited < 15000:
        node = stack.pop()
        visited += 1
        if isinstance(node, dict):
            identifier = str(node.get("aweme_id") or node.get("awemeId") or "")
            if identifier == expected_id and ("video" in node or "images" in node):
                return node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def video_from_detail(detail: dict, referer: str, user_agent: str, cookies: list[dict]) -> ResolvedVideo:
    video_id = str(detail.get("aweme_id") or detail.get("awemeId") or "")
    if not video_id.isdigit():
        raise RuntimeError("视频详情中没有有效的视频 ID。")
    video = detail.get("video")
    if not isinstance(video, dict):
        raise RuntimeError("页面没有提供可下载的单个视频数据，暂不支持直播。")
    address = video.get("play_addr") or video.get("playAddr") or {}
    if not isinstance(address, dict):
        raise RuntimeError("页面返回的视频地址格式异常，请重试。")
    urls = address.get("url_list") or address.get("urlList") or []
    if not isinstance(urls, list):
        raise RuntimeError("页面返回的视频地址格式异常，请重试。")
    urls = [url for url in urls if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"}]
    if not urls:
        raise RuntimeError("页面没有提供可直接下载的视频地址。")
    author = detail.get("author") or {}
    if not isinstance(author, dict):
        author = {}
    return ResolvedVideo(
        video_id=video_id, title=str(detail.get("desc") or "未命名视频"),
        author=str(author.get("nickname") or "未知作者"), urls=list(dict.fromkeys(urls)),
        referer=referer, user_agent=user_agent, cookies=cookies,
    )


def work_from_detail(detail: dict, referer: str, user_agent: str, cookies: list[dict]) -> ResolvedVideo | ResolvedAlbum:
    images = detail.get("images")
    is_note = "/note/" in urlsplit(referer).path or detail.get("aweme_type") == 68
    if not images and not is_note:
        return video_from_detail(detail, referer, user_agent, cookies)
    if not isinstance(images, list) or not images:
        raise ImagesUnavailable("已识别图文，尚未取得可下载图片，请检查浏览器。")
    if len(images) > 1000:
        raise RuntimeError("图片数量超过当前支持范围。")
    identifier = str(detail.get("aweme_id") or detail.get("awemeId") or "")
    if not identifier.isdigit():
        raise RuntimeError("作品详情中没有有效的作品 ID。")
    assets = []
    live = False
    for index, raw in enumerate(images, 1):
        image = raw if isinstance(raw, dict) else {}
        urls = image.get("url_list") or image.get("urlList") or []
        if not isinstance(urls, list):
            urls = []
        urls = [url for url in urls if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"} and urlsplit(url).hostname]
        key = image.get("uri") or image.get("image_id") or image.get("imageId") or ""
        assets.append(ResolvedImage(index, str(key), list(dict.fromkeys(urls))))
        live = live or bool(image.get("video"))
    if not any(asset.urls for asset in assets):
        raise ImagesUnavailable("已识别图文，尚未取得可下载图片，请检查浏览器。")
    author = detail.get("author") or {}
    caption = str(detail.get("desc") or "")
    notice = "本次仅保存静态图片，未保存实况视频。" if live else ""
    if detail.get("music"):
        notice += (" " if notice else "") + "图文配乐未单独保存。"
    return ResolvedAlbum(identifier, caption or "未命名图文", str(author.get("nickname") or "未知作者") if isinstance(author, dict) else "未知作者",
                         assets, referer, user_agent, cookies, caption, notice)


def resolve_work(
    url: str, config: SessionConfig, emit: Callable[[dict], None],
    cancel: Event, resume: Event, defer: Event, show_browser: Event,
) -> ResolvedVideo | ResolvedAlbum:
    def check() -> None:
        if cancel.is_set():
            raise Cancelled()
        if defer.is_set():
            raise Deferred()

    check()
    emit({"status": "resolving", "message": "正在打开独立浏览器，识别作品类型…"})
    profile = config.data_dir / "browser-profile" / config.channel
    temporary = nullcontext(str(profile)) if config.remember else tempfile.TemporaryDirectory(prefix="shiying-")
    with temporary as profile_name:
        Path(profile_name).mkdir(parents=True, exist_ok=True)
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(profile_name), channel=config.channel, headless=config.headless,
                    locale="zh-CN", viewport={"width": 1120, "height": 760},
                )
                try:
                    context.set_default_timeout(5000)
                    if config.cookies:
                        context.add_cookies(config.cookies)
                    page = context.pages[0] if context.pages else context.new_page()
                    payloads: list[dict] = []

                    def on_response(response) -> None:
                        parsed = urlsplit(response.url)
                        if parsed.hostname not in {"www.douyin.com", "douyin.com"}:
                            return
                        if parsed.path.rstrip("/") not in {
                            "/aweme/v1/web/aweme/detail", "/aweme/v1/web/aweme/post",
                        } or response.status != 200:
                            return
                        try:
                            data = response.json()
                            if isinstance(data, dict):
                                payloads.append(data)
                                del payloads[:-12]
                        except (BrowserError, ValueError):
                            pass

                    page.on("response", on_response)
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    except BrowserTimeout:
                        pass
                    check()
                    deadline = time.monotonic() + config.resolve_timeout
                    verification_deadline = None
                    last_dom_check = 0.0
                    expected_id = work_id_from_url(url)
                    while True:
                        check()
                        if page.is_closed():
                            raise RuntimeError("浏览器窗口已关闭，请重新下载。")
                        if show_browser.is_set():
                            show_browser.clear()
                            page.bring_to_front()
                        expected_id = expected_id or work_id_from_url(page.url)
                        detail = next(
                            (found for payload in reversed(payloads)
                             if (found := detail_from_payload(payload, expected_id))),
                            None,
                        )
                        now = time.monotonic()
                        if not detail and expected_id and now - last_dom_check > 2:
                            last_dom_check = now
                            for selector in ("#__UNIVERSAL_DATA_FOR_REHYDRATION__", "#RENDER_DATA"):
                                script = page.locator(selector)
                                if not script.count():
                                    continue
                                try:
                                    text = script.first.text_content(timeout=1000) or ""
                                    data = json.loads(unquote(text) if selector == "#RENDER_DATA" else text)
                                    detail = detail_from_payload(data, expected_id)
                                except (BrowserError, ValueError):
                                    continue
                                if detail:
                                    break
                        if detail:
                            check()
                            try:
                                return work_from_detail(detail, page.url, page.evaluate("navigator.userAgent"), context.cookies())
                            except ImagesUnavailable:
                                pass
                        if resume.is_set():
                            resume.clear()
                            emit({"status": "resolving", "message": "正在重新检查作品页面…"})
                            try:
                                page.reload(wait_until="domcontentloaded", timeout=15000)
                            except BrowserTimeout:
                                pass
                            deadline = time.monotonic() + config.resolve_timeout
                        if verification_deadline is None and now >= deadline:
                            verification_deadline = now + config.verification_timeout
                            emit({
                                "status": "verification",
                                "message": "尚未取得可下载的作品信息。请检查浏览器，若要求登录或验证，请手动完成后点击“继续解析”。",
                                "remaining": int(config.verification_timeout),
                            })
                        if verification_deadline is not None:
                            remaining = max(0, int(verification_deadline - now))
                            if remaining == 0:
                                raise RuntimeError("等待浏览器处理超时，请确认作品可访问后重新下载。")
                            if now >= deadline:
                                emit({"remaining": remaining})
                                deadline = now + 1
                        page.wait_for_timeout(250)
                finally:
                    context.close()
        except BrowserError as exc:
            check()
            message = str(exc).lower()
            if "executable" in message or "distribution" in message:
                raise RuntimeError("未找到所选浏览器，请在设置中切换到已安装的 Edge 或 Chrome。") from exc
            raise RuntimeError("浏览器会话中断，可能是窗口被关闭或浏览器启动受限，请重试。") from exc
