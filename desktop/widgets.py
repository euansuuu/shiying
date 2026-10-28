from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QPushButton

from .appearance import theme_colors


class NavigationButton(QPushButton):
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.isChecked():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.property("accentColor") or "#1764d8"))
            painter.drawRoundedRect(QRectF(4, (self.height() - 20) / 2, 3, 20), 1.5, 1.5)


class BrowserComboBox(QComboBox):
    """Keep native combo behavior while painting a single flat frame and arrow."""

    def __init__(self):
        super().__init__()
        self.colors = theme_colors()
        self.setFixedSize(206, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("解析浏览器")
        self.setIconSize(QSize(20, 20))

    def set_theme(self, colors: dict[str, str]) -> None:
        self.colors = colors
        self.update()

    def paintEvent(self, event) -> None:
        colors = self.colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font())
        painter.setBrush(QColor(colors["field"]))
        painter.setPen(QPen(QColor(colors["accent"] if self.hasFocus() else colors["line"]), 1))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 8, 8)
        left = 14
        if not self.itemIcon(self.currentIndex()).isNull():
            self.itemIcon(self.currentIndex()).paint(painter, 12, (self.height() - 20) // 2, 20, 20)
            left = 41
        painter.setPen(QColor(colors["text"] if self.isEnabled() else colors["muted"]))
        text = self.fontMetrics().elidedText(self.currentText(), Qt.TextElideMode.ElideRight, self.width() - left - 34)
        painter.drawText(self.rect().adjusted(left, 0, -34, 0), Qt.AlignmentFlag.AlignVCenter, text)
        painter.setPen(QPen(QColor(colors["icon"]), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        center = self.height() / 2
        painter.drawPolyline([QPointF(self.width() - 25, center - 2), QPointF(self.width() - 20, center + 3), QPointF(self.width() - 15, center - 2)])


class SessionCheckBox(QCheckBox):
    def __init__(self, text: str):
        super().__init__(text)
        self.colors = theme_colors()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)

    def sizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 32, 40)

    def hitButton(self, position) -> bool:
        return self.rect().contains(position)

    def set_theme(self, colors: dict[str, str]) -> None:
        self.colors = colors
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font())
        colors = self.colors
        top = (self.height() - 19) / 2
        fill = colors["buttonStart"] if self.isChecked() else colors["field"]
        border = colors["accent"] if self.hasFocus() else colors["buttonStart"] if self.isChecked() else colors["icon"]
        painter.setPen(QPen(QColor(border), 1.5 if self.hasFocus() else 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(QRectF(1, top, 19, 19), 4, 4)
        if self.isChecked():
            painter.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPolyline([QPointF(5, top + 10), QPointF(9, top + 14), QPointF(16, top + 6)])
        painter.setPen(QColor(colors["text"]))
        painter.drawText(self.rect().adjusted(29, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, self.text())
