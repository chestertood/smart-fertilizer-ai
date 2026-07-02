import os
import sys
import flet as ft
from app.app import main

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
    ft.run(main, view=ft.AppView.WEB_BROWSER, port=port, host=host)
else:
    # 2. เมื่อเข้ามาตรงนี้ บน Pi 5 จะเปิดเป็นหน้าต่างโปรแกรมทันที
    # แนะนำให้ใส่พารามิเตอร์ของ Flet AppView ลงไปเพื่อความชัวร์
    ft.run(main, view=ft.AppView.FLET_APP)