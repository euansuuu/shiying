from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication


def icon(kind: str, color: str = "#6e91bc", size: int = 20) -> QIcon:
    image = QPixmap(size * 2, size * 2)
    image.fill(Qt.GlobalColor.transparent)
    image.setDevicePixelRatio(2)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24, size / 24)
    painter.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == "folder":
        painter.drawPolyline([QPointF(3, 19), QPointF(3, 5), QPointF(9, 5), QPointF(11, 8), QPointF(21, 8), QPointF(21, 19), QPointF(3, 19)])
    elif kind == "settings":
        painter.drawEllipse(QRectF(5, 5, 14, 14))
        painter.drawEllipse(QRectF(9, 9, 6, 6))
        for x1, y1, x2, y2 in [(12, 2, 12, 5), (12, 19, 12, 22), (2, 12, 5, 12), (19, 12, 22, 12),
                               (5, 5, 7, 7), (17, 17, 19, 19), (5, 19, 7, 17), (17, 7, 19, 5)]:
            painter.drawLine(x1, y1, x2, y2)
    elif kind == "sun":
        painter.drawEllipse(QRectF(8, 8, 8, 8))
        for x1, y1, x2, y2 in [(12, 2, 12, 5), (12, 19, 12, 22), (2, 12, 5, 12), (19, 12, 22, 12),
                               (5, 5, 7, 7), (17, 17, 19, 19), (5, 19, 7, 17), (17, 7, 19, 5)]:
            painter.drawLine(x1, y1, x2, y2)
    elif kind == "moon":
        path = QPainterPath(QPointF(16, 3))
        path.cubicTo(3, 0, 0, 19, 12, 21)
        path.cubicTo(17, 22, 21, 18, 21, 14)
        path.cubicTo(12, 18, 8, 9, 16, 3)
        painter.drawPath(path)
    elif kind == "monitor":
        painter.drawRoundedRect(QRectF(3, 4, 18, 13), 1, 1)
        painter.drawLine(12, 17, 12, 21)
        painter.drawLine(8, 21, 16, 21)
    elif kind == "info":
        painter.drawEllipse(QRectF(3, 3, 18, 18))
        painter.drawPoint(12, 8)
        painter.drawLine(12, 11, 12, 17)
    elif kind == "chrome":
        painter.setPen(Qt.PenStyle.NoPen)
        for start, fill in [(30, "#ea4335"), (150, "#34a853"), (270, "#fbbc05")]:
            painter.setBrush(QColor(fill))
            painter.drawPie(QRectF(2, 2, 20, 20), start * 16, 120 * 16)
        painter.setBrush(QColor("#4285f4"))
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawEllipse(QRectF(7, 7, 10, 10))
    elif kind == "edge":
        painter.drawEllipse(QRectF(3, 3, 18, 18))
        painter.drawEllipse(QRectF(7, 3, 10, 18))
        painter.drawLine(3, 12, 21, 12)
    elif kind == "clipboard":
        painter.drawRoundedRect(QRectF(5, 5, 14, 16), 2, 2)
        painter.drawRoundedRect(QRectF(9, 3, 6, 4), 1, 1)
        painter.drawLine(9, 12, 15, 12)
        painter.drawLine(9, 16, 15, 16)
    elif kind == "plus":
        painter.drawLine(12, 5, 12, 19)
        painter.drawLine(5, 12, 19, 12)
    elif kind == "images":
        painter.drawRoundedRect(QRectF(3, 3, 15, 15), 2, 2)
        painter.drawRoundedRect(QRectF(6, 6, 15, 15), 2, 2)
        painter.drawEllipse(QRectF(9, 9, 3, 3))
        painter.drawPolyline([QPointF(8, 18), QPointF(13, 13), QPointF(17, 17), QPointF(19, 15)])
    elif kind == "film":
        painter.drawRoundedRect(QRectF(5, 3, 14, 18), 2, 2)
        painter.drawLine(9, 4, 9, 20)
        painter.drawLine(15, 4, 15, 20)
        painter.drawLine(5, 9, 19, 9)
        painter.drawLine(5, 15, 19, 15)
    elif kind == "check":
        painter.drawPolyline([QPointF(5, 12), QPointF(10, 17), QPointF(20, 7)])
    elif kind == "shield":
        painter.drawPolyline([QPointF(12, 3), QPointF(20, 6), QPointF(19, 15), QPointF(12, 21), QPointF(5, 15), QPointF(4, 6), QPointF(12, 3)])
        painter.drawLine(12, 8, 12, 13)
        painter.drawPoint(12, 17)
    else:
        painter.drawLine(12, 3, 12, 15)
        painter.drawPolyline([QPointF(7, 10), QPointF(12, 15), QPointF(17, 10)])
        painter.drawPolyline([QPointF(4, 17), QPointF(4, 21), QPointF(20, 21), QPointF(20, 17)])
    painter.end()
    return QIcon(image)


def brand_icon(tile: bool = False) -> QIcon:
    image = QPixmap(512, 512)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(4, 4)
    painter.setPen(Qt.PenStyle.NoPen)
    if tile:
        background = QLinearGradient(0, 0, 128, 128)
        background.setColorAt(0, QColor("#f5fbff"))
        background.setColorAt(1, QColor("#dcefff"))
        painter.setBrush(background)
        painter.drawRoundedRect(QRectF(2, 2, 124, 124), 28, 28)
        painter.translate(12, 10)
        painter.scale(0.82, 0.82)

    ribbon = QPainterPath(QPointF(34, 9))
    ribbon.cubicTo(23, 3, 11, 12, 11, 28)
    ribbon.lineTo(11, 66)
    ribbon.cubicTo(11, 79, 18, 85, 31, 85)
    ribbon.lineTo(44, 85)
    ribbon.cubicTo(50, 85, 54, 90, 54, 96)
    ribbon.lineTo(54, 98)
    ribbon.lineTo(40, 98)
    ribbon.quadTo(35, 98, 39, 103)
    ribbon.lineTo(60, 123)
    ribbon.quadTo(63, 126, 66, 123)
    ribbon.lineTo(88, 103)
    ribbon.quadTo(92, 98, 86, 98)
    ribbon.lineTo(73, 98)
    ribbon.lineTo(73, 91)
    ribbon.lineTo(96, 77)
    ribbon.cubicTo(119, 64, 120, 49, 99, 36)
    ribbon.lineTo(47, 9)
    ribbon.quadTo(40, 5, 34, 9)
    ribbon.closeSubpath()
    ribbon.moveTo(38, 35)
    ribbon.cubicTo(38, 29, 42, 27, 48, 31)
    ribbon.lineTo(83, 51)
    ribbon.cubicTo(90, 55, 89, 60, 83, 64)
    ribbon.lineTo(47, 76)
    ribbon.quadTo(38, 81, 38, 73)
    ribbon.closeSubpath()
    ribbon.setFillRule(Qt.FillRule.OddEvenFill)
    gradient = QLinearGradient(15, 20, 110, 90)
    gradient.setColorAt(0, QColor("#1675ff"))
    gradient.setColorAt(0.55, QColor("#244dec"))
    gradient.setColorAt(1, QColor("#22d3ed"))
    painter.fillPath(ribbon, gradient)

    fold = QPainterPath(QPointF(11, 37))
    fold.cubicTo(8, 11, 23, 1, 44, 10)
    fold.lineTo(99, 39)
    fold.cubicTo(119, 52, 112, 68, 96, 77)
    fold.lineTo(73, 91)
    fold.lineTo(73, 81)
    fold.cubicTo(73, 73, 69, 68, 64, 67)
    fold.lineTo(83, 60)
    fold.cubicTo(94, 55, 87, 43, 77, 37)
    fold.lineTo(48, 22)
    fold.cubicTo(30, 13, 17, 23, 11, 37)
    fold.closeSubpath()
    highlight = QLinearGradient(22, 8, 108, 74)
    highlight.setColorAt(0, QColor("#22d9eb"))
    highlight.setColorAt(0.55, QColor("#3376ff"))
    highlight.setColorAt(0.72, QColor("#6563fa"))
    highlight.setColorAt(1, QColor("#18cde8"))
    painter.fillPath(fold, highlight)

    arrow = QPainterPath(QPointF(11, 66))
    arrow.cubicTo(13, 82, 27, 80, 43, 80)
    arrow.cubicTo(64, 77, 73, 84, 73, 98)
    arrow.lineTo(86, 98)
    arrow.quadTo(92, 98, 88, 103)
    arrow.lineTo(66, 123)
    arrow.quadTo(63, 126, 60, 123)
    arrow.lineTo(39, 103)
    arrow.quadTo(35, 98, 40, 98)
    arrow.lineTo(54, 98)
    arrow.lineTo(54, 96)
    arrow.cubicTo(54, 90, 50, 85, 44, 85)
    arrow.lineTo(31, 85)
    arrow.cubicTo(18, 85, 11, 79, 11, 66)
    gradient = QLinearGradient(28, 104, 82, 84)
    gradient.setColorAt(0, QColor("#137bff"))
    gradient.setColorAt(1, QColor("#16d5e8"))
    painter.fillPath(arrow, gradient)
    painter.end()
    return QIcon(image)


def app_icon() -> QIcon:
    return brand_icon(tile=True)


def theme_colors(mode: str = "system") -> dict[str, str]:
    dark = mode == "dark" or (mode == "system" and QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark)
    return (
        {"bg":"#0d1728", "panel":"#142238", "side":"#101d31", "text":"#e8effb", "muted":"#a2b3cd",
         "line":"#2a3d59", "accent":"#85bcff", "onAccent":"#ffffff", "tint":"#1c3657", "field":"#101d30",
         "icon":"#a2bee4", "error":"#ffb4bd", "warn":"#efc27d", "success":"#8bd8b2",
         "buttonStart":"#2369db", "buttonEnd":"#117d9b", "progressEnd":"#63d7ea", "hover":"#23456e"}
        if dark else
        {"bg":"#f3f8ff", "panel":"#ffffff", "side":"#edf4fd", "text":"#202d43", "muted":"#5e708a",
         "line":"#dfe9f6", "accent":"#1764d8", "onAccent":"#ffffff", "tint":"#e5f0ff", "field":"#f6faff",
         "icon":"#6485b0", "error":"#ad3f50", "warn":"#8e5d13", "success":"#24734c",
         "buttonStart":"#1e69e8", "buttonEnd":"#117d9b", "progressEnd":"#43cde3", "hover":"#d8eaff"}
    )


def stylesheet(mode: str = "system") -> str:
    tokens = theme_colors(mode)
    css = """
    QWidget { color:@text; font-family:"Microsoft YaHei UI"; font-size:14px; }
    QMainWindow, QWidget#central, QWidget#page { background:@bg; }
    QFrame#sidebar { background:@side; border-right:1px solid @line; }
    QLabel { background:transparent; }
    QLabel#brand { font-size:25px; font-weight:600; letter-spacing:2px; }
    QLabel#brandSub { color:@muted; font-size:10px; letter-spacing:1px; }
    QLabel#pageTitle { font-size:25px; font-weight:600; }
    QLabel#subtitle, QLabel#muted, QLabel#caption { color:@muted; }
    QLabel#caption { font-size:12px; }
    QLabel#sectionTitle, QLabel#settingTitle { font-size:14px; font-weight:600; }
    QLabel#tag { color:@muted; background:@field; font-size:11px; border:1px solid @line; border-radius:6px; padding:4px 8px; }
    QLabel#error { color:@error; font-size:12px; }
    QLabel#feedback { color:@accent; font-size:12px; }
    QLabel#cover { background:@tint; border-radius:7px; }
    QLabel#warning { color:@warn; font-size:12px; }
    QLabel#success { color:@success; font-size:12px; }
    QLabel#active { color:@accent; font-size:12px; }
    QLabel#jobTitle { font-weight:600; }
    QPushButton { background:@panel; border:1px solid @line; border-radius:8px; padding:8px 13px; }
    QPushButton:hover { background:@tint; }
    QPushButton:pressed { border-color:@accent; }
    QPushButton:focus { border:1px solid @accent; }
    QPushButton:disabled { color:@muted; }
    QPushButton#primary { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @buttonStart,stop:1 @buttonEnd); color:@onAccent; border:1px solid transparent; border-radius:9px; font-weight:600; padding:10px 18px; }
    QPushButton#primary:hover { border:1px solid @accent; }
    QPushButton#primary:pressed { background:@buttonStart; }
    QPushButton#primary:disabled { background:@side; color:@muted; border-color:@line; }
    QPushButton#link { color:@accent; background:transparent; border:1px solid transparent; padding:4px 5px; font-size:12px; }
    QPushButton#link:hover { background:@tint; }
    QPushButton#outlineAccent { color:@accent; }
    QPushButton#warningAction { color:@warn; border-color:@warn; }
    QPushButton#directory { text-align:left; background:transparent; border:1px solid transparent; padding:2px 0; font-size:12px; }
    QPushButton#directory:hover { color:@accent; }
    QPushButton#nav { text-align:left; padding:12px 16px; border:0; border-radius:8px; background:transparent; }
    QPushButton#nav:checked { color:@accent; background:@tint; font-weight:600; }
    QPushButton#nav:hover { background:@tint; }
    QPushButton#nav:focus { border:1px solid @accent; }
    QFrame#themeSelector { background:@field; border:1px solid @line; border-radius:8px; }
    QPushButton#theme { background:transparent; border:0; border-radius:6px; padding:7px 9px; font-size:13px; }
    QPushButton#theme:hover { background:@tint; }
    QPushButton#theme:checked { background:@buttonStart; color:#ffffff; }
    QPushButton#theme:focus { border:1px solid @accent; }
    QFrame#divider { background:@line; border:0; }
    QFrame#composer, QWidget#jobList, QFrame#settings { background:@panel; border:1px solid @line; border-radius:12px; }
    QFrame#jobCard { background:transparent; border:0; border-bottom:1px solid @line; }
    QPlainTextEdit { background:@field; color:@text; border:1px solid @line; border-radius:8px; padding:10px; selection-background-color:@buttonStart; selection-color:#ffffff; }
    QPlainTextEdit:focus { border-color:@accent; }
    QScrollArea { background:transparent; border:0; }
    QScrollArea > QWidget > QWidget { background:@panel; }
    QScrollArea#settingsScroll > QWidget > QWidget { background:@bg; }
    QScrollBar:vertical { background:transparent; width:8px; margin:2px; }
    QScrollBar::handle:vertical { background:@line; border-radius:3px; min-height:28px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:none; }
    QProgressBar { background:@side; border:0; border-radius:3px; height:5px; min-height:5px; max-height:5px; }
    QProgressBar::chunk { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @buttonStart,stop:1 @progressEnd); border-radius:3px; }
    QProgressBar#partialProgress::chunk { background:@warn; }
    QComboBox QAbstractItemView { background:@panel; selection-background-color:@tint; selection-color:@text; color:@text; border:1px solid @line; outline:0; padding:4px; }
    QComboBox QAbstractItemView::item { min-height:32px; padding:4px 10px; }
    QFrame#notice { background:@tint; border:0; border-radius:9px; }
    QMessageBox { background:@panel; }
    QToolTip { background:@panel; color:@text; border:1px solid @line; padding:5px; }
    """
    for key in sorted(tokens, key=len, reverse=True):
        css = css.replace("@" + key, tokens[key])
    return css
