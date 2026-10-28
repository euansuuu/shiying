from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__


def main() -> int:
    parser = argparse.ArgumentParser(description="拾影 · Windows 抖音作品下载")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--data-dir", type=Path, help="使用独立的应用数据目录")
    parser.add_argument("--smoke-test", type=Path, metavar="OUTPUT_DIR", help="使用隔离数据检查界面与本地下载，不访问抖音")
    args = parser.parse_args()
    if args.smoke_test:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from PySide6.QtCore import QLockFile
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .storage import app_data_dir
    from .window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setOrganizationName("Shiying")
    app.setApplicationName("Shiying")
    app.setApplicationDisplayName("拾影 · 抖音作品下载")
    app.setStyle("Fusion")
    if args.smoke_test and os.name == "nt":
        # The offscreen platform does not enumerate the Windows font database.
        fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "segoeuib.ttf"):
            if (fonts / name).exists():
                QFontDatabase.addApplicationFont(str(fonts / name))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    if args.smoke_test:
        from .smoke import run
        return run(app, args.smoke_test.resolve())

    directory = args.data_dir.expanduser().resolve() if args.data_dir else app_data_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(directory / "app.lock"))
        if not lock.tryLock(0):
            QMessageBox.information(None, "拾影已在运行", "请使用已打开的拾影窗口。")
            return 0
        logger = logging.getLogger("shiying")
        logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(directory / "application.log", maxBytes=256000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        window = MainWindow(directory)
    except (OSError, RuntimeError) as exc:
        QMessageBox.critical(None, "无法启动拾影", f"无法创建或访问应用数据目录。\n{type(exc).__name__}")
        return 1

    def exception_hook(kind, value, tb) -> None:
        # Record call sites without exception text, cookies or signed media URLs.
        logger.error("Unhandled %s\n%s", kind.__name__, "".join(traceback.format_list(traceback.extract_tb(tb))))
        QMessageBox.warning(window, "操作未完成", "发生意外错误，请重试。诊断信息已保存到本机日志。")

    sys.excepthook = exception_hook
    window.show()
    result = app.exec()
    lock.unlock()
    return result
