from __future__ import annotations

import argparse
import http.cookiejar
import os
import re
import tempfile
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, Iterator

import yt_dlp
from yt_dlp.utils import DownloadError, YoutubeDLError


DOUYIN_URL_RE = re.compile(
    r"https?://(?:v\.douyin\.com/[A-Za-z0-9_-]+/?|"
    r"(?:www\.)?douyin\.com/(?:video|note)/\d+)[^\s]*",
    re.IGNORECASE,
)


def extract_douyin_url(text: str) -> str:
    """Extract a supported Douyin URL from copied share text."""
    match = DOUYIN_URL_RE.search(text)
    if not match:
        raise ValueError("未找到有效的抖音链接")
    return match.group(0).rstrip(".,，。;；!！?？")


def _base_options(save_dir: Path) -> dict[str, Any]:
    options: dict[str, Any] = {
        "outtmpl": str(save_dir / "%(uploader|未知作者)s - %(title)s [%(id)s].%(ext)s"),
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "windowsfilenames": os.name == "nt",
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 20,
        "http_headers": {
            "Referer": "https://www.douyin.com/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        "quiet": False,
        "no_warnings": False,
    }

    # curl_cffi lets yt-dlp reproduce a real browser's TLS fingerprint. This
    # often makes anonymous requests less likely to be rejected by Douyin.
    try:
        # Import yt-dlp's handler, not only curl_cffi itself: yt-dlp may reject
        # a newly released curl_cffi version until compatibility is verified.
        import yt_dlp.networking._curlcffi  # noqa: F401
        from yt_dlp.networking.impersonate import ImpersonateTarget
    except ImportError:
        pass
    else:
        options["impersonate"] = ImpersonateTarget(client="chrome")

    return options


def _browser_cookie_option(
    browser: str,
    profile: str | None = None,
) -> tuple[str, str | None, None, None]:
    supported = {"chrome", "edge", "firefox", "brave", "chromium", "opera", "vivaldi"}
    normalized = browser.lower()
    if normalized not in supported:
        raise ValueError(f"不支持的浏览器 {browser!r}，可选：{', '.join(sorted(supported))}")
    return normalized, profile, None, None


def _browser_error_hint(browser: str, error: BaseException) -> str:
    message = str(error).lower()
    browser_label = browser.capitalize()
    if "could not copy" in message and "cookie database" in message:
        return (
            f"\n无法读取 {browser_label} 的 Cookie 数据库，因为浏览器仍在占用该文件。"
            f"请完全退出 {browser_label}（包括系统托盘和后台进程）后重试；"
            "也可以先用另一个未运行的浏览器打开一次抖音，再改用 "
            "--browser edge 或 --browser firefox。"
        )
    if "failed to decrypt with dpapi" in message or (
        "decrypt" in message and "cookie" in message
    ):
        return (
            f"\n{browser_label} Cookie 受 Windows DPAPI/App-Bound Encryption 保护，"
            "第三方程序无法可靠解密。请改用 --browser-session chrome，"
            "让独立浏览器会话生成抖音验证 cookies；也可以改用 Firefox。"
        )
    return ""


def _playwright_cookie(cookie: dict[str, Any]) -> http.cookiejar.Cookie:
    domain = cookie["domain"]
    expires = cookie.get("expires")
    expires = int(expires) if expires and expires > 0 else None
    rest: dict[str, Any] = {}
    if cookie.get("httpOnly"):
        rest["HttpOnly"] = None
    if cookie.get("sameSite"):
        rest["SameSite"] = cookie["sameSite"]
    return http.cookiejar.Cookie(
        version=0,
        name=cookie["name"],
        value=cookie["value"],
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path=cookie.get("path") or "/",
        path_specified=True,
        secure=bool(cookie.get("secure")),
        expires=expires,
        discard=expires is None,
        comment=None,
        comment_url=None,
        rest=rest,
        rfc2109=False,
    )


@contextmanager
def _browser_session_cookie_file(
    url: str,
    browser: str,
    project_dir: Path,
) -> Iterator[Path]:
    normalized = browser.lower()
    channels = {"chrome": "chrome", "edge": "msedge"}
    if normalized not in channels:
        raise ValueError("浏览器会话模式目前支持 chrome 或 edge")

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "缺少 Playwright，请执行 python -m pip install -r requirements.txt"
        ) from exc

    profile_dir = project_dir / ".browser-session" / normalized
    profile_dir.mkdir(parents=True, exist_ok=True)
    print(f"正在启动独立 {normalized} 会话以生成抖音验证 cookies...")

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                channel=channels[normalized],
                headless=False,
                locale="zh-CN",
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(5_000)
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(5_000)
                cookies = context.cookies(["https://www.douyin.com/"])
            finally:
                context.close()
    except PlaywrightError as exc:
        raise RuntimeError(f"浏览器会话启动失败：{exc}") from exc

    if not cookies:
        raise RuntimeError("浏览器会话未生成抖音 cookies，请检查页面是否出现验证码")

    jar = http.cookiejar.MozillaCookieJar()
    for cookie in cookies:
        jar.set_cookie(_playwright_cookie(cookie))

    handle, temp_name = tempfile.mkstemp(prefix="douyin-", suffix=".cookies.txt")
    os.close(handle)
    cookie_path = Path(temp_name)
    jar.filename = str(cookie_path)
    jar.save(ignore_discard=True, ignore_expires=True)
    try:
        print(f"已生成 {len(cookies)} 个临时 cookies，开始下载。")
        yield cookie_path
    finally:
        cookie_path.unlink(missing_ok=True)


def download_douyin(
    share_text: str,
    save_dir: str | Path = "./downloads",
    *,
    browser: str | None = None,
    browser_profile: str | None = None,
    browser_session: str | None = None,
    cookie_file: str | Path | None = None,
) -> Path:
    """Download one Douyin video.

    Anonymous mode is used unless ``browser`` or ``cookie_file`` is supplied.
    Browser mode reads the browser cookie database directly; it does not need
    an exported cookies.txt file.
    """
    url = extract_douyin_url(share_text)
    destination = Path(save_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    options = _base_options(destination)
    if browser:
        options["cookiesfrombrowser"] = _browser_cookie_option(browser, browser_profile)
    elif browser_profile:
        raise ValueError("--browser-profile 必须和 --browser 一起使用")
    elif cookie_file:
        cookie_path = Path(cookie_file).expanduser().resolve()
        if not cookie_path.is_file():
            raise FileNotFoundError(f"Cookie 文件不存在：{cookie_path}")
        options["cookiefile"] = str(cookie_path)

    if browser_session:
        mode = f"独立浏览器会话（{browser_session}）"
    elif browser:
        mode = f"浏览器登录态（{browser}）"
    elif cookie_file:
        mode = f"Cookie 文件（{cookie_file}）"
    else:
        mode = "匿名模式（无 cookies）"
    print(f"提取到链接：{url}")
    print(f"下载模式：{mode}")

    try:
        cookie_context = (
            _browser_session_cookie_file(url, browser_session, Path(__file__).resolve().parent)
            if browser_session
            else nullcontext(None)
        )
        with cookie_context as session_cookie:
            if session_cookie:
                options["cookiefile"] = str(session_cookie)
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise RuntimeError("yt-dlp 未返回视频信息")
                filename = Path(ydl.prepare_filename(info))
                requested = info.get("requested_downloads") or []
                if requested and requested[0].get("filepath"):
                    filename = Path(requested[0]["filepath"])
    except (DownloadError, YoutubeDLError) as exc:
        hint = ""
        if browser:
            hint = _browser_error_hint(browser, exc)
        elif not browser_session and not cookie_file:
            hint = (
                "\n匿名请求可能被抖音风控拦截。请先升级依赖，或使用 "
                "--browser edge/chrome 自动读取本机登录态。"
            )
        raise RuntimeError(f"下载失败：{exc}{hint}") from exc

    print("\n下载完成")
    print(f"标题：{info.get('title', '未知')}")
    print(f"作者：{info.get('uploader') or '未知'}")
    print(f"文件：{filename}")
    return filename


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="下载抖音分享链接中的单个视频")
    parser.add_argument("share_text", help="抖音分享文本或视频链接")
    parser.add_argument("-o", "--output", default="./downloads", help="保存目录")
    auth = parser.add_mutually_exclusive_group()
    auth.add_argument(
        "--browser",
        metavar="NAME",
        help="匿名下载失败时，自动读取浏览器登录态，如 edge、chrome、firefox",
    )
    auth.add_argument(
        "--browser-session",
        choices=("chrome", "edge"),
        help="启动独立浏览器会话生成验证 cookies，绕过 Chrome DPAPI 解密限制",
    )
    auth.add_argument("--cookie-file", help="兼容已有 Netscape 格式 cookies.txt")
    parser.add_argument(
        "--browser-profile",
        metavar="PROFILE",
        help="浏览器配置目录名称或路径，如 'Profile 1'；需配合 --browser",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        download_douyin(
            args.share_text,
            args.output,
            browser=args.browser,
            browser_profile=args.browser_profile,
            browser_session=args.browser_session,
            cookie_file=args.cookie_file,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"错误：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
