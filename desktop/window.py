from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QSize, QThread, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QImageReader, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from . import __version__
from .appearance import app_icon, brand_icon, icon, stylesheet, theme_colors
from .models import ACTIVE_STATES, JOB_EVENT_FIELDS, STATUS_LABELS, Job, SessionConfig, extract_url, work_id_from_url
from .storage import CookieVault, Preferences, Store, import_cookies
from .worker import DownloadWorker
from .widgets import BrowserComboBox, NavigationButton, SessionCheckBox


BRAND_MARK_SIZE = round(48 * 0.8)


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text: str, name: str = "", icon_name: str = "") -> QPushButton:
    widget = QPushButton(text)
    widget.setObjectName(name)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if name not in {"link", "directory"}:
        widget.setMinimumHeight(40)
    if icon_name:
        widget.setProperty("iconKind", icon_name)
        widget.setIcon(icon(icon_name))
    return widget


def format_bytes(value: int | float) -> str:
    if value >= 1024 ** 3:
        return f"{value / 1024 ** 3:.2f} GB"
    if value >= 1024 ** 2:
        return f"{value / 1024 ** 2:.1f} MB"
    return f"{value / 1024:.0f} KB"


class JobCard(QFrame):
    requested = Signal(str, str)

    def __init__(self, job: Job):
        super().__init__()
        self.setObjectName("jobCard")
        self.job_id = job.id
        self.previous_status = ""
        self.previous_actions = None
        self.content_kind = "unknown"
        self.thumbnail_path = ""
        self.thumbnail = QPixmap()
        row = QHBoxLayout(self)
        row.setContentsMargins(17, 15, 17, 15)
        row.setSpacing(14)
        self.cover = label("", "cover")
        self.cover.setFixedSize(46, 64)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.cover)
        body = QVBoxLayout()
        body.setSpacing(5)
        self.title = label("", "jobTitle", True)
        self.caption = label("", "caption", True)
        self.author = label("", "caption")
        self.message = label("", "caption", True)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setAccessibleName("作品下载进度")
        body.addWidget(self.title)
        body.addWidget(self.author)
        body.addWidget(self.caption)
        body.addWidget(self.message)
        body.addWidget(self.progress)
        row.addLayout(body, 1)
        self.actions = QGridLayout()
        self.actions.setSpacing(7)
        self.actions.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row.addLayout(self.actions)
        self.colors = theme_colors()
        self.update_job(job)

    def apply_theme(self, colors: dict[str, str]) -> None:
        self.colors = colors
        verifying = self.previous_status == "verification"
        if not verifying and not self.thumbnail.isNull() and self.content_kind == "album":
            self.cover.setPixmap(self.thumbnail.scaled(46, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            kind = "shield" if verifying else "images" if self.content_kind == "album" else "film"
            self.cover.setPixmap(icon(kind, colors["warn"] if verifying else colors["icon"], 23).pixmap(23, 23))

    def update_job(self, job: Job) -> None:
        self.title.setText(job.title)
        self.content_kind = job.content_kind
        if self.thumbnail_path != job.thumbnail_path:
            self.thumbnail_path = job.thumbnail_path
            self.thumbnail = QPixmap()
            try:
                path = Path(job.thumbnail_path)
                reader = QImageReader(str(path))
                size = reader.size()
                if path.is_file() and path.stat().st_size < 512 * 1024 and 0 < size.width() <= 128 and 0 < size.height() <= 128:
                    self.thumbnail = QPixmap.fromImage(reader.read())
            except OSError:
                pass
        author = job.author
        album = job.content_kind == "album"
        if album:
            author += (" · " if author else "") + f"图文 · {job.image_total} 张"
        self.author.setText(author)
        self.author.setVisible(bool(author))
        status = STATUS_LABELS[job.status]
        if album and job.image_total and job.status != "verification":
            text = f"{status} · 已保存 {job.image_done}/{job.image_total} 张"
            if job.status == "downloading" and job.current_image:
                size = f"/{format_bytes(job.image_size)}" if job.image_size else ""
                text += f" · 当前第 {job.current_image} 张 {format_bytes(job.image_bytes)}{size} · {format_bytes(job.speed)}/s"
            elif job.status == "partial" and job.image_failed:
                text += f"，{job.image_failed} 张失败"
            elif job.status == "completed":
                text += f" · {format_bytes(job.downloaded)}"
            self.caption.setText(text)
        elif job.status == "downloading":
            total = f" / {format_bytes(job.total)}" if job.total else ""
            percent = f" · {min(100, int(job.downloaded * 100 / job.total))}%" if job.total else ""
            self.caption.setText(f"{status}{percent} · {format_bytes(job.downloaded)}{total} · {format_bytes(job.speed)}/s")
        elif job.status == "completed":
            self.caption.setText(f"已完成 · {format_bytes(job.downloaded)}")
        elif job.status == "verification":
            self.caption.setText(f"等待浏览器验证 · 剩余 {job.remaining} 秒")
        else:
            self.caption.setText(status)
        self.progress.setVisible(job.status in {"downloading", "finalizing", "partial"})
        if album and job.image_total:
            self.progress.setRange(0, job.image_total)
            self.progress.setValue(job.image_done)
        elif job.total and job.status == "downloading":
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, int(job.downloaded * 100 / job.total)))
        else:
            self.progress.setRange(0, 0)
        messages = [job.message] if job.message and job.status in {"failed", "partial", "cancelled", "verification", "deferred", "interrupted", "resolving"} else []
        if job.notice:
            messages.append(job.notice)
        self.message.setText("\n".join(messages))
        self.message.setVisible(bool(messages))
        if job.status != self.previous_status:
            names = {"completed": "success", "verification": "warning", "partial": "warning", "downloading": "active"}
            self.caption.setObjectName(names.get(job.status, "caption"))
            self.caption.style().unpolish(self.caption)
            self.caption.style().polish(self.caption)
            self.progress.setObjectName("partialProgress" if job.status == "partial" else "")
            self.progress.style().unpolish(self.progress)
            self.progress.style().polish(self.progress)
        self.previous_status = job.status
        self.apply_theme(self.colors)
        action_key = (job.status, album, bool(job.result_dir), bool(job.caption_path), bool(job.image_errors))
        if action_key != self.previous_actions:
            self.previous_actions = action_key
            while self.actions.count():
                item = self.actions.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()
            if album and job.status == "completed":
                actions = [("打开目录", "folder")]
                if job.caption_path:
                    actions.append(("查看文案", "caption"))
            elif album and job.status == "partial":
                actions = [("重试失败项", "retry"), ("打开目录", "folder"), ("查看失败", "errors")]
            elif album and job.status in {"cancelled", "interrupted", "deferred", "failed"}:
                actions = [("继续下载" if job.image_done else "重新下载", "retry")]
                if job.result_dir:
                    actions.append(("打开目录", "folder"))
                if job.image_errors:
                    actions.append(("查看失败", "errors"))
            elif job.status == "completed":
                actions = [("打开文件", "open"), ("打开目录", "folder")]
            elif job.status == "verification":
                actions = [("继续解析", "resume"), ("显示浏览器", "show"), ("稍后处理", "defer"), ("取消", "cancel")]
            elif job.status == "finalizing":
                actions = []
            elif job.status in {"queued", "resolving", "downloading"}:
                actions = [("取消", "cancel")]
            else:
                actions = [("重新下载", "retry")]
            for index, (text, action) in enumerate(actions):
                name = "warningAction" if action == "resume" else "link" if action in {"defer", "cancel"} and job.status == "verification" else "outlineAccent" if action == "open" else ""
                control = button(text, name)
                control.setMinimumWidth(88)
                control.setProperty("jobAction", action)
                control.clicked.connect(lambda checked=False, name=action: self.requested.emit(self.job_id, name))
                self.actions.addWidget(control, index // 2, index % 2)
        self.setAccessibleName(f"{job.title}，{status}")


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path, preview: bool = False):
        super().__init__()
        self.data_dir = data_dir
        self.preview = preview
        self.preferences = Preferences(data_dir)
        self.colors = theme_colors(self.preferences.theme)
        self.store = Store(data_dir)
        self.vault = CookieVault(data_dir)
        self.jobs = self.store.load() if preview else self.store.recover()
        self.cookies: list[dict] = []
        startup_message = ""
        if self.preferences.remember:
            try:
                self.cookies = self.vault.load()
            except RuntimeError as exc:
                startup_message = str(exc)
        self.thread: QThread | None = None
        self.worker: DownloadWorker | None = None
        self.active_id: str | None = None
        self.closing = False
        self._closed_store = False
        self._last_persist: dict[str, float] = {}
        self.cards: dict[str, JobCard] = {}
        self.history_cards: dict[str, JobCard] = {}
        self.setWindowTitle("拾影 · 抖音作品下载")
        self.setWindowIcon(app_icon())
        self.resize(1120, 800)
        self.setMinimumSize(960, 700)
        self._build_ui()
        QApplication.styleHints().colorSchemeChanged.connect(self.apply_theme)
        self._apply_theme_preference()
        self.rebuild_lists()
        if startup_message:
            self.feedback.setText(startup_message)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(184)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(14, 30, 14, 20)
        left.setSpacing(6)
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 24)
        brand.setSpacing(9)
        self.brand_mark = label("")
        self.brand_mark.setFixedSize(BRAND_MARK_SIZE, BRAND_MARK_SIZE)
        self.brand_mark.setPixmap(brand_icon().pixmap(BRAND_MARK_SIZE, BRAND_MARK_SIZE))
        brand.addWidget(self.brand_mark, 0, Qt.AlignmentFlag.AlignVCenter)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addWidget(label("拾影", "brand"))
        brand_text.addWidget(label("LOCAL VIDEO", "brandSub"))
        brand.addLayout(brand_text)
        brand.addStretch()
        left.addLayout(brand)
        self.navigation = QButtonGroup(self)
        self.navigation.setExclusive(True)
        self.nav_buttons = {}
        for name, text, image in [
            ("downloads", "下载任务", "download"), ("history", "下载记录", "folder"), ("settings", "设置", "settings"),
        ]:
            control = NavigationButton(text)
            control.setObjectName("nav")
            control.setProperty("iconKind", image)
            control.setIcon(icon(image))
            control.setIconSize(QSize(20, 20))
            control.setCursor(Qt.CursorShape.PointingHandCursor)
            control.setFixedHeight(46)
            control.setCheckable(True)
            control.clicked.connect(lambda checked=False, view=name: self.set_view(view))
            self.navigation.addButton(control)
            self.nav_buttons[name] = control
            left.addWidget(control)
        left.addStretch()
        self.session_label = label("", "caption", True)
        left.addWidget(self.session_label)
        left.addSpacing(4)
        left.addWidget(label("作品保存在你的电脑", "caption"))
        left.addWidget(label(f"v{__version__} · Windows 桌面版", "caption"))
        layout.addWidget(sidebar)
        main_widget = QWidget()
        main = QVBoxLayout(main_widget)
        main.setContentsMargins(30, 28, 30, 17)
        main.setSpacing(0)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(5)
        self.page_title = label("下载作品", "pageTitle")
        self.page_description = label("粘贴抖音分享内容，保存视频或图文到你的电脑。", "subtitle")
        heading.addWidget(self.page_title)
        heading.addWidget(self.page_description)
        header.addLayout(heading, 1)
        header.addWidget(
            label("界面预览 · 示例任务" if self.preview else "WINDOWS · 本地下载", "tag"),
            0, Qt.AlignmentFlag.AlignVCenter,
        )
        main.addLayout(header)
        main.addSpacing(25)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._download_page())
        self.stack.addWidget(self._history_page())
        self.stack.addWidget(self._settings_page())
        main.addWidget(self.stack, 1)
        self.feedback = label("", "feedback", True)
        self.feedback.setMinimumHeight(24)
        main.addSpacing(10)
        main.addWidget(self.feedback)
        layout.addWidget(main_widget, 1)
        self.set_view("downloads")
        self.shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.shortcut.activated.connect(self.submit)
        self._update_session_label()

    def _download_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        composer = QFrame()
        composer.setObjectName("composer")
        form = QVBoxLayout(composer)
        form.setContentsMargins(20, 17, 20, 18)
        form.setSpacing(11)
        top = QHBoxLayout()
        title = label("抖音分享链接", "sectionTitle")
        self.paste_btn = button("从剪贴板粘贴", "link", "clipboard")
        self.paste_btn.clicked.connect(self.paste)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.paste_btn)
        form.addLayout(top)
        self.share_input = QPlainTextEdit()
        self.share_input.setAccessibleName("抖音分享链接")
        self.share_input.setPlaceholderText("粘贴抖音分享文字、视频或图文链接\n自动识别作品类型，无需手动删除链接前后的文字。")
        self.share_input.setFixedHeight(92)
        self.share_input.setTabChangesFocus(True)
        form.addWidget(self.share_input)
        self.input_error = label("", "error", True)
        self.input_error.hide()
        form.addWidget(self.input_error)
        bottom = QHBoxLayout()
        directory = QVBoxLayout()
        directory.setSpacing(0)
        directory.addWidget(label("保存到", "caption"))
        self.directory_btn = button("", "directory", "folder")
        self.directory_btn.clicked.connect(self.choose_directory)
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(self.directory_btn)
        change_path = button("更改", "link")
        change_path.clicked.connect(self.choose_directory)
        path_row.addWidget(change_path)
        path_row.addStretch()
        directory.addLayout(path_row)
        bottom.addLayout(directory, 1)
        self.add_btn = button("添加下载", "primary", "plus")
        self.add_btn.setToolTip("添加下载任务（Ctrl+Enter）")
        self.add_btn.clicked.connect(self.submit)
        bottom.addWidget(self.add_btn)
        form.addLayout(bottom)
        layout.addWidget(composer)
        layout.addSpacing(23)
        queue_header = QHBoxLayout()
        queue_header.setSpacing(10)
        queue_header.addWidget(label("下载队列", "sectionTitle"))
        self.queue_count = label("", "caption")
        queue_header.addWidget(self.queue_count)
        queue_header.addStretch()
        queue_header.addWidget(label("依次下载 · 并发 1", "caption"))
        layout.addLayout(queue_header)
        layout.addSpacing(12)
        self.job_scroll, self.job_layout = self._job_list()
        layout.addWidget(self.job_scroll, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 10, 0, 0)
        footer.addWidget(label("支持抖音短链 / 视频 / 图文链接", "caption"))
        footer.addStretch()
        footer.addWidget(label("仅保存你有权使用的作品", "caption"))
        layout.addLayout(footer)
        return page

    @staticmethod
    def _job_list() -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        container.setObjectName("jobList")
        content = QVBoxLayout(container)
        content.setContentsMargins(1, 1, 1, 1)
        content.setSpacing(0)
        content.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)
        return scroll, content

    def _history_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.history_count = label("", "sectionTitle")
        top.addWidget(self.history_count)
        top.addStretch()
        open_dir = button("打开保存目录", "link", "folder")
        open_dir.clicked.connect(lambda: self.open_path(Path(self.preferences.output_dir)))
        top.addWidget(open_dir)
        layout.addLayout(top)
        self.history_scroll, self.history_layout = self._job_list()
        layout.addWidget(self.history_scroll, 1)
        return page

    def _settings_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        panel = QFrame()
        panel.setObjectName("settings")
        rows = QVBoxLayout(panel)
        rows.setContentsMargins(20, 3, 20, 3)
        rows.setSpacing(0)

        def setting(title: str, subtitle: QLabel, control: QWidget) -> None:
            if rows.count():
                divider = QFrame()
                divider.setObjectName("divider")
                divider.setFixedHeight(1)
                rows.addWidget(divider)
            row = QHBoxLayout()
            row.setContentsMargins(0, 13, 0, 13)
            text = QVBoxLayout()
            text.setSpacing(4)
            text.addWidget(label(title, "settingTitle"))
            text.addWidget(subtitle)
            row.addLayout(text, 1)
            row.addSpacing(16)
            row.addWidget(control)
            rows.addLayout(row)

        selector = QFrame()
        selector.setObjectName("themeSelector")
        selector.setAccessibleName("外观主题")
        selector.setFixedSize(294, 42)
        segments = QHBoxLayout(selector)
        segments.setContentsMargins(3, 3, 3, 3)
        segments.setSpacing(1)
        self.theme_group = QButtonGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_buttons = {}
        for mode, text, image in [("light", "浅色", "sun"), ("dark", "暗色", "moon"), ("system", "跟随系统", "monitor")]:
            control = button(text, "theme", image)
            control.setMinimumHeight(0)
            control.setCheckable(True)
            control.setChecked(self.preferences.theme == mode)
            control.setAccessibleName(f"外观主题：{text}")
            control.clicked.connect(lambda checked=False, mode=mode: self._change_theme(mode))
            self.theme_group.addButton(control)
            self.theme_buttons[mode] = control
            segments.addWidget(control, 5 if mode == "system" else 4)
        setting("外观主题", label("立即生效，并记住本机选择", "caption"), selector)
        self.setting_path = label("", "caption", True)
        change = button("更改目录")
        change.clicked.connect(self.choose_directory)
        setting("保存目录", self.setting_path, change)
        self.browser_combo = BrowserComboBox()
        self.browser_combo.addItem(icon("edge", "#1596cd"), "Microsoft Edge", "msedge")
        self.browser_combo.addItem(icon("chrome"), "Google Chrome", "chrome")
        self.browser_combo.setCurrentIndex(self.browser_combo.findData(self.preferences.channel))
        self.browser_combo.currentIndexChanged.connect(self._change_browser)
        setting("解析浏览器", label("解析与验证时打开软件专用浏览器窗口", "caption", True), self.browser_combo)
        self.remember_check = SessionCheckBox("启用")
        self.remember_check.setAccessibleName("记住浏览器登录状态")
        self.remember_check.setChecked(self.preferences.remember)
        self.remember_check.toggled.connect(self._change_remember)
        setting("记住浏览器登录状态", label("下次使用时复用本软件的独立会话", "caption"), self.remember_check)
        self.cookie_caption = label("", "caption", True)
        import_btn = button("导入文件")
        import_btn.clicked.connect(self.choose_cookies)
        setting("高级：导入 Cookie 文件", self.cookie_caption, import_btn)
        clear_btn = button("清除登录状态")
        clear_btn.clicked.connect(self.clear_session)
        setting("本机登录数据", label("清除本软件保存的会话，不影响日常浏览器", "caption", True), clear_btn)
        layout.addWidget(panel)
        notice = QFrame()
        notice.setObjectName("notice")
        note = QHBoxLayout(notice)
        note.setContentsMargins(16, 13, 16, 13)
        self.notice_icon = label("")
        self.notice_icon.setFixedSize(26, 26)
        note.addWidget(self.notice_icon, 0, Qt.AlignmentFlag.AlignTop)
        note.addSpacing(5)
        notice_text = QVBoxLayout()
        notice_text.addWidget(label("首次使用", "sectionTitle"))
        notice_text.addWidget(label("若页面要求登录或验证，请在浏览器中完成，再返回任务点击“继续解析”。", "", True))
        note.addLayout(notice_text, 1)
        layout.addWidget(notice)
        saved = QHBoxLayout()
        saved.setSpacing(7)
        self.saved_icon = label("")
        self.saved_icon.setFixedSize(16, 16)
        saved.addWidget(self.saved_icon)
        saved.addWidget(label("设置自动保存", "caption"))
        saved.addStretch()
        layout.addLayout(saved)
        layout.addStretch()
        self._update_paths()
        self._update_cookie_caption()
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def apply_theme(self, *args) -> None:
        self.colors = theme_colors(self.preferences.theme)
        self.setStyleSheet(stylesheet(self.preferences.theme))
        self.browser_combo.set_theme(self.colors)
        self.remember_check.set_theme(self.colors)
        self.notice_icon.setPixmap(icon("info", self.colors["accent"], 24).pixmap(24, 24))
        self.saved_icon.setPixmap(icon("check", self.colors["muted"], 16).pixmap(16, 16))
        self._refresh_icons()

    def _refresh_icons(self) -> None:
        for control in self.findChildren(QPushButton):
            kind = control.property("iconKind")
            if kind:
                if control.objectName() == "primary" or control.objectName() == "theme" and control.isChecked():
                    color = self.colors["onAccent"]
                elif control.isChecked() or control.objectName() in {"link", "directory"}:
                    color = self.colors["accent"]
                else:
                    color = self.colors["icon"]
                control.setIcon(icon(kind, color))
            if isinstance(control, NavigationButton):
                control.setProperty("accentColor", self.colors["accent"])
                control.update()
        for card in list(self.cards.values()) + list(self.history_cards.values()):
            card.apply_theme(self.colors)

    def _apply_theme_preference(self) -> None:
        hints = QApplication.styleHints()
        if self.preferences.theme == "system":
            hints.unsetColorScheme()
        else:
            hints.setColorScheme(Qt.ColorScheme.Dark if self.preferences.theme == "dark" else Qt.ColorScheme.Light)
        self.apply_theme()

    def _change_theme(self, mode: str) -> None:
        self.preferences.theme = mode
        self.preferences.save()
        self._apply_theme_preference()

    def set_view(self, name: str) -> None:
        names = {"downloads": (0, "下载作品", "粘贴抖音分享内容，保存视频或图文到你的电脑。"),
                 "history": (1, "下载记录", "已保存的视频和图文，随时查看。"),
                 "settings": (2, "设置", "调整外观、保存位置与浏览器会话。")}
        index, title, description = names[name]
        self.stack.setCurrentIndex(index)
        self.page_title.setText(title)
        self.page_description.setText(description)
        self.nav_buttons[name].setChecked(True)
        self._refresh_icons()

    def _update_paths(self) -> None:
        path = self.preferences.output_dir
        self.directory_btn.setText(self.fontMetrics().elidedText(path, Qt.TextElideMode.ElideMiddle, 380).replace("&", "&&"))
        self.directory_btn.setToolTip(path)
        self.setting_path.setText(path)

    def _update_session_label(self) -> None:
        self.session_label.setText("● 独立浏览器会话" if self.preferences.remember else "● 临时浏览器会话")

    def _update_cookie_caption(self) -> None:
        self.cookie_caption.setText(
            f"已导入 {len(self.cookies)} 项 · " + ("Windows 加密存储" if self.preferences.remember else "仅本次运行有效")
            if self.cookies else "可选：兼容 Netscape 格式的 cookies.txt"
        )

    def _change_browser(self) -> None:
        self.preferences.channel = self.browser_combo.currentData()
        self.preferences.save()
        self.feedback.setText("浏览器设置已保存，下一个任务生效。")

    def _change_remember(self, checked: bool) -> None:
        try:
            if checked and self.cookies:
                self.vault.save(self.cookies)
            elif not checked:
                self.vault.clear()
        except (OSError, RuntimeError) as exc:
            self.remember_check.blockSignals(True)
            self.remember_check.setChecked(self.preferences.remember)
            self.remember_check.blockSignals(False)
            QMessageBox.warning(self, "无法更新登录设置", str(exc))
            return
        self.preferences.remember = checked
        self.preferences.save()
        self._update_session_label()
        self._update_cookie_caption()
        self.feedback.setText("设置已保存，下一个任务生效。已有专用浏览器会话可通过“清除登录状态”移除。")

    def choose_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择作品保存目录", self.preferences.output_dir)
        if path:
            self.preferences.output_dir = str(Path(path).resolve())
            self.preferences.save()
            self._update_paths()
            self.feedback.setText("保存目录已更新，已有任务仍使用添加时的目录。")

    def choose_cookies(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "导入抖音 Cookie", "", "Cookie 文件 (*.txt);;所有文件 (*)")
        if not name:
            return
        try:
            cookies = import_cookies(Path(name))
            if self.preferences.remember:
                self.vault.save(cookies)
            self.cookies = cookies
            self._update_cookie_caption()
            self.feedback.setText("Cookie 已导入，下一个任务生效。")
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "导入失败", str(exc))

    def clear_session(self) -> None:
        if self.thread:
            QMessageBox.information(self, "任务正在执行", "请先完成或取消当前任务，再清除登录状态。")
            return
        if QMessageBox.question(self, "清除登录状态", "将清除本软件的独立浏览器会话与已导入 Cookie，是否继续？") != QMessageBox.StandardButton.Yes:
            return
        try:
            profile = self.data_dir / "browser-profile"
            if profile.exists():
                if profile.is_symlink() or profile.resolve().parent != self.data_dir.resolve():
                    raise RuntimeError("会话目录路径异常，未清除。")
                shutil.rmtree(profile)
            self.vault.clear()
            self.cookies = []
            self._update_cookie_caption()
            self.feedback.setText("本软件保存的登录状态已清除。")
        except (OSError, RuntimeError):
            QMessageBox.warning(self, "清除失败", "无法清除会话，请关闭本软件启动的浏览器后重试。")

    def paste(self) -> None:
        text = QApplication.clipboard().text()
        if not text.strip():
            self.input_error.setText("剪贴板中没有文字，请复制抖音分享链接。")
            self.input_error.show()
            return
        self.share_input.setPlainText(text)
        self.input_error.hide()
        self.share_input.setFocus()

    def submit(self) -> None:
        if self.closing:
            return
        try:
            url = extract_url(self.share_input.toPlainText())
        except ValueError as exc:
            self.input_error.setText(str(exc))
            self.input_error.show()
            return
        identifier = work_id_from_url(url)
        for existing in self.jobs:
            if (existing.status in ACTIVE_STATES and existing.destination == Path(self.preferences.output_dir).expanduser().resolve()
                    and (existing.url == url or (identifier and existing.work_id == identifier))):
                self.input_error.setText("这个作品已经在当前保存目录的下载队列中。")
                self.input_error.show()
                return
        job = Job(url=url, output_dir=self.preferences.output_dir, work_id=identifier)
        self.store.save(job)
        self.jobs.insert(0, job)
        self.share_input.clear()
        self.input_error.hide()
        self.feedback.setText("已添加到队列。" + ("当前为界面预览，不执行真实下载。" if self.preview else ""))
        self.set_view("downloads")
        self.rebuild_lists()
        self._start_next()

    def rebuild_lists(self) -> None:
        for content in (self.job_layout, self.history_layout):
            while content.count():
                item = content.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()
        self.cards.clear()
        self.history_cards.clear()
        for job in self.jobs:
            card = JobCard(job)
            card.apply_theme(self.colors)
            card.requested.connect(self.job_action)
            self.cards[job.id] = card
            self.job_layout.addWidget(card)
            if job.status == "completed" or job.content_kind == "album" and job.image_done and job.status not in ACTIVE_STATES:
                history = JobCard(job)
                history.apply_theme(self.colors)
                history.requested.connect(self.job_action)
                self.history_cards[job.id] = history
                self.history_layout.addWidget(history)
        if not self.jobs:
            empty = label("还没有下载任务\n\n粘贴抖音分享链接，开始保存视频或图文。", "muted", True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(190)
            self.job_layout.addWidget(empty)
        if not self.history_cards:
            empty = label("还没有已保存的作品。", "muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(170)
            self.history_layout.addWidget(empty)
        self.queue_count.setText(f"{len(self.jobs)} 个任务")
        self.history_count.setText(f"本地作品 · {len(self.history_cards)} 个")

    def _start_next(self) -> None:
        if self.thread or self.closing or self.preview:
            return
        job = next((item for item in reversed(self.jobs) if item.status == "queued"), None)
        if not job:
            return
        self.active_id = job.id
        config = SessionConfig(
            self.data_dir, self.preferences.channel, self.preferences.remember,
            [dict(cookie) for cookie in self.cookies],
        )
        self.thread = QThread(self)
        self.worker = DownloadWorker(Job(**job.as_dict()), config)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.changed.connect(self._event)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    @Slot(str, object)
    def _event(self, job_id: str, event: dict) -> None:
        job = next(item for item in self.jobs if item.id == job_id)
        previous = job.status
        for key, value in event.items():
            if key in JOB_EVENT_FIELDS:
                setattr(job, key, value)
        now = time.monotonic()
        if "status" in event or "title" in event or now - self._last_persist.get(job_id, 0) > 1:
            self.store.save(job)
            self._last_persist[job_id] = now
        if job.status in {"completed", "partial", "cancelled", "interrupted", "deferred", "failed"} and previous != job.status:
            self.rebuild_lists()
            if job.status in {"completed", "partial"}:
                self.feedback.setText(f"{STATUS_LABELS[job.status]}：{job.result_dir if job.content_kind == 'album' else job.file_path}")
        else:
            if job_id in self.cards:
                self.cards[job_id].update_job(job)
            if job_id in self.history_cards:
                self.history_cards[job_id].update_job(job)

    @Slot()
    def _thread_finished(self) -> None:
        finished = self.thread
        self.thread = None
        self.worker = None
        self.active_id = None
        if finished:
            finished.deleteLater()
        if self.closing:
            QTimer.singleShot(0, self.close)
        else:
            QTimer.singleShot(0, self._start_next)

    def job_action(self, job_id: str, action: str) -> None:
        job = next(item for item in self.jobs if item.id == job_id)
        if action == "open":
            self.open_path(Path(job.file_path))
        elif action == "folder":
            self.open_path(Path(job.result_dir if job.content_kind == "album" else job.file_path), select=True)
        elif action == "caption":
            self.open_path(Path(job.caption_path))
        elif action == "errors":
            dialog = QDialog(self)
            dialog.setWindowTitle("未完成项")
            dialog.resize(560, 360)
            layout = QVBoxLayout(dialog)
            details = QPlainTextEdit()
            details.setReadOnly(True)
            details.setPlainText("\n".join(job.image_errors) or job.message or "暂无失败详情。")
            layout.addWidget(details)
            close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            close.rejected.connect(dialog.reject)
            layout.addWidget(close)
            dialog.exec()
        elif action == "retry":
            if job.status in ACTIVE_STATES:
                return
            job.status = "queued"
            if job.content_kind != "album":
                job.downloaded = 0
                job.total = None
            job.current_image = 0
            job.image_bytes = 0
            job.speed = 0
            job.message = ""
            self.store.save(job)
            self.rebuild_lists()
            self._start_next()
        elif self.active_id == job_id and self.worker:
            if action == "cancel":
                self.worker.cancel.set()
                self.feedback.setText("正在取消，当前网络请求结束后会停止。")
            elif action == "resume":
                self.worker.resume.set()
            elif action == "show":
                self.worker.show_browser.set()
            elif action == "defer":
                self.worker.defer.set()
        elif action == "cancel" and job.status in ACTIVE_STATES:
            job.status = "cancelled"
            job.message = "任务已取消。"
            self.store.save(job)
            self.rebuild_lists()

    def open_path(self, path: Path, select: bool = False) -> None:
        if not path.exists():
            QMessageBox.information(self, "文件不存在", "文件可能已移动或删除，请重新下载或检查保存目录。")
            return
        if select and path.is_file() and os.name == "nt":
            subprocess.Popen(["explorer.exe", "/select,", str(path.resolve())])
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            QMessageBox.warning(self, "无法打开", "系统未能打开该文件或目录，请在资源管理器中查看。")

    def closeEvent(self, event) -> None:
        if self.thread:
            if not self.closing:
                answer = QMessageBox.question(
                    self, "停止下载并退出？", "当前任务尚未完成。退出将取消下载，之后可重新下载。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
                self.closing = True
                self.add_btn.setEnabled(False)
                self.feedback.setText("正在停止任务并关闭独立浏览器，请稍候…")
                if self.worker:
                    self.worker.cancel.set()
            event.ignore()
            return
        if not self._closed_store:
            self.preferences.save()
            self.store.close()
            self._closed_store = True
        event.accept()
