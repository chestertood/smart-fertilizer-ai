# Kiosk setup

Runs the app full-screen with no window frame and no title-bar buttons, quit
via the red power button at the bottom-left of the nav rail.

**This is the default.** `python main.py` opens full-screen on any platform —
no flag needed. Set `KIOSK=0` to get an ordinary resizable window back, which
is what you want while developing:

```bash
KIOSK=0 python main.py        # Linux/macOS
set KIOSK=0 && python main.py # Windows cmd
```

Nothing in the app depends on the working directory — every path (`.env`, the
database, the crop seed, assets) resolves from its own file location. So a
launcher only has to name `main.py` by absolute path.

## Raspberry Pi: start at boot

Copy the project to the Pi, `pip install -r requirements.txt`, then:

```bash
mkdir -p ~/.config/autostart
cp /home/pi/LLM_fertilizer/scripts/smartfert.desktop ~/.config/autostart/
sudo reboot
```

That's the whole thing — the `.desktop` file just runs `python3 main.py`. If
the project lives somewhere other than `/home/pi/LLM_fertilizer`, edit the
`Exec=` line to match.

## Windows

`python main.py` is enough. `scripts\start_kiosk.bat` is a double-click
convenience: it runs the app under `pythonw`, so no black console window sits
behind the kiosk. Right-click it → Send to → Desktop for a shortcut.

## Quitting

The kiosk window has no title bar, so there is no close button in the corner.
Exit with the red power button at the bottom-left of the nav rail (it asks for
confirmation first).

If the UI ever becomes unresponsive: `pkill -f 'python.*main.py'` on the Pi, or
Task Manager on Windows. Alt+F4 also still works on Windows.

## Notes

- Autostart runs after the desktop session loads, so the Pi must be set to boot
  to desktop, not to the console (`sudo raspi-config` → System Options → Boot).
- **The first run on the Pi needs internet.** `flet-desktop` ships no binary; it
  downloads the Flutter client (`flet-linux-debian12-arm64`, ~25 MB) into
  `~/.flet/client/` on first launch and reuses it offline after that. Run
  `python3 main.py` once by hand before relying on autostart.
- Logs land in `data/app.log` — the first place to look if the screen stays
  blank after boot.
- The display is expected to be in landscape. Portrait works but the layout is
  built for 1280x720.
