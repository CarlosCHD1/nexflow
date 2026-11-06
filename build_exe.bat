@echo off
chcp 65001 >nul
title Compilador NexFlow Pro — Gerador de Executável (.exe)
echo ====================================================================
echo             NexFlow Pro — Gerador de Executável Comercial (.exe)
echo ====================================================================
echo.

cd /d "%~dp0"

echo [1/3] Verificando dependências de build (PyInstaller, Pillow)...
python -m pip install --upgrade pip
python -m pip install pillow pyinstaller

echo.
echo [2/3] Escolha o formato de compilação:
echo   1. Arquivo único (NexFlow.exe Standalone — ideal para distribuir/vender aos clientes)
echo   2. Pasta portátil (Inicialização ultrarrápida, ideal para instaladores)
set /p OPTION="Digite a opção [1 ou 2, padrão 1]: "

if "%OPTION%"=="2" (
    echo.
    echo [3/3] Compilando em pasta portátil...
    pyinstaller --noconfirm --clean ^
        --name "NexFlow" ^
        --windowed ^
        --icon "assets\icon.ico" ^
        --add-data "assets;assets" ^
        --add-data "config.example.json;." ^
        --hidden-import "PIL" ^
        --hidden-import "PIL.Image" ^
        --hidden-import "PIL.ImageTk" ^
        --hidden-import "licensing" ^
        --hidden-import "platform_adapter" ^
        --hidden-import "audio_recorder" ^
        --hidden-import "transcriber" ^
        --hidden-import "floating_pill" ^
        --hidden-import "win32_utils" ^
        app.py
) else (
    echo.
    echo [3/3] Compilando em arquivo único standalone...
    pyinstaller --noconfirm --clean --onefile ^
        --name "NexFlow" ^
        --windowed ^
        --icon "assets\icon.ico" ^
        --add-data "assets;assets" ^
        --add-data "config.example.json;." ^
        --hidden-import "PIL" ^
        --hidden-import "PIL.Image" ^
        --hidden-import "PIL.ImageTk" ^
        --hidden-import "licensing" ^
        --hidden-import "platform_adapter" ^
        --hidden-import "audio_recorder" ^
        --hidden-import "transcriber" ^
        --hidden-import "floating_pill" ^
        --hidden-import "win32_utils" ^
        app.py
)

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ====================================================================
    echo  SUCESSO! NexFlow.exe gerado com sucesso na pasta:
    echo  %~dp0dist\
    echo ====================================================================
) else (
    echo.
    echo [ERRO] Ocorreu uma falha durante a compilação do NexFlow.
)
echo.
pause
