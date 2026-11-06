@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Iniciando NexFlow Pro...
if exist "C:\Python314\pythonw.exe" (
    start "" "C:\Python314\pythonw.exe" "%~dp0app.py"
) else (
    start "" pythonw "%~dp0app.py"
)
