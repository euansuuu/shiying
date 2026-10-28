from __future__ import annotations

import json
import tempfile
import threading
import time
import traceback
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QFontDatabase, QImage, QImageReader
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QPushButton

from .models import Job, ResolvedAlbum, ResolvedImage, work_id_from_url
from .appearance import theme_colors
from .storage import Preferences, Store
from .window import BRAND_MARK_SIZE, JobCard, MainWindow


def _check_albums(app, data_dir: Path, output: Path, checks: list[str]) -> None:
    codecs = {bytes(kind).decode().lower() for kind in QImageReader.supportedImageFormats()}
    assert {"jpeg", "png", "webp"} <= codecs, "缺少图片解码插件"
    bodies = {}
    for kind, color in (("JPEG", "#278dfa"), ("PNG", "#27b8c8"), ("WEBP", "#7560d6")):
        image = QImage(192, 256, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        assert image.save(buffer, kind)
        bodies[kind] = bytes(buffer.data())
    routes = {"/one": (bodies["JPEG"], "image/jpeg"), "/two": (b"<html>error</html>", "text/html"),
              "/three": (bodies["WEBP"], "image/webp"), "/slow": (bodies["PNG"], "image/png")}
    requested = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requested.append(self.path)
            if self.path == "/slow":
                time.sleep(0.4)
            body, kind = routes[self.path]
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    base = f"http://127.0.0.1:{server.server_port}"
    def resolve(url, *args):
        identifier = work_id_from_url(url)
        paths = ("/one", "/two", "/three") if identifier == "123456" else ("/one", "/slow", "/three")
        return ResolvedAlbum(identifier, "把沿途的风景，存进生活里", "拾影示例 · 本地测试", [
            ResolvedImage(index, f"image-{index}", [base + path]) for index, path in enumerate(paths, 1)
        ], url, "smoke-agent", [], "把沿途的风景，存进生活里 #图文")
    def wait_until(condition):
        deadline = time.monotonic() + 12
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert condition(), "后台图片任务超时"
    window = MainWindow(data_dir, preview=True)
    try:
        window.show()
        window.preview = False
        window.preferences.output_dir = str(data_dir / "中文图文下载")
        window._update_paths()
        with patch("desktop.worker.resolve_work", side_effect=resolve):
            window.share_input.setPlainText("https://www.douyin.com/note/123456")
            QTest.mouseClick(window.add_btn, Qt.MouseButton.LeftButton)
            job = window.jobs[0]
            wait_until(lambda: window.thread is None)
            assert job.status == "partial" and (job.image_done, job.image_failed, job.image_total) == (2, 1, 3)
            assert job.id in window.history_cards
            card = window.cards[job.id]
            assert card.progress.value() == 2 and card.progress.maximum() == 3
            assert not card.thumbnail.isNull()
            def actions():
                return {item.property("jobAction"): item for item in window.cards[job.id].findChildren(QPushButton)}
            assert set(actions()) == {"retry", "folder", "errors"}
            for mode in ("light", "dark"):
                QTest.mouseClick(window.theme_buttons[mode], Qt.MouseButton.LeftButton)
                app.processEvents()
                assert window.grab().save(str(output / f"windows-album-partial-{mode}.png"))
            def inspect_errors(dialog):
                text = dialog.findChild(QPlainTextEdit).toPlainText()
                assert "第 2 张" in text and "http" not in text
                return QDialog.DialogCode.Accepted
            with patch("desktop.window.QDialog.exec", inspect_errors):
                QTest.mouseClick(actions()["errors"], Qt.MouseButton.LeftButton)
            checks.append("图文在后台线程下载、JPEG/PNG/WebP 插件、首图缓存、部分完成与失败原因")
            requested.clear()
            routes["/two"] = (bodies["PNG"], "image/png")
            QTest.mouseClick(actions()["retry"], Qt.MouseButton.LeftButton)
            wait_until(lambda: window.thread is None)
            assert job.status == "completed" and job.image_done == 3 and job.image_failed == 0
            assert requested == ["/two"], "重试重复下载了成功图片"
            root = Path(job.result_dir)
            assert (root / "001.jpg").read_bytes() == bodies["JPEG"]
            assert (root / "002.png").read_bytes() == bodies["PNG"]
            assert (root / "003.webp").read_bytes() == bodies["WEBP"]
            assert Path(job.caption_path).read_text(encoding="utf-8").endswith("#图文")
            assert set(actions()) == {"folder", "caption"}
            with patch("desktop.window.QDesktopServices.openUrl", return_value=True) as opened:
                QTest.mouseClick(actions()["folder"], Qt.MouseButton.LeftButton)
                QTest.mouseClick(actions()["caption"], Qt.MouseButton.LeftButton)
                assert [Path(args[0][0].toLocalFile()) for args in opened.call_args_list] == [Path(job.result_dir), Path(job.caption_path)]
            for mode in ("light", "dark"):
                QTest.mouseClick(window.theme_buttons[mode], Qt.MouseButton.LeftButton)
                app.processEvents()
                assert window.grab().save(str(output / f"windows-album-complete-{mode}.png"))
            checks.append("图文仅重试失败图片、保留原始格式与顺序、文案及目录按钮")
            window.share_input.setPlainText("https://www.douyin.com/note/223456")
            QTest.mouseClick(window.add_btn, Qt.MouseButton.LeftButton)
            cancelled = window.jobs[0]
            wait_until(lambda: cancelled.image_done == 1)
            window.job_action(cancelled.id, "cancel")
            wait_until(lambda: window.thread is None)
            assert cancelled.status == "cancelled" and cancelled.image_done == 1
            assert (Path(cancelled.result_dir) / "001.jpg").is_file()
            assert not list(Path(cancelled.result_dir).glob("*.part"))
            requested.clear()
            window.job_action(cancelled.id, "retry")
            wait_until(lambda: window.thread is None)
            assert cancelled.status == "completed" and cancelled.image_done == 3
            assert "/one" not in requested
            window.resize(960, 700)
            app.processEvents()
            assert window.grab().save(str(output / "windows-album-minimum.png"))
            checks.append("图文取消保留已保存图片、继续下载、最小窗口布局")
        completed_id = job.id
        window.preview = True
        window.close()
        app.processEvents()
        window = MainWindow(data_dir, preview=True)
        restored = next(item for item in window.jobs if item.id == completed_id)
        assert restored.image_done == 3 and restored.status == "completed" and restored.id in window.history_cards
        assert not window.cards[restored.id].thumbnail.isNull()
        checks.append("重新打开后恢复图文数量、缩略图和下载记录")
    finally:
        if window.thread:
            window.worker.cancel.set()
            wait_until(lambda: window.thread is None)
        window.close()
        server.shutdown()
        server.server_close()
        serving.join(2)


def run(app, output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    try:
        with tempfile.TemporaryDirectory(prefix="shiying-smoke-") as temporary, ExitStack() as cleanup:
            assert QFontDatabase.families(), "未载入用于界面渲染的字体"
            data_dir = Path(temporary)
            store = Store(data_dir)
            examples = [
                Job("https://v.douyin.com/dmp19uECBJE/", str(data_dir), title="当你也是股东，经济增长就有你的一份",
                    author="Ethan.", status="downloading", downloaded=24800000, total=40000000, speed=3200000),
                Job("https://www.douyin.com/video/1234567890123456789", str(data_dir),
                    title="去海边，等一场刚刚好的日落", author="山海之间", status="completed",
                    downloaded=21600000, total=21600000, file_path=str(data_dir / "示例视频.mp4")),
                Job("https://v.douyin.com/example/", str(data_dir), status="verification", remaining=156,
                    message="请在浏览器中手动完成登录或验证，然后返回继续解析。"),
            ]
            for job in reversed(examples):
                store.save(job)
            store.close()
            window = MainWindow(data_dir, preview=True)
            cleanup.callback(lambda: window.close())
            window.preferences.output_dir = r"D:\视频\抖音"
            window._update_paths()
            window.show()
            QTest.mouseClick(window.theme_buttons["light"], Qt.MouseButton.LeftButton)
            app.processEvents()
            assert window.grab().save(str(output / "windows-main.png"))
            assert window.grab().save(str(output / "windows-light.png"))
            checks.append("主界面与示例状态渲染")
            assert window.brand_mark.width() == BRAND_MARK_SIZE == round(48 * 0.8)
            assert window.brand_mark.height() == BRAND_MARK_SIZE
            verification = window.cards[examples[2].id]
            actions = {control.property("jobAction"): control for control in verification.findChildren(QPushButton)}
            assert set(actions) == {"resume", "show", "defer", "cancel"}
            requested = []
            verification.requested.disconnect(window.job_action)
            verification.requested.connect(lambda job_id, action: requested.append((job_id, action)))
            for action in ("resume", "show", "defer", "cancel"):
                QTest.mouseClick(actions[action], Qt.MouseButton.LeftButton)
            assert requested == [(examples[2].id, action) for action in ("resume", "show", "defer", "cancel")]
            verification.requested.connect(window.job_action)
            checks.append("80% 品牌图标，四个验证操作独立触发")

            original_ids = [job.id for job in window.jobs]
            window.share_input.setPlainText("切换主题后保留的文字")
            QTest.mouseClick(window.theme_buttons["dark"], Qt.MouseButton.LeftButton)
            app.processEvents()
            assert window.colors == theme_colors("dark")
            assert Preferences(data_dir).theme == "dark"
            assert window.grab().save(str(output / "windows-dark.png"))
            assert window.share_input.toPlainText() == "切换主题后保留的文字"
            assert [job.id for job in window.jobs] == original_ids
            assert window.cards[examples[0].id].progress.value() == 62
            checks.append("浅色/暗色即时切换，保留任务、进度和输入")

            QTest.mouseClick(window.theme_buttons["system"], Qt.MouseButton.LeftButton)
            hints = app.styleHints()
            system = {"scheme": Qt.ColorScheme.Dark}
            fake_app = SimpleNamespace(styleHints=lambda: SimpleNamespace(colorScheme=lambda: system["scheme"]))
            with patch("desktop.appearance.QApplication", fake_app):
                hints.colorSchemeChanged.emit(Qt.ColorScheme.Dark)
                app.processEvents()
                assert window.colors == theme_colors("dark")
                system["scheme"] = Qt.ColorScheme.Light
                hints.colorSchemeChanged.emit(Qt.ColorScheme.Light)
                app.processEvents()
                assert window.colors == theme_colors("light")
                QTest.mouseClick(window.theme_buttons["dark"], Qt.MouseButton.LeftButton)
                hints.colorSchemeChanged.emit(Qt.ColorScheme.Light)
                app.processEvents()
                assert window.colors == theme_colors("dark")
            checks.append("跟随系统响应主题通知，固定模式保持选择")
            QTest.mouseClick(window.theme_buttons["light"], Qt.MouseButton.LeftButton)
            window.share_input.clear()
            app.processEvents()
            QTest.mouseClick(window.add_btn, Qt.MouseButton.LeftButton)
            assert window.input_error.isVisible()
            checks.append("空链接校验")
            window.share_input.setPlainText("复制打开抖音 https://v.douyin.com/TestShare123/")
            QTest.mouseClick(window.add_btn, Qt.MouseButton.LeftButton)
            assert len(window.jobs) == 4 and window.jobs[0].status == "queued"
            new_job = window.jobs[0]
            cancel = next(control for control in window.cards[new_job.id].findChildren(QPushButton) if control.text() == "取消")
            QTest.mouseClick(cancel, Qt.MouseButton.LeftButton)
            assert new_job.status == "cancelled"
            app.processEvents()
            retry = next(control for control in window.cards[new_job.id].findChildren(QPushButton) if control.text() == "重新下载")
            QTest.mouseClick(retry, Qt.MouseButton.LeftButton)
            assert new_job.status == "queued"
            app.processEvents()
            visible_cards = [card for card in window.job_scroll.widget().findChildren(JobCard) if not card.isHidden()]
            assert len(visible_cards) == len(window.jobs), "刷新列表后仍有旧任务卡片可见"
            checks.append("列表刷新立即隐藏旧卡片，取消/重试不残留控件")
            checks.append("添加任务、取消与重新下载")

            QTest.mouseClick(window.nav_buttons["history"], Qt.MouseButton.LeftButton)
            assert window.stack.currentIndex() == 1 and len(window.history_cards) == 1
            QTest.mouseClick(window.nav_buttons["settings"], Qt.MouseButton.LeftButton)
            chosen = str(data_dir / "中文保存目录")
            with patch("desktop.window.QFileDialog.getExistingDirectory", return_value=chosen):
                window.choose_directory()
            assert window.preferences.output_dir == chosen
            window.browser_combo.showPopup()
            app.processEvents()
            assert window.browser_combo.view().isVisible()
            assert window.browser_combo.view().window().grab().save(str(output / "windows-browser-menu.png"))
            QTest.keyClick(window.browser_combo, Qt.Key.Key_Down)
            QTest.keyClick(window.browser_combo, Qt.Key.Key_Return)
            app.processEvents()
            assert window.browser_combo.currentData() == "chrome"
            assert Preferences(data_dir).channel == "chrome"
            QTest.mouseClick(window.remember_check, Qt.MouseButton.LeftButton)
            assert not window.preferences.remember
            QTest.keyClick(window.remember_check, Qt.Key.Key_Space)
            assert window.preferences.remember
            app.processEvents()
            assert window.grab().save(str(output / "windows-settings.png"))
            QTest.mouseClick(window.theme_buttons["dark"], Qt.MouseButton.LeftButton)
            app.processEvents()
            assert window.grab().save(str(output / "windows-settings-dark.png"))
            checks.append("记录、中文目录、浏览器菜单键盘选择、勾选会话状态")
            window.set_view("downloads")
            window.resize(960, 700)
            app.processEvents()
            assert window.grab().save(str(output / "windows-minimum.png"))
            assert window.share_input.width() > 300
            window.set_view("settings")
            app.processEvents()
            assert window.grab().save(str(output / "windows-settings-minimum.png"))
            selector = window.theme_buttons["system"].parentWidget()
            assert selector.width() <= window.stack.currentWidget().viewport().width()
            checks.append("最小窗口布局")
            window.close()
            app.processEvents()
            window = MainWindow(data_dir, preview=True)
            assert window.preferences.theme == "dark"
            assert window.theme_buttons["dark"].isChecked()
            assert window.colors == theme_colors("dark")
            assert window.preferences.channel == "chrome"
            window.close()
            app.processEvents()
            checks.append("重新打开后恢复主题选择")
            _check_albums(app, data_dir / "album-check", output, checks)
            from playwright.sync_api import Error as BrowserError, sync_playwright
            with sync_playwright() as playwright:
                browser = None
                for channel in ("msedge", "chrome"):
                    try:
                        browser = playwright.chromium.launch(channel=channel, headless=True)
                        break
                    except BrowserError:
                        continue
                assert browser is not None, "请安装 Edge 或 Chrome 后再检查浏览器驱动"
                try:
                    page = browser.new_page()
                    page.set_content("<title>Shiying driver check</title><p>Local only</p>")
                    assert page.title() == "Shiying driver check"
                finally:
                    browser.close()
            checks.append("Playwright 驱动与本机浏览器启动")
        report = {"ok": True, "checks": checks, "note": "隔离数据的离屏界面和本地 HTTP 下载检查；不访问抖音。"}
        (output / "smoke-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except Exception:
        (output / "smoke-result.json").write_text(
            json.dumps({"ok": False, "checks": checks, "error": traceback.format_exc()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 1
