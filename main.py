import logging
import logging.handlers
import os
import sys
import flet as ft
from app.app import main

# Base dir for writable runtime data. When packaged with `flet pack`
# (PyInstaller), __file__ points into the temp extraction dir (_MEIPASS),
# which is deleted on exit — so logs/DB would vanish. Use the exe's own
# folder when frozen, the source dir otherwise.
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Bundled assets (window icon) live next to the source, or in _MEIPASS when
# frozen (added via `flet pack --add-data assets`).
_ASSETS_DIR = os.path.join(
    getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "assets"
)

# Logging was never configured, so every logger.info/error across the
# services was silently discarded — undebuggable on the Pi. Console +
# rotating file (data/app.log, 3 x 1MB).
_LOG_DIR = os.path.join(_BASE_DIR, "data")
os.makedirs(_LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            os.path.join(_LOG_DIR, "app.log"),
            maxBytes=1_000_000, backupCount=3, encoding="utf-8",
        ),
    ],
)

# 1. เอา sys.platform.startswith("linux") ออก 
# เพื่อไม่ให้มันบังคับเปิดบนเว็บเมื่ออยู่บน Raspberry Pi
use_web = os.environ.get("FLET_VIEW") == "web" 
port = int(os.environ.get("FLET_WEB_PORT", "8550"))
host = os.environ.get("FLET_WEB_HOST", "0.0.0.0")

if use_web:
    print(
        f"\n>>> Open in a browser on this machine:  http://localhost:{port}"
        f"\n>>> Or from another device on the same network:  http://<this-pi-ip>:{port}\n",
        flush=True,
    )
    ft.run(main, view=ft.AppView.WEB_BROWSER, port=port, host=host,
           assets_dir=_ASSETS_DIR)
else:
    # 2. เมื่อเข้ามาตรงนี้ บน Pi 5 จะเปิดเป็นหน้าต่างโปรแกรมทันที
    # แนะนำให้ใส่พารามิเตอร์ของ Flet AppView ลงไปเพื่อความชัวร์
    ft.run(main, view=ft.AppView.FLET_APP, assets_dir=_ASSETS_DIR)