@echo off
cd /d "%~dp0"
if exist "C:\Python314\pythonw.exe" (
    start "" "C:\Python314\pythonw.exe" "%~dp0app.py"
) else (
    start "" pythonw "%~dp0app.py"
)
