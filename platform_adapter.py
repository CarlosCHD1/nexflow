"""
NexFlow — Adaptador de Plataforma Multiplataforma (Windows, macOS, Linux)
Permite que o NexFlow execute com 100% de estabilidade e funcionalidade nativa
em qualquer sistema operacional.
"""

import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

_SYSTEM = platform.system()


def is_windows() -> bool:
    return _SYSTEM == "Windows"


def is_macos() -> bool:
    return _SYSTEM == "Darwin"


def is_linux() -> bool:
    return _SYSTEM == "Linux"


def get_platform_name() -> str:
    if is_windows():
        return "Windows"
    elif is_macos():
        return "macOS"
    elif is_linux():
        return "Linux"
    return _SYSTEM


# --- INJEÇÃO DE TEXTO NO CURSOR ---

def inject_text_cross_platform(text: str, target_hwnd: int = 0) -> bool:
    """Injeta texto diretamente no campo de texto ativo onde o cursor do usuário está."""
    if not text:
        return False

    if is_windows():
        try:
            from win32_utils import inject_text_at_cursor
            return inject_text_at_cursor(text, target_hwnd=target_hwnd)
        except Exception as e:
            print(f"[Platform] Erro na injeção Windows: {e}")

    elif is_macos():
        try:
            # 1. Copia o texto para a área de transferência do macOS (pbcopy)
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(text.encode("utf-8"))

            # 2. Envia Cmd + V via AppleScript nativo (System Events)
            script = 'tell application "System Events" to keystroke "v" using command down'
            subprocess.run(["osascript", "-e", script], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"[Platform] Erro na injeção macOS: {e}")

    elif is_linux():
        try:
            # Tenta Wayland (wl-copy) ou X11 (xclip)
            copied = False
            for copy_tool in [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]:
                try:
                    p = subprocess.Popen(copy_tool, stdin=subprocess.PIPE)
                    p.communicate(text.encode("utf-8"))
                    copied = True
                    break
                except FileNotFoundError:
                    continue

            if not copied:
                return False

            # Envia Ctrl + V via xdotool ou ydotool
            for paste_cmd in [["xdotool", "key", "--clearmodifiers", "ctrl+v"], ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]]:
                try:
                    subprocess.run(paste_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True
                except Exception:
                    continue
        except Exception as e:
            print(f"[Platform] Erro na injeção Linux: {e}")

    return False


# --- REPRODUÇÃO DE SONS SUAVES ---

def play_audio_cue_cross_platform(wav_bytes: bytes, cue_name: str = "done") -> None:
    """Reproduz um som de feedback de forma não-bloqueante no sistema operacional ativo."""
    if not wav_bytes:
        return

    if is_windows():
        try:
            import winsound
            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return
        except Exception:
            pass

    elif is_macos():
        try:
            # Grava em arquivo temporário e toca com o comando nativo afplay
            temp_path = os.path.join(tempfile.gettempdir(), f"nexflow_cue_{cue_name}.wav")
            with open(temp_path, "wb") as f:
                f.write(wav_bytes)
            subprocess.Popen(["afplay", temp_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass

    elif is_linux():
        try:
            temp_path = os.path.join(tempfile.gettempdir(), f"nexflow_cue_{cue_name}.wav")
            with open(temp_path, "wb") as f:
                f.write(wav_bytes)
            for player in ["paplay", "pw-cat -p", "aplay"]:
                try:
                    cmd = player.split() + [temp_path]
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except FileNotFoundError:
                    continue
        except Exception:
            pass


# --- ABRIR PASTA NO GERENCIADOR DE ARQUIVOS NATIVO ---

def open_folder_cross_platform(folder_path: str) -> None:
    """Abre uma pasta no Windows Explorer, macOS Finder ou Linux File Manager."""
    folder = str(folder_path)
    os.makedirs(folder, exist_ok=True)

    if is_windows():
        try:
            os.startfile(folder)
            return
        except Exception:
            subprocess.Popen(["explorer.exe", folder])
    elif is_macos():
        subprocess.Popen(["open", folder])
    elif is_linux():
        subprocess.Popen(["xdg-open", folder])


# --- CONFIGURAR INICIALIZAÇÃO COM O SISTEMA ---

def configure_startup_cross_platform(enable: bool, app_path: Optional[str] = None) -> bool:
    """Ativa ou desativa a inicialização automática do NexFlow ao ligar o computador."""
    if app_path is None:
        if getattr(sys, "frozen", False):
            app_path = sys.executable
        else:
            app_path = str(Path(__file__).resolve().parent / "app.py")

    if is_windows():
        try:
            from win32_utils import configure_windows_startup
            return configure_windows_startup(enable)
        except Exception as e:
            print(f"[Startup] Erro Windows: {e}")
            return False

    elif is_macos():
        launch_dir = Path.home() / "Library" / "LaunchAgents"
        plist_path = launch_dir / "com.nexflow.app.plist"
        if not enable:
            if plist_path.exists():
                try:
                    subprocess.run(["launchctl", "unload", str(plist_path)], stderr=subprocess.DEVNULL)
                    plist_path.unlink()
                except Exception:
                    pass
            return True
        try:
            launch_dir.mkdir(parents=True, exist_ok=True)
            python_exec = sys.executable
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nexflow.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_exec}</string>
        <string>{app_path}</string>
        <string>--minimized</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"""
            plist_path.write_text(plist_content, encoding="utf-8")
            subprocess.run(["launchctl", "load", str(plist_path)], stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"[Startup] Erro macOS: {e}")
            return False

    elif is_linux():
        autostart_dir = Path.home() / ".config" / "autostart"
        desktop_file = autostart_dir / "nexflow.desktop"
        if not enable:
            if desktop_file.exists():
                desktop_file.unlink()
            return True
        try:
            autostart_dir.mkdir(parents=True, exist_ok=True)
            desktop_content = f"""[Desktop Entry]
Type=Application
Exec={sys.executable} "{app_path}" --minimized
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=NexFlow
Comment=Ditado Inteligente por Voz com IA
"""
            desktop_file.write_text(desktop_content, encoding="utf-8")
            return True
        except Exception as e:
            print(f"[Startup] Erro Linux: {e}")
            return False

    return False


# --- ESTILIZAÇÃO E TRANSPARÊNCIA DA PÍLULA FLUTUANTE ---

def apply_pill_window_styles(tk_window, transparent_key: str = "#010101") -> None:
    """Aplica propriedades de janela não-bloqueante e transparência de acordo com a plataforma."""
    try:
        tk_window.attributes("-topmost", True)
    except Exception:
        pass

    if is_windows():
        try:
            tk_window.configure(bg=transparent_key)
            tk_window.wm_attributes("-transparentcolor", transparent_key)
        except Exception:
            pass
        try:
            from win32_utils import make_window_non_activating
            hwnd = int(tk_window.wm_frame(), 16) if tk_window.wm_frame() != "0x0" else tk_window.winfo_id()
            make_window_non_activating(hwnd)
            make_window_non_activating(tk_window.winfo_id())
        except Exception:
            pass

    elif is_macos():
        # No macOS, -transparentcolor não é suportado no Tkinter. Usa-se -alpha e fundo escuro.
        try:
            tk_window.attributes("-alpha", 0.98)
            tk_window.configure(bg="#0B0C10")
        except Exception:
            pass

    elif is_linux():
        try:
            tk_window.attributes("-alpha", 0.96)
            tk_window.configure(bg="#0B0C10")
        except Exception:
            pass
