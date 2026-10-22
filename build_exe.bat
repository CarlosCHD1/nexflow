@echo off
chcp 65001 >nul
title Compilador WisperFlow Free — Gerador de Executável (.exe)
echo ====================================================================
echo             WisperFlow Free — Gerador de Executável (.exe)
echo ====================================================================
echo.

cd /d "%~dp0"

echo [1/3] Verificando e instalando PyInstaller e Pillow...
python -m pip install --upgrade pip
python -m pip install pillow pyinstaller

echo.
echo [2/3] Escolha o formato de compilação:
echo   1. Arquivo único (.exe Standalone — ideal para compartilhar direto no GitHub)
echo   2. Pasta portátil (Inicialização mais rápida, ideal para criar instalador)
set /p OPTION="Digite a opção [1 ou 2, padrão 1]: "

if "%OPTION%"=="2" (
    echo.
    echo [3/3] Compilando em pasta portátil...
    pyinstaller --noconfirm --clean ^
        --name "WisperFlow" ^
        --windowed ^
        --icon "assets\icon.ico" ^
        --add-data "assets;assets" ^
        --add-data "config.example.json;." ^
        --hidden-import "PIL" ^
        --hidden-import "PIL.Image" ^
        --hidden-import "PIL.ImageTk" ^
        app.py
) else (
    echo.
    echo [3/3] Compilando em arquivo único standalone...
    pyinstaller --noconfirm --clean --onefile ^
        --name "WisperFlow" ^
        --windowed ^
        --icon "assets\icon.ico" ^
        --add-data "assets;assets" ^
        --add-data "config.example.json;." ^
        --hidden-import "PIL" ^
        --hidden-import "PIL.Image" ^
        --hidden-import "PIL.ImageTk" ^
        app.py
)

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ====================================================================
    echo  SUCESSO! O executável foi gerado na pasta:
    echo  %~dp0dist\
    echo ====================================================================
) else (
    echo.
    echo [ERRO] Ocorreu uma falha durante a compilação.
)
echo.
pause
