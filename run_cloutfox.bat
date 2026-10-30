@echo off
rem Start CloutFox with a console window that shows its output.
rem The Start menu shortcut made by install.cmd starts it without one.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" cloutfox_app.py %*
) else (
    python cloutfox_app.py %*
)
