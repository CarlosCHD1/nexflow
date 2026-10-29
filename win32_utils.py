import ctypes
from ctypes import wintypes
import io
import math
import struct
import threading
import time
import wave
import winsound
from typing import Callable, List, Optional, Tuple, Dict

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Constantes Win32
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_UNICODE = 0x0004

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_PAUSE = 0x13
VK_CAPITAL = 0x14  # CapsLock
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_V = 0x56

# Mapa de nomes amigáveis de teclas Virtual-Key
VK_NAMES: Dict[int, str] = {
    0x08: "Backspace",
    0x09: "Tab",
    0x10: "Shift",
    0x11: "Ctrl",
    0x12: "Alt",
    0x13: "Pause",
    0x14: "CapsLock",
    0x20: "Espaço",
    0x21: "PageUp",
    0x22: "PageDown",
    0x23: "End",
    0x24: "Home",
    0x2D: "Insert",
    0x2E: "Delete",
    0x5B: "Win",
    0x5C: "Win Dir",
    0xA0: "Shift Esq",
    0xA1: "Shift Dir",
    0xA2: "Ctrl Esq",
    0xA3: "Ctrl Dir",
    0xA4: "Alt Esq",
    0xA5: "Alt Dir",
    0xC0: "' (Aspas)",
    0xBA: "Ç",
    0xBB: "=",
    0xBC: ",",
    0xBD: "-",
    0xBE: ".",
    0xBF: ";",
    0xDB: "´",
    0xDC: "\\",
    0xDD: "[",
    0xDE: "~",
}
# F1..F12
for _f in range(1, 13):
    VK_NAMES[0x6F + _f] = f"F{_f}"
# A..Z
for _c in range(ord("A"), ord("Z") + 1):
    VK_NAMES[_c] = chr(_c)
# 0..9
for _n in range(ord("0"), ord("9") + 1):
    VK_NAMES[_n] = chr(_n)

# Presets rápidos de atalho para o menu
HOTKEY_PRESETS: List[Dict[str, any]] = [
    {"label": "CapsLock (1 Tecla — Ctrl+Caps ativa/desativa)", "codes": [0x14]},
    {"label": "Ctrl Direito (1 Tecla)", "codes": [0xA3]},
    {"label": "Alt Direito (1 Tecla)", "codes": [0xA5]},
    {"label": "F8 (1 Tecla dedicada)", "codes": [0x77]},
    {"label": "F9 (1 Tecla dedicada)", "codes": [0x78]},
    {"label": "Insert (1 Tecla)", "codes": [0x2D]},
    {"label": "Pause (1 Tecla)", "codes": [0x13]},
    {"label": "Ctrl + Win (Padrão 2 Teclas)", "codes": [0x11, 0x5B]},
    {"label": "Ctrl + Espaço (2 Teclas)", "codes": [0x11, 0x20]},
    {"label": "Alt + Espaço (2 Teclas)", "codes": [0x12, 0x20]},
]

# Configuração correta de tipos 64-bit para Clipboard e Janelas
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL

ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTunion),
    ]


def make_window_non_activating(hwnd: int) -> None:
    """
    Configura uma janela Tkinter (ex: pílula flutuante) para NUNCA roubar o foco
    do aplicativo onde o usuário está digitando e não aparecer no Alt+Tab.
    """
    try:
        get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        style = get_long(hwnd, GWL_EXSTYLE)
        new_style = style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
        set_long(hwnd, GWL_EXSTYLE, new_style)
    except Exception as e:
        print(f"[Win32] Aviso ao configurar janela sem foco: {e}")


def get_clipboard_text() -> Optional[str]:
    """Lê o texto atual da área de transferência do Windows."""
    text = None
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                h_data = user32.GetClipboardData(CF_UNICODETEXT)
                if h_data:
                    ptr = kernel32.GlobalLock(h_data)
                    if ptr:
                        try:
                            text = ctypes.wstring_at(ptr)
                        finally:
                            kernel32.GlobalUnlock(h_data)
            finally:
                user32.CloseClipboard()
            break
        time.sleep(0.015)
    return text


def set_clipboard_text(text: str) -> bool:
    """Define o texto Unicode na área de transferência do Windows com segurança 64-bit."""
    encoded = text.encode("utf-16-le") + b"\x00\x00"
    for _ in range(8):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
                if not h_mem:
                    return False
                ptr = kernel32.GlobalLock(h_mem)
                if not ptr:
                    kernel32.GlobalFree(h_mem)
                    return False
                ctypes.memmove(ptr, encoded, len(encoded))
                kernel32.GlobalUnlock(h_mem)
                res = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                return bool(res)
            finally:
                user32.CloseClipboard()
        time.sleep(0.015)
    return False


def _send_key_event(vk: int, key_up: bool = False) -> None:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki.wVk = vk
    inp.union.ki.wScan = user32.MapVirtualKeyW(vk, 0)
    inp.union.ki.dwFlags = KEYEVENTF_KEYUP if key_up else 0
    inp.union.ki.time = 0
    inp.union.ki.dwExtraInfo = 0
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _release_active_modifiers() -> None:
    """
    Aguarda brevemente o usuário soltar teclas modificadoras do atalho (Win, Alt, Shift, Ctrl)
    e garante que nenhuma tecla modificadora fique presa antes do Ctrl+V.
    """
    mod_keys = [
        VK_LWIN,
        VK_RWIN,
        VK_MENU,
        VK_LMENU,
        VK_RMENU,
        VK_SHIFT,
        VK_LSHIFT,
        VK_RSHIFT,
        VK_CONTROL,
        VK_LCONTROL,
        VK_RCONTROL,
    ]
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 0.35:
        still_down = any((user32.GetAsyncKeyState(k) & 0x8000) != 0 for k in mod_keys)
        if not still_down:
            break
        time.sleep(0.015)

    # Libera sinteticamente caso alguma tecla modificadora ainda esteja registrada no estado da janela
    for k in [VK_LWIN, VK_RWIN, VK_LMENU, VK_RMENU, VK_LSHIFT, VK_RSHIFT]:
        if (user32.GetAsyncKeyState(k) & 0x8000) != 0:
            _send_key_event(k, key_up=True)


def inject_text_unicode_direct(text: str) -> bool:
    """
    Injeta caracteres Unicode diretamente via SendInput (KEYEVENTF_UNICODE)
    sem precisar da área de transferência.
    """
    if not text:
        return False
    _release_active_modifiers()
    time.sleep(0.02)
    utf16_units = [
        int.from_bytes( text_char.encode("utf-16-le")[i : i + 2], "little" )
        for text_char in text
        for i in range(0, len(text_char.encode("utf-16-le")), 2)
    ]
    n = len(utf16_units) * 2
    inputs = (INPUT * n)()
    idx = 0
    for code_unit in utf16_units:
        # Key down
        inputs[idx].type = INPUT_KEYBOARD
        inputs[idx].union.ki.wVk = 0
        inputs[idx].union.ki.wScan = code_unit
        inputs[idx].union.ki.dwFlags = KEYEVENTF_UNICODE
        idx += 1
        # Key up
        inputs[idx].type = INPUT_KEYBOARD
        inputs[idx].union.ki.wVk = 0
        inputs[idx].union.ki.wScan = code_unit
        inputs[idx].union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        idx += 1
    sent = user32.SendInput(n, ctypes.byref(inputs), ctypes.sizeof(INPUT))
    return sent == n


def get_foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0)


def inject_text_at_cursor(
    text: str,
    restore_clipboard: bool = False,
    target_hwnd: Optional[int] = None,
) -> bool:
    """
    Injeta o texto transcrito diretamente onde o cursor de texto do usuário está.
    Usa Clipboard Unicode + Ctrl+V via VK_CONTROL (0x11) com cadência real de teclado
    (compatível com Antigravity, VS Code, Pesquisa do Windows, Chrome, WhatsApp, Word, etc.).
    """
    if not text:
        return False

    # Se a janela alvo foi salva e o foco saiu dela por acidente, restaura o foco
    if target_hwnd:
        cur_fg = user32.GetForegroundWindow()
        if cur_fg != target_hwnd:
            try:
                user32.SetForegroundWindow(target_hwnd)
                time.sleep(0.03)
            except Exception:
                pass

    prev_clip = get_clipboard_text() if restore_clipboard else None

    if not set_clipboard_text(text):
        return inject_text_unicode_direct(text)

    _release_active_modifiers()
    time.sleep(0.03)

    # Envia Ctrl (0x11) + V (0x56) com intervalo de 20ms para que apps Electron/VS Code/Windows Search reconheçam 100%
    _send_key_event(VK_CONTROL, key_up=False)
    time.sleep(0.02)
    _send_key_event(VK_V, key_up=False)
    time.sleep(0.02)
    _send_key_event(VK_V, key_up=True)
    time.sleep(0.02)
    _send_key_event(VK_CONTROL, key_up=True)

    if restore_clipboard and prev_clip is not None:
        def _restore():
            time.sleep(0.35)
            set_clipboard_text(prev_clip)
        threading.Thread(target=_restore, daemon=True).start()

    return True


# Estado de teclas interceptadas pelo hook de baixo nível (ex: CapsLock bloqueado p/ não ativar MAIÚSCULAS)
_LL_INTERCEPTED_DOWN: Dict[int, bool] = {}

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
LLKHF_INJECTED = 0x00000010


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)
user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL


def ensure_capslock_off() -> None:
    """Se a luz do CapsLock estiver acesa (MAIÚSCULAS ativas), desliga automaticamente."""
    try:
        if (user32.GetKeyState(VK_CAPITAL) & 0x0001) != 0:
            _send_key_event(VK_CAPITAL, key_up=False)
            _send_key_event(VK_CAPITAL, key_up=True)
    except Exception:
        pass


def configure_windows_startup(enable: bool = True) -> bool:
    """
    Configura ou remove a inicialização automática com o Windows na pasta Startup do usuário.
    Assim que o computador ligar, o Wispr Flow Free inicia silenciosamente em segundo plano.
    """
    try:
        import os
        from pathlib import Path

        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return False
        startup_dir = (
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
        )
        vbs_path = startup_dir / "WisprFlow_Free_AutoStart.vbs"
        app_dir = Path(__file__).resolve().parent
        app_py = app_dir / "app.py"

        if enable:
            startup_dir.mkdir(parents=True, exist_ok=True)
            pyw = r"C:\Python314\pythonw.exe"
            if not Path(pyw).exists():
                import sys
                pyw = sys.executable.replace("python.exe", "pythonw.exe")
            vbs_content = (
                'Set WshShell = CreateObject("WScript.Shell")\r\n'
                f'WshShell.CurrentDirectory = "{app_dir}"\r\n'
                f'WshShell.Run """{pyw}"" ""{app_py}"" --minimized", 0, False\r\n'
            )
            with open(vbs_path, "w", encoding="mbcs", errors="replace") as f:
                f.write(vbs_content)
            return True
        else:
            if vbs_path.exists():
                vbs_path.unlink()
            return True
    except Exception as e:
        print(f"[Startup] Erro ao configurar inicialização com o Windows: {e}")
        return False


def is_key_pressed(vk: int) -> bool:
    """Verifica se uma tecla Virtual-Key está pressionada no momento."""
    if _LL_INTERCEPTED_DOWN.get(vk, False):
        return True
    if vk == VK_CONTROL:
        return bool(
            (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
            or (user32.GetAsyncKeyState(VK_LCONTROL) & 0x8000)
            or (user32.GetAsyncKeyState(VK_RCONTROL) & 0x8000)
        )
    if vk == VK_SHIFT:
        return bool(
            (user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
            or (user32.GetAsyncKeyState(VK_LSHIFT) & 0x8000)
            or (user32.GetAsyncKeyState(VK_RSHIFT) & 0x8000)
        )
    if vk == VK_MENU:
        return bool(
            (user32.GetAsyncKeyState(VK_MENU) & 0x8000)
            or (user32.GetAsyncKeyState(VK_LMENU) & 0x8000)
            or (user32.GetAsyncKeyState(VK_RMENU) & 0x8000)
        )
    if vk == VK_LWIN:
        return bool(
            (user32.GetAsyncKeyState(VK_LWIN) & 0x8000)
            or (user32.GetAsyncKeyState(VK_RWIN) & 0x8000)
        )
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def format_hotkey_label(codes: List[int]) -> str:
    return " + ".join(VK_NAMES.get(c, f"Tecla({hex(c)})") for c in codes)


# Sons suaves sintetizados em memória (estilo Wispr Flow)
_SOUND_CACHE: Dict[str, bytes] = {}


def _build_chime_wav(freqs: List[Tuple[float, float, float]]) -> bytes:
    """Gera um efeito sonoro sutil e agradável em WAV na memória."""
    sr = 24000
    all_samples = []
    for freq, dur, vol in freqs:
        n = int(sr * dur)
        for i in range(n):
            t = i / sr
            attack = min(1.0, i / (sr * 0.008))
            decay = math.exp(-t * (18.0 / max(0.05, dur)))
            sample = math.sin(2.0 * math.pi * freq * t) * vol * attack * decay
            all_samples.append(int(max(-1.0, min(1.0, sample)) * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{len(all_samples)}h", *all_samples))
    return buf.getvalue()


def play_sound_cue(cue_name: str, enabled: bool = True) -> None:
    if not enabled:
        return
    try:
        if not _SOUND_CACHE:
            _SOUND_CACHE["start"] = _build_chime_wav([(520.0, 0.055, 0.16), (780.0, 0.085, 0.20)])
            _SOUND_CACHE["stop"] = _build_chime_wav([(740.0, 0.055, 0.16), (560.0, 0.09, 0.15)])
            _SOUND_CACHE["done"] = _build_chime_wav([(660.0, 0.045, 0.12), (990.0, 0.08, 0.15)])
            _SOUND_CACHE["cancel"] = _build_chime_wav([(360.0, 0.07, 0.16), (260.0, 0.11, 0.14)])
            _SOUND_CACHE["enable_tool"] = _build_chime_wav([(440.0, 0.05, 0.15), (660.0, 0.05, 0.17), (880.0, 0.09, 0.20)])
            _SOUND_CACHE["disable_tool"] = _build_chime_wav([(780.0, 0.05, 0.15), (520.0, 0.05, 0.15), (340.0, 0.10, 0.16)])
        wav_data = _SOUND_CACHE.get(cue_name)
        if wav_data:
            winsound.PlaySound(
                wav_data, winsound.SND_MEMORY | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            )
    except Exception:
        pass


class GlobalHotkeyListener:
    """
    Monitor global de atalho de teclado em segundo plano + Hook de baixo nível (WH_KEYBOARD_LL):
    - Quando a ferramenta está ATIVA:
      - Apertar CapsLock inicia/para a gravação de voz SEM ligar as LETRAS MAIÚSCULAS do teclado!
      - Apertar Ctrl + CapsLock DESATIVA a ferramenta (liberando o CapsLock normal do Windows).
    - Quando a ferramenta está DESATIVADA:
      - O CapsLock funciona 100% normal no Windows (liga/desliga maiúsculas).
      - Apertar Ctrl + CapsLock ATIVA novamente a ferramenta de voz!
    """

    SMART_HOLD_THRESHOLD_S = 0.32

    def __init__(
        self,
        get_hotkey_codes: Callable[[], List[int]],
        get_hotkey_mode: Callable[[], str],
        on_start_recording: Callable[[str], None],
        on_stop_recording: Callable[[], None],
        on_cancel_recording: Callable[[], None],
        on_toggle_locked: Optional[Callable[[], None]] = None,
        on_master_toggle: Optional[Callable[[bool], None]] = None,
        on_toggle_audio_recording: Optional[Callable[[], None]] = None,
        initial_tool_enabled: bool = True,
    ):
        self.get_hotkey_codes = get_hotkey_codes
        self.get_hotkey_mode = get_hotkey_mode
        self.on_start_recording = on_start_recording
        self.on_stop_recording = on_stop_recording
        self.on_cancel_recording = on_cancel_recording
        self.on_toggle_locked = on_toggle_locked
        self.on_master_toggle = on_master_toggle
        self.on_toggle_audio_recording = on_toggle_audio_recording

        self.tool_enabled = initial_tool_enabled
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._hook_thread: Optional[threading.Thread] = None
        self._hook_handle = None
        self._hook_proc_ref = None
        self._ctrl_caps_latched = False
        self._alt_a_latched = False
        self.is_recording_active = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        if self.tool_enabled and self.get_hotkey_codes() == [VK_CAPITAL]:
            ensure_capslock_off()
        self._hook_thread = threading.Thread(target=self._run_ll_keyboard_hook, daemon=True)
        self._hook_thread.start()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._hook_handle:
            try:
                user32.UnhookWindowsHookEx(self._hook_handle)
            except Exception:
                pass
            self._hook_handle = None

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        if paused:
            _LL_INTERCEPTED_DOWN.clear()

    def set_tool_enabled(self, enabled: bool, notify: bool = True) -> None:
        self.tool_enabled = enabled
        _LL_INTERCEPTED_DOWN.clear()
        if not enabled and self.is_recording_active:
            self.is_recording_active = False
            self.on_cancel_recording()
        if enabled and self.get_hotkey_codes() == [VK_CAPITAL]:
            ensure_capslock_off()
        if notify and self.on_master_toggle:
            self.on_master_toggle(enabled)

    def notify_recording_stopped_externally(self) -> None:
        self.is_recording_active = False

    def _run_ll_keyboard_hook(self) -> None:
        """
        Hook global WH_KEYBOARD_LL para:
        1) Detectar Ctrl + CapsLock e alternar Ativar / Desativar a ferramenta.
        2) Quando a ferramenta está ATIVA e o atalho é CapsLock, impedir que o CapsLock
           ligue as LETRAS MAIÚSCULAS enquanto o usuário fala!
        """
        def _low_level_proc(nCode: int, wParam: int, lParam: int) -> int:
            if nCode >= 0 and not self._paused:
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                # Ignora eventos sintéticos injetados pelo próprio app
                if not (kb.flags & LLKHF_INJECTED):
                    vk = kb.vkCode
                    is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    is_up = wParam in (WM_KEYUP, WM_SYSKEYUP)

                    if vk == VK_CAPITAL:
                        ctrl_down = bool(
                            (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                            or (user32.GetAsyncKeyState(VK_LCONTROL) & 0x8000)
                            or (user32.GetAsyncKeyState(VK_RCONTROL) & 0x8000)
                        )
                        # Caso 1: Usuário pressionou Ctrl + CapsLock -> Ativa / Desativa a ferramenta!
                        if ctrl_down:
                            if is_down and not self._ctrl_caps_latched:
                                self._ctrl_caps_latched = True
                                _LL_INTERCEPTED_DOWN[VK_CAPITAL] = False
                                new_state = not self.tool_enabled
                                threading.Thread(
                                    target=self.set_tool_enabled,
                                    args=(new_state, True),
                                    daemon=True,
                                ).start()
                            elif is_up:
                                self._ctrl_caps_latched = False
                                _LL_INTERCEPTED_DOWN[VK_CAPITAL] = False
                            return 1  # Engole o evento para não mexer no CapsLock do Windows

                        self._ctrl_caps_latched = False

                        # Caso 2: Ferramenta ATIVA e CapsLock é a tecla de falar
                        if self.tool_enabled and self.get_hotkey_codes() == [VK_CAPITAL]:
                            if is_down:
                                _LL_INTERCEPTED_DOWN[VK_CAPITAL] = True
                            elif is_up:
                                _LL_INTERCEPTED_DOWN[VK_CAPITAL] = False
                            return 1  # Engole o CapsLock para não ativar MAIÚSCULAS enquanto grava!
                        else:
                            # Ferramenta DESATIVADA -> CapsLock funciona normalmente no Windows!
                            _LL_INTERCEPTED_DOWN[VK_CAPITAL] = False

                    # Caso 3: Alt + A para o Gravador de Áudio Dedicado (Salva arquivo em Vídeos/Conteúdos/áudios)
                    if vk == 0x41:  # Tecla 'A'
                        alt_down = bool(
                            (user32.GetAsyncKeyState(VK_MENU) & 0x8000)
                            or (user32.GetAsyncKeyState(VK_LMENU) & 0x8000)
                            or (user32.GetAsyncKeyState(VK_RMENU) & 0x8000)
                        )
                        if alt_down:
                            if is_down and not self._alt_a_latched:
                                self._alt_a_latched = True
                                if self.on_toggle_audio_recording:
                                    threading.Thread(
                                        target=self.on_toggle_audio_recording,
                                        daemon=True,
                                    ).start()
                            elif is_up:
                                self._alt_a_latched = False
                            return 1  # Engole o Alt+A para não abrir atalhos no app em foco

            return user32.CallNextHookEx(self._hook_handle, nCode, wParam, lParam)

        self._hook_proc_ref = HOOKPROC(_low_level_proc)
        self._hook_handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_proc_ref, None, 0
        )

        msg = wintypes.MSG()
        while self._running:
            res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _are_hotkey_codes_down(self, codes: List[int]) -> bool:
        if not codes:
            return False
        # Se o atalho for apenas CapsLock, garante que Ctrl não está pressionado junto
        if codes == [VK_CAPITAL] and is_key_pressed(VK_CONTROL):
            return False
        return all(is_key_pressed(c) for c in codes)

    def _poll_loop(self) -> None:
        was_combo_down = False
        was_alt_a_down = False
        press_start_time = 0.0
        active_submode = "hold"  # "hold" ou "toggle_latched"
        notified_hold = False

        while self._running:
            if self._paused or not self.tool_enabled:
                was_combo_down = False
                was_alt_a_down = False
                time.sleep(0.03)
                continue

            # Fallback de polling para Alt + A (Gravador de Áudio)
            alt_a_down = is_key_pressed(VK_MENU) and is_key_pressed(0x41)
            if alt_a_down and not was_alt_a_down:
                was_alt_a_down = True
                if not self._alt_a_latched and self.on_toggle_audio_recording:
                    self._alt_a_latched = True
                    threading.Thread(target=self.on_toggle_audio_recording, daemon=True).start()
            elif not alt_a_down and was_alt_a_down:
                was_alt_a_down = False
                self._alt_a_latched = False

            codes = self.get_hotkey_codes()
            mode = self.get_hotkey_mode()  # "smart", "hold", "toggle"
            combo_down = self._are_hotkey_codes_down(codes)

            # Se estiver gravando e apertar ESC, cancela na hora
            if self.is_recording_active and is_key_pressed(VK_ESCAPE):
                self.is_recording_active = False
                was_combo_down = False
                self.on_cancel_recording()
                while is_key_pressed(VK_ESCAPE) and self._running:
                    time.sleep(0.02)
                continue

            now = time.perf_counter()

            # Transição: Solto -> Pressionado
            if combo_down and not was_combo_down:
                press_start_time = now
                notified_hold = False
                # Evita que o Menu Iniciar do Windows abra ao soltar a tecla Win
                if VK_LWIN in codes or VK_RWIN in codes:
                    _send_key_event(0xFF, key_up=True)

                if not self.is_recording_active:
                    self.is_recording_active = True
                    if mode == "toggle":
                        active_submode = "toggle_latched"
                        self.on_start_recording("toggle")
                    elif mode == "hold":
                        active_submode = "hold"
                        self.on_start_recording("hold")
                    else:  # "smart"
                        active_submode = "smart_pending"
                        self.on_start_recording("smart")
                else:
                    # Já estava gravando (em modo toggle/latched) -> parar gravação!
                    self.is_recording_active = False
                    self.on_stop_recording()
                    while self._are_hotkey_codes_down(codes) and self._running:
                        time.sleep(0.02)
                    was_combo_down = False
                    continue

            # Enquanto mantém pressionado no modo "smart"
            elif combo_down and was_combo_down and self.is_recording_active:
                if mode == "smart" and active_submode == "smart_pending":
                    if (now - press_start_time) >= self.SMART_HOLD_THRESHOLD_S and not notified_hold:
                        notified_hold = True
                        active_submode = "hold"

            # Transição: Pressionado -> Solto
            elif not combo_down and was_combo_down:
                if self.is_recording_active:
                    held_duration = now - press_start_time
                    if mode == "hold":
                        self.is_recording_active = False
                        self.on_stop_recording()
                    elif mode == "smart":
                        if held_duration >= self.SMART_HOLD_THRESHOLD_S:
                            # Segurou para falar -> soltou, transcreve!
                            self.is_recording_active = False
                            self.on_stop_recording()
                        else:
                            # Toque rápido (< 320ms) -> Trava no modo mãos-livres (Toggle)!
                            active_submode = "toggle_latched"
                            if self.on_toggle_locked:
                                self.on_toggle_locked()

            was_combo_down = combo_down
            time.sleep(0.012)


def capture_custom_hotkey(
    on_complete: Callable[[List[int], str], None],
    on_cancel: Callable[[], None],
    timeout_s: float = 8.0,
) -> None:
    """
    Captura interativamente uma tecla única ou combinação pressionada pelo usuário.
    Roda em uma thread separada.
    """
    specific_modifiers = [
        VK_LCONTROL,
        VK_RCONTROL,
        VK_LMENU,
        VK_RMENU,
        VK_LSHIFT,
        VK_RSHIFT,
        VK_LWIN,
        VK_RWIN,
    ]
    other_vks = (
        [
            VK_CAPITAL,
            VK_SPACE,
            VK_TAB,
            VK_PAUSE,
            0x2D,  # Insert
            0x2E,  # Delete
            0x24,  # Home
            0x23,  # End
            0x21,  # PageUp
            0x22,  # PageDown
            0xC0,  # Aspas '
        ]
        + list(range(0x70, 0x7C))  # F1..F12
        + list(range(ord("A"), ord("Z") + 1))
        + list(range(ord("0"), ord("9") + 1))
    )
    all_vks = specific_modifiers + other_vks

    def _worker():
        # Primeiro aguarda soltar qualquer tecla já pressionada
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 1.5:
            if not any((user32.GetAsyncKeyState(k) & 0x8000) != 0 for k in all_vks):
                break
            time.sleep(0.02)

        peak_keys: List[int] = []
        started = False
        start_wait = time.perf_counter()

        while time.perf_counter() - start_wait < timeout_s:
            if is_key_pressed(VK_ESCAPE):
                on_cancel()
                return

            currently_down: List[int] = [
                vk for vk in all_vks if (user32.GetAsyncKeyState(vk) & 0x8000) != 0
            ]

            if currently_down:
                started = True
                for k in currently_down:
                    if k not in peak_keys and len(peak_keys) < 3:
                        peak_keys.append(k)
            elif started and peak_keys:
                # Se for combinação de 2+ teclas, converte Ctrl/Alt/Shift Esq para o código genérico
                if len(peak_keys) > 1:
                    norm_map = {
                        VK_LCONTROL: VK_CONTROL,
                        VK_LMENU: VK_MENU,
                        VK_LSHIFT: VK_SHIFT,
                    }
                    peak_keys = [norm_map.get(k, k) for k in peak_keys]
                label = format_hotkey_label(peak_keys)
                on_complete(peak_keys, label)
                return

            time.sleep(0.015)

        on_cancel()

    threading.Thread(target=_worker, daemon=True).start()
