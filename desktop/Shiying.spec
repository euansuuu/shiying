from pathlib import Path
import os
import re
from PyInstaller.utils.hooks import collect_all

desktop = Path(SPECPATH)
root = desktop.parent
pw_data, pw_binaries, pw_imports = collect_all("playwright")
a = Analysis(
    [str(desktop / "entry.py")],
    pathex=[str(root)],
    binaries=pw_binaries,
    datas=pw_data,
    hiddenimports=pw_imports,
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "yt_dlp"],
    noarchive=False,
)
# Qt uses Windows ICU. PATH may expose incompatible Poppler/Conda ICU DLLs.
a.binaries = [
    entry for entry in a.binaries
    if not re.fullmatch(r"icu(?:uc|in|dt)(?:\d+)?\.dll", Path(entry[0]).name.lower())
]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Shiying",
    debug=False, strip=False, upx=False, console=os.environ.get("SHIYING_DEBUG") == "1",
    icon=str(desktop / "assets" / "app.ico"),
    version=str(desktop / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Shiying")
