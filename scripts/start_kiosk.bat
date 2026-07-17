@echo off
REM Launch Smart Fertilizer full-screen on Windows — same kiosk mode as the Pi.
REM Double-click this file, or make a desktop shortcut to it.

REM Resolve the repo root from this script's own location (%~dp0 = scripts\).
cd /d "%~dp0.."

set KIOSK=1

REM Prefer the venv interpreter when one exists; fall back to the launcher.
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" main.py
) else (
    start "" pythonw main.py
)
