import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .appearance import app_icon


if __name__ == "__main__":
    app = QApplication([])
    destination = Path(__file__).resolve().parent / "assets" / "app.ico"
    destination.parent.mkdir(exist_ok=True)
    images = []
    application_icon = app_icon()
    sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
    for size in sizes:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not application_icon.pixmap(size, size).save(buffer, "PNG"):
            raise RuntimeError("无法生成应用图标")
        images.append(bytes(buffer.data()))
    offset = 6 + 16 * len(images)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    for size, data in zip(sizes, images):
        directory.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    destination.write_bytes(directory + b"".join(images))
    assert {size.width() for size in QIcon(str(destination)).availableSizes()} == set(sizes)
