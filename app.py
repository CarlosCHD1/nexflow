"""
NexFlow — Ditado Inteligente por Voz com IA & Gravador Studio Broadcast
Aplicativo comercial premium para Windows, macOS e Linux.
"""

import ctypes
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from pathlib import Path
from typing import Dict, Any, List, Optional

from PIL import Image, ImageTk

from config import (
    APP_NAME,
    APP_VERSION,
    APP_TAGLINE,
    load_config,
    save_config,
    load_history,
    add_history_entry,
    get_resource_path,
    get_audios_dir,
    add_audio_recording_entry,
    load_audio_history,
)
from audio_recorder import AudioRecorder, list_microphones
from transcriber import HybridTranscriber, LOCAL_MODELS_CATALOG
from win32_utils import (
    GlobalHotkeyListener,
    HOTKEY_PRESETS,
    capture_custom_hotkey,
    get_foreground_window,
    play_sound_cue,
    set_clipboard_text,
    IS_WINDOWS,
)
from floating_pill import FloatingPillOverlay
from platform_adapter import (
    is_windows,
    is_macos,
    is_linux,
    get_platform_name,
    inject_text_cross_platform,
    open_folder_cross_platform,
    configure_startup_cross_platform,
)
from licensing import (
    is_activated,
    get_license_info,
    activate_license,
    deactivate_license,
    get_machine_fingerprint,
)

# Ativa DPI Awareness no Windows para renderização nítida
if is_windows():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class NexFlowApp:
    # Paleta Dark Obsidian inspirada no ecossistema Apple Pro e Wispr Flow
    BG_MAIN = "#0A0B10"
    BG_TOPBAR = "#0F111C"
    BG_CARD = "#141726"
    BG_CARD_SUBTLE = "#191D30"
    BG_INPUT = "#1E2238"
    BORDER_COL = "#252B44"
    BORDER_ACTIVE = "#8B5CF6"
    ACCENT = "#8B5CF6"
    ACCENT_HOVER = "#7C3AED"
    ACCENT_GLOW = "#A78BFA"
    TEXT_PRIMARY = "#FFFFFF"
    TEXT_SECONDARY = "#94A3B8"
    TEXT_MUTED = "#64748B"
    SUCCESS = "#10B981"
    STUDIO_RED = "#F43F5E"
    GOLD = "#F59E0B"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.config: Dict[str, Any] = load_config()
        self.history: List[Dict[str, Any]] = load_history()
        self.audio_history: List[Dict[str, Any]] = load_audio_history()
        self.mics = list_microphones()
        self._is_recording_audio = False
        self._audio_rec_folder = get_audios_dir()

        # Garante a inicialização com o sistema
        configure_startup_cross_platform(bool(self.config.get("start_with_windows", True)))

        self.recorder = AudioRecorder(on_auto_silence_stop=self._trigger_stop_from_ui)
        self.transcriber = HybridTranscriber(on_status_change=self._on_transcriber_status)
        self._is_processing = False
        self._last_latency_s = 0.0
        self._target_hwnd: int = 0
        self._active_tab = "dictation"

        self._setup_main_window()
        self._build_ui()

        # Cria a Pílula Flutuante Animada
        self.pill = FloatingPillOverlay(
            root=self.root,
            get_waveform_bars=lambda: self.recorder.waveform_bars,
            get_recording_duration=self.recorder.get_duration,
            on_open_settings=self.show_main_window,
            on_stop_clicked=self._trigger_stop_from_ui,
            on_cancel_clicked=self._trigger_cancel_from_ui,
            on_position_changed=self._on_pill_moved,
            initial_x=self.config.get("pill_x"),
            initial_y=self.config.get("pill_y"),
            hotkey_label=self.config.get("hotkey_label", "CapsLock"),
            visibility_mode=self.config.get("pill_visibility", "always"),
        )
        self.pill.update_preferences(
            hotkey_label=self.config.get("hotkey_label", "CapsLock"),
            visibility_mode=self.config.get("pill_visibility", "always"),
            tool_enabled=bool(self.config.get("tool_enabled", True)),
        )

        # Inicia o listener global de atalhos de teclado (Windows / Mac / Linux)
        self.hotkey_listener = GlobalHotkeyListener(
            get_hotkey_codes=lambda: self.config.get("hotkey_codes", [0x14]),
            get_hotkey_mode=lambda: self.config.get("hotkey_mode", "smart"),
            on_start_recording=self._on_hotkey_start,
            on_stop_recording=self._on_hotkey_stop,
            on_cancel_recording=self._on_hotkey_cancel,
            on_toggle_locked=self._on_hotkey_locked,
            on_master_toggle=self._on_master_toggle,
            on_toggle_audio_recording=self._on_toggle_audio_recording,
            initial_tool_enabled=bool(self.config.get("tool_enabled", True)),
        )
        self.hotkey_listener.start()

        # Pré-carrega o modelo local na GPU em segundo plano se configurado
        if self.config.get("engine_mode", "hybrid") in ("hybrid", "local"):
            self.transcriber.preload_local_model_async(
                self.config.get("local_model", "mobiuslabsgmbh/faster-whisper-large-v3-turbo")
            )

        # Se o software ainda não estiver ativado, exibe a tela de ativação
        if not is_activated():
            self.root.after(350, self.show_activation_dialog)

    def _setup_main_window(self) -> None:
        self.root.title(f"{APP_NAME} Pro — {APP_TAGLINE}")
        self.root.geometry("880x780")
        self.root.minsize(820, 720)
        self.root.configure(bg=self.BG_MAIN)

        # Ícone da janela e barra de tarefas
        try:
            ico_path = get_resource_path(os.path.join("assets", "icon.ico"))
            if ico_path.exists() and is_windows():
                self.root.iconbitmap(str(ico_path))
        except Exception:
            pass

        try:
            png_path = get_resource_path(os.path.join("assets", "icon_64.png"))
            if png_path.exists():
                self._app_icon_photo = ImageTk.PhotoImage(Image.open(str(png_path)))
                self.root.iconphoto(True, self._app_icon_photo)
        except Exception:
            pass

        # Centraliza na tela
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(20, (sw - 880) // 2)
        y = max(30, (sh - 780) // 2 - 20)
        self.root.geometry(f"880x780+{x}+{y}")

        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_pill)

        # Estilo dos Comboboxes ttk
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dark.TCombobox",
            fieldbackground=self.BG_INPUT,
            background=self.BG_INPUT,
            foreground=self.TEXT_PRIMARY,
            arrowcolor=self.TEXT_PRIMARY,
            bordercolor=self.BORDER_COL,
            lightcolor=self.BG_INPUT,
            darkcolor=self.BG_INPUT,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", self.BG_INPUT)],
            selectbackground=[("readonly", self.BG_INPUT)],
            selectforeground=[("readonly", self.TEXT_PRIMARY)],
        )

    def _build_ui(self) -> None:
        # Topo estilo Apple Pro com Logo e Status de Licença
        top_bar = tk.Frame(self.root, bg=self.BG_TOPBAR, padx=22, pady=14)
        top_bar.pack(fill="x")

        brand_left = tk.Frame(top_bar, bg=self.BG_TOPBAR)
        brand_left.pack(side="left")

        try:
            logo_p = get_resource_path(os.path.join("assets", "logo.png"))
            if logo_p.exists():
                pil_logo = Image.open(str(logo_p)).convert("RGBA").resize((40, 40), Image.Resampling.LANCZOS)
                self._header_logo_img = ImageTk.PhotoImage(pil_logo)
                lbl_logo = tk.Label(brand_left, image=self._header_logo_img, bg=self.BG_TOPBAR, bd=0)
                lbl_logo.pack(side="left", padx=(0, 12))
        except Exception as e:
            print(f"[UI] Aviso ao carregar logo: {e}")

        title_info = tk.Frame(brand_left, bg=self.BG_TOPBAR)
        title_info.pack(side="left")

        title_row = tk.Frame(title_info, bg=self.BG_TOPBAR)
        title_row.pack(anchor="w")

        tk.Label(
            title_row,
            text=APP_NAME,
            font=("Segoe UI Variable Display", 17, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_TOPBAR,
        ).pack(side="left")

        # Badge de Licença Pro ou Free
        self.lbl_license_badge = tk.Label(
            title_row,
            text="",
            font=("Segoe UI Semibold", 8),
            padx=8,
            pady=2,
            bd=0,
            cursor="hand2",
        )
        self.lbl_license_badge.pack(side="left", padx=(10, 0))
        self.lbl_license_badge.bind("<Button-1>", lambda e: self.show_activation_dialog())
        self._refresh_license_badge()

        self.lbl_engine_status = tk.Label(
            title_info,
            text=f"● {APP_TAGLINE} • {get_platform_name()}",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_TOPBAR,
        )
        self.lbl_engine_status.pack(anchor="w", pady=(2, 0))

        # Ações no topo direito
        top_actions = tk.Frame(top_bar, bg=self.BG_TOPBAR)
        top_actions.pack(side="right")

        tk.Button(
            top_actions,
            text="🎯 Localizar Pílula",
            font=("Segoe UI Semibold", 9),
            bg="#2E1065",
            fg="#DDD6FE",
            activebackground="#4C1D95",
            activeforeground="#FFFFFF",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=lambda: self.pill.reset_position_to_center(),
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            top_actions,
            text="Minimizar p/ Pílula",
            font=("Segoe UI Semibold", 9),
            bg=self.BG_INPUT,
            fg=self.TEXT_PRIMARY,
            activebackground=self.BORDER_COL,
            activeforeground=self.TEXT_PRIMARY,
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self.minimize_to_pill,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            top_actions,
            text="Sair",
            font=("Segoe UI Semibold", 9),
            bg="#2D161E",
            fg="#FCA5A5",
            activebackground="#451A26",
            activeforeground="#FECACA",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self.quit_app,
        ).pack(side="left")

        # Container Principal
        body = tk.Frame(self.root, bg=self.BG_MAIN, padx=22, pady=12)
        body.pack(fill="both", expand=True)

        # Barra de Navegação Segmentada estilo Apple (Tabs)
        tab_bar = tk.Frame(body, bg=self.BG_CARD, padx=6, pady=6, highlightthickness=1, highlightbackground=self.BORDER_COL)
        tab_bar.pack(fill="x", pady=(0, 12))

        self.tab_buttons: Dict[str, tk.Button] = {}
        tabs = [
            ("dictation", "⚡ Ditado & IA"),
            ("studio", "🎧 Gravador Studio (Alt + A)"),
            ("pill", "🎨 Pílula & Sistema"),
            ("license", "🔑 Licença Comercial"),
        ]
        for key, label in tabs:
            btn = tk.Button(
                tab_bar,
                text=label,
                font=("Segoe UI Semibold", 9),
                bd=0,
                padx=16,
                pady=7,
                cursor="hand2",
                command=lambda k=key: self._switch_tab(k),
            )
            btn.pack(side="left", padx=4)
            self.tab_buttons[key] = btn

        # Área de Conteúdo das Abas
        self.tab_container = tk.Frame(body, bg=self.BG_MAIN)
        self.tab_container.pack(fill="both", expand=True)

        self._build_tab_dictation()
        self._build_tab_studio()
        self._build_tab_pill()
        self._build_tab_license()

        # Exibe a aba inicial
        self._switch_tab("dictation")

        # --- ÁREA INFERIOR: PLAYGROUND INTERATIVO + HISTÓRICO ---
        bottom_area = tk.Frame(body, bg=self.BG_CARD, padx=16, pady=10, highlightthickness=1, highlightbackground=self.BORDER_COL)
        bottom_area.pack(fill="x", pady=(10, 0))

        test_hdr = tk.Frame(bottom_area, bg=self.BG_CARD)
        test_hdr.pack(fill="x", pady=(0, 4))

        tk.Label(
            test_hdr,
            text="🎙️ Campo de Teste Rápido (Clique abaixo, aperte seu atalho e fale!):",
            font=("Segoe UI Semibold", 9),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(side="left")

        tk.Button(
            test_hdr,
            text="Copiar Último Texto",
            font=("Segoe UI Semibold", 8),
            bg=self.BG_INPUT,
            fg="#A78BFA",
            activebackground=self.BORDER_COL,
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._copy_last_transcription,
        ).pack(side="right")

        self.txt_playground = tk.Text(
            bottom_area,
            height=3,
            bg=self.BG_INPUT,
            fg=self.TEXT_PRIMARY,
            insertbackground="#A78BFA",
            relief="flat",
            font=("Segoe UI", 9),
            padx=10,
            pady=6,
            wrap="word",
        )
        self.txt_playground.pack(fill="x", pady=(0, 6))
        self.txt_playground.insert(
            "1.0",
            "Pressione seu atalho (CapsLock) e comece a falar. O texto corrigido pela IA será inserido aqui instantaneamente!",
        )
        self.txt_playground.bind("<FocusIn>", self._clear_placeholder_on_focus)
        self._placeholder_active = True

        hist_hdr = tk.Frame(bottom_area, bg=self.BG_CARD)
        hist_hdr.pack(fill="x")
        tk.Label(
            hist_hdr,
            text="Últimas transcrições salvas:",
            font=("Segoe UI", 8),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_CARD,
        ).pack(side="left")

        self.lst_history = tk.Listbox(
            bottom_area,
            height=3,
            bg=self.BG_INPUT,
            fg=self.TEXT_SECONDARY,
            selectbackground=self.BORDER_COL,
            selectforeground=self.TEXT_PRIMARY,
            relief="flat",
            font=("Consolas", 8),
            bd=0,
            highlightthickness=0,
        )
        self.lst_history.pack(fill="x", pady=(3, 0))
        self.lst_history.bind("<Double-Button-1>", self._on_history_double_click)
        self._refresh_history_list()

    def _switch_tab(self, tab_key: str) -> None:
        self._active_tab = tab_key
        for k, btn in self.tab_buttons.items():
            if k == tab_key:
                btn.configure(bg=self.ACCENT, fg="#FFFFFF", activebackground=self.ACCENT_HOVER, activeforeground="#FFFFFF")
            else:
                btn.configure(bg=self.BG_CARD, fg=self.TEXT_SECONDARY, activebackground=self.BG_CARD_SUBTLE, activeforeground=self.TEXT_PRIMARY)

        # Oculta todos os painéis e exibe o selecionado
        for frame in [self.frame_dictation, self.frame_studio, self.frame_pill, self.frame_license]:
            frame.pack_forget()

        if tab_key == "dictation":
            self.frame_dictation.pack(fill="both", expand=True)
        elif tab_key == "studio":
            self.frame_studio.pack(fill="both", expand=True)
            self._refresh_audio_history_list()
        elif tab_key == "pill":
            self.frame_pill.pack(fill="both", expand=True)
        elif tab_key == "license":
            self.frame_license.pack(fill="both", expand=True)
            self._update_license_tab_view()

    # --- ABA 1: DITADO & IA ---
    def _build_tab_dictation(self) -> None:
        self.frame_dictation = tk.Frame(self.tab_container, bg=self.BG_MAIN)

        # Métricas no topo
        stats_row = tk.Frame(self.frame_dictation, bg=self.BG_MAIN)
        stats_row.pack(fill="x", pady=(0, 10))
        for i in range(3):
            stats_row.columnconfigure(i, weight=1)

        self.lbl_stat_words = self._create_stat_box(
            stats_row, 0, "PALAVRAS DITADAS", f"{self.config.get('stats_total_words', 0)}"
        )
        self.lbl_stat_shortcut = self._create_stat_box(
            stats_row, 1, "ATALHO ATIVO", self.config.get("hotkey_label", "CapsLock")
        )
        self.lbl_stat_speed = self._create_stat_box(
            stats_row, 2, "LATÊNCIA / MOTOR", "Pronto (< 0.4s)"
        )

        grid_frame = tk.Frame(self.frame_dictation, bg=self.BG_MAIN)
        grid_frame.pack(fill="both", expand=True)
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        # Coluna Esquerda: Atalho e Gatilho
        left_card = tk.Frame(grid_frame, bg=self.BG_CARD, padx=16, pady=12, highlightthickness=1, highlightbackground=self.BORDER_COL)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        tk.Label(left_card, text="⌨️ Atalho de Ditado", font=("Segoe UI Semibold", 11), fg=self.TEXT_PRIMARY, bg=self.BG_CARD).pack(anchor="w", pady=(0, 6))
        tk.Label(left_card, text="Selecione um atalho rápido ou grave sua tecla preferida:", font=("Segoe UI", 8), fg=self.TEXT_SECONDARY, bg=self.BG_CARD).pack(anchor="w")

        hk_row = tk.Frame(left_card, bg=self.BG_CARD)
        hk_row.pack(fill="x", pady=(4, 8))

        preset_labels = [p["label"] for p in HOTKEY_PRESETS]
        self.cmb_hotkey = ttk.Combobox(hk_row, values=preset_labels, state="readonly", style="Dark.TCombobox", width=22)
        current_codes = self.config.get("hotkey_codes", [0x14])
        matched_preset = next((p["label"] for p in HOTKEY_PRESETS if p["codes"] == current_codes), f"Personalizado: {self.config.get('hotkey_label', 'CapsLock')}")
        self.cmb_hotkey.set(matched_preset)
        self.cmb_hotkey.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.cmb_hotkey.bind("<<ComboboxSelected>>", self._on_preset_hotkey_selected)

        self.btn_record_hk = tk.Button(
            hk_row, text="⏺ Gravar Tecla", font=("Segoe UI Semibold", 8), bg=self.ACCENT, fg="#FFFFFF",
            activebackground=self.ACCENT_HOVER, bd=0, padx=10, pady=4, cursor="hand2", command=self._start_custom_hotkey_capture
        )
        self.btn_record_hk.pack(side="right")

        tk.Label(left_card, text="Comportamento da Tecla:", font=("Segoe UI", 9), fg=self.TEXT_SECONDARY, bg=self.BG_CARD).pack(anchor="w", pady=(4, 2))
        self.mode_map = {
            "Inteligente (Toque rápido = Toggle, Segurar = Push-to-Talk)": "smart",
            "Apenas Segurar para Falar (Push-to-Talk)": "hold",
            "Apenas Alternar Liga / Desliga (Toggle)": "toggle",
        }
        inv_mode = {v: k for k, v in self.mode_map.items()}
        self.cmb_mode = ttk.Combobox(left_card, values=list(self.mode_map.keys()), state="readonly", style="Dark.TCombobox")
        self.cmb_mode.set(inv_mode.get(self.config.get("hotkey_mode", "smart"), list(self.mode_map.keys())[0]))
        self.cmb_mode.pack(fill="x", pady=(0, 8))
        self.cmb_mode.bind("<<ComboboxSelected>>", lambda e: self._save_ui_settings())

        tk.Label(
            left_card,
            text="💡 Dica de Ouro: Pressione Ctrl + CapsLock para pausar/retomar a ferramenta quando precisar usar o CapsLock tradicional para maiúsculas.",
            font=("Segoe UI", 8),
            fg="#A78BFA",
            bg=self.BG_CARD,
            wraplength=340,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        # Coluna Direita: Motor de IA e Limpeza
        right_card = tk.Frame(grid_frame, bg=self.BG_CARD, padx=16, pady=12, highlightthickness=1, highlightbackground=self.BORDER_COL)
        right_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        tk.Label(right_card, text="🧠 Motor de IA & Reescrita", font=("Segoe UI Semibold", 11), fg=self.TEXT_PRIMARY, bg=self.BG_CARD).pack(anchor="w", pady=(0, 6))

        tk.Label(right_card, text="Motor de Transcrição:", font=("Segoe UI", 9), fg=self.TEXT_SECONDARY, bg=self.BG_CARD).pack(anchor="w", pady=(0, 2))
        self.engine_map = {
            "Híbrido (Groq Cloud Ultrarrápido + GPU Local)": "hybrid",
            "100% Local Offline (Faster-Whisper CUDA / CPU)": "local",
            "Apenas Nuvem (Groq Cloud API)": "groq",
        }
        inv_engine_map = {v: k for k, v in self.engine_map.items()}
        self.cmb_engine = ttk.Combobox(right_card, values=list(self.engine_map.keys()), state="readonly", style="Dark.TCombobox")
        self.cmb_engine.set(inv_engine_map.get(self.config.get("engine_mode", "hybrid"), list(self.engine_map.keys())[0]))
        self.cmb_engine.pack(fill="x", pady=(0, 6))
        self.cmb_engine.bind("<<ComboboxSelected>>", lambda e: self._save_ui_settings())

        tk.Label(right_card, text="Limpeza de Vícios & Pontuação Automática:", font=("Segoe UI", 9), fg=self.TEXT_SECONDARY, bg=self.BG_CARD).pack(anchor="w", pady=(0, 2))
        self.cleanup_map = {
            "Completa (Remove 'ééé', 'tipo', gagueiras, auto-correções e pontua)": "smart_ai",
            "Limpeza Rápida (Remove muletas e palavras repetidas)": "clean_fillers",
            "Literal (Sem filtro — apenas o que o microfone captar)": "raw",
        }
        inv_cleanup = {v: k for k, v in self.cleanup_map.items()}
        self.cmb_cleanup = ttk.Combobox(right_card, values=list(self.cleanup_map.keys()), state="readonly", style="Dark.TCombobox")
        self.cmb_cleanup.set(inv_cleanup.get(self.config.get("cleanup_level", "smart_ai"), list(self.cleanup_map.keys())[0]))
        self.cmb_cleanup.pack(fill="x", pady=(0, 6))
        self.cmb_cleanup.bind("<<ComboboxSelected>>", lambda e: self._save_ui_settings())

        # Chave Groq
        key_hdr = tk.Frame(right_card, bg=self.BG_CARD)
        key_hdr.pack(fill="x", pady=(2, 0))
        tk.Label(key_hdr, text="Chave Groq Cloud (Opcional p/ transcrição em < 0.4s):", font=("Segoe UI", 8), fg=self.TEXT_SECONDARY, bg=self.BG_CARD).pack(side="left")
        lbl_link = tk.Label(key_hdr, text="Gerar grátis ↗", font=("Segoe UI Semibold", 8, "underline"), fg="#A78BFA", bg=self.BG_CARD, cursor="hand2")
        lbl_link.pack(side="right")
        lbl_link.bind("<Button-1>", lambda e: webbrowser.open("https://console.groq.com/keys"))

        key_row = tk.Frame(right_card, bg=self.BG_CARD)
        key_row.pack(fill="x", pady=(2, 0))
        self.ent_groq_key = tk.Entry(key_row, bg=self.BG_INPUT, fg=self.TEXT_PRIMARY, insertbackground=self.TEXT_PRIMARY, relief="flat", font=("Consolas", 8), show="•")
        self.ent_groq_key.insert(0, self.config.get("groq_api_key", ""))
        self.ent_groq_key.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 6))
        tk.Button(key_row, text="Salvar", font=("Segoe UI Semibold", 8), bg=self.ACCENT, fg="#FFFFFF", bd=0, padx=8, pady=3, cursor="hand2", command=self._save_ui_settings).pack(side="right")

    # --- ABA 2: GRAVADOR STUDIO (ALT + A) ---
    def _build_tab_studio(self) -> None:
        self.frame_studio = tk.Frame(self.tab_container, bg=self.BG_MAIN)

        card_studio = tk.Frame(self.frame_studio, bg=self.BG_CARD, padx=18, pady=14, highlightthickness=1, highlightbackground=self.BORDER_COL)
        card_studio.pack(fill="x", pady=(0, 10))

        shdr = tk.Frame(card_studio, bg=self.BG_CARD)
        shdr.pack(fill="x")

        sleft = tk.Frame(shdr, bg=self.BG_CARD)
        sleft.pack(side="left", fill="x", expand=True)

        tk.Label(sleft, text="🎧 Gravador de Áudio Studio Broadcast", font=("Segoe UI Semibold", 12), fg=self.STUDIO_RED, bg=self.BG_CARD).pack(anchor="w")
        tk.Label(sleft, text="Gravações com fidelidade máxima sem colar texto na tela, direto em arquivo WAV.", font=("Segoe UI", 8), fg=self.TEXT_SECONDARY, bg=self.BG_CARD).pack(anchor="w", pady=(1, 0))

        sright = tk.Frame(shdr, bg=self.BG_CARD)
        sright.pack(side="right")

        tk.Button(
            sright, text="📁 Abrir Pasta de Áudios", font=("Segoe UI Semibold", 9), bg=self.BG_INPUT, fg="#FFFFFF",
            bd=0, padx=12, pady=5, cursor="hand2", command=self._open_audios_folder
        ).pack(side="left", padx=(0, 8))

        self.btn_rec_audio_ui = tk.Button(
            sright, text="⏺ Gravar Áudio (Alt + A)", font=("Segoe UI Semibold", 9), bg="#9F1239", fg="#FFFFFF",
            activebackground="#BE123C", bd=0, padx=14, pady=5, cursor="hand2", command=self._on_toggle_audio_recording
        )
        self.btn_rec_audio_ui.pack(side="left")

        # Configurações do Gravador
        sbody = tk.Frame(card_studio, bg=self.BG_CARD)
        sbody.pack(fill="x", pady=(12, 0))

        tk.Label(sbody, text=f"📂 Pasta de Destino: {self._audio_rec_folder}", font=("Segoe UI", 8), fg=self.TEXT_MUTED, bg=self.BG_CARD).pack(anchor="w")
        tk.Label(sbody, text="● Qualidade: 48.000 Hz, 16-bit PCM WAV (Padrão DaVinci Resolve, Premiere e CapCut)", font=("Segoe UI Semibold", 8), fg=self.SUCCESS, bg=self.BG_CARD).pack(anchor="w", pady=(2, 0))

        # Lista de Áudios Gravados
        hist_card = tk.Frame(self.frame_studio, bg=self.BG_CARD, padx=16, pady=12, highlightthickness=1, highlightbackground=self.BORDER_COL)
        hist_card.pack(fill="both", expand=True)

        tk.Label(hist_card, text="🎙️ Histórico de Gravações de Áudio:", font=("Segoe UI Semibold", 10), fg=self.TEXT_PRIMARY, bg=self.BG_CARD).pack(anchor="w", pady=(0, 6))

        self.lst_audio_history = tk.Listbox(
            hist_card,
            bg=self.BG_INPUT,
            fg=self.TEXT_PRIMARY,
            selectbackground=self.BORDER_COL,
            selectforeground=self.TEXT_PRIMARY,
            relief="flat",
            font=("Consolas", 9),
            bd=0,
            highlightthickness=0,
        )
        self.lst_audio_history.pack(fill="both", expand=True)
        self.lst_audio_history.bind("<Double-Button-1>", lambda e: self._open_audios_folder())

    # --- ABA 3: PÍLULA & SISTEMA ---
    def _build_tab_pill(self) -> None:
        self.frame_pill = tk.Frame(self.tab_container, bg=self.BG_MAIN)

        pcard = tk.Frame(self.frame_pill, bg=self.BG_CARD, padx=18, pady=14, highlightthickness=1, highlightbackground=self.BORDER_COL)
        pcard.pack(fill="both", expand=True)

        tk.Label(pcard, text="🎨 Preferências da Pílula Flutuante & Sistema", font=("Segoe UI Semibold", 11), fg=self.TEXT_PRIMARY, bg=self.BG_CARD).pack(anchor="w", pady=(0, 10))

        tk.Label(pcard, text="Microfone de Entrada:", font=("Segoe UI", 9), fg=self.TEXT_SECONDARY, bg=self.BG_CARD).pack(anchor="w", pady=(0, 2))
        mic_names = [m["name"] for m in self.mics]
        self.cmb_mic = ttk.Combobox(pcard, values=mic_names, state="readonly", style="Dark.TCombobox")
        cur_mic_id = self.config.get("mic_device_id", -1)
        cur_mic_label = next((m["name"] for m in self.mics if m["id"] == cur_mic_id), mic_names[0] if mic_names else "Padrão")
        self.cmb_mic.set(cur_mic_label)
        self.cmb_mic.pack(fill="x", pady=(0, 10))
        self.cmb_mic.bind("<<ComboboxSelected>>", lambda e: self._save_ui_settings())

        tk.Label(pcard, text="Modo de Exibição da Pílula na Tela:", font=("Segoe UI", 9), fg=self.TEXT_SECONDARY, bg=self.BG_CARD).pack(anchor="w", pady=(0, 2))
        self.pill_vis_map = {
            "Sempre visível na tela (Pílula Vertical Discreta)": "always",
            "Aparecer somente enquanto estiver gravando ou processando": "active_only",
        }
        inv_pill_map = {v: k for k, v in self.pill_vis_map.items()}
        self.cmb_pill_vis = ttk.Combobox(pcard, values=list(self.pill_vis_map.keys()), state="readonly", style="Dark.TCombobox")
        self.cmb_pill_vis.set(inv_pill_map.get(self.config.get("pill_visibility", "always"), list(self.pill_vis_map.keys())[0]))
        self.cmb_pill_vis.pack(fill="x", pady=(0, 10))
        self.cmb_pill_vis.bind("<<ComboboxSelected>>", lambda e: self._save_ui_settings())

        # Checkboxes de Opções
        self.var_autostart = tk.BooleanVar(value=bool(self.config.get("start_with_windows", True)))
        tk.Checkbutton(
            pcard, text="Iniciar automaticamente ao ligar o computador", variable=self.var_autostart,
            font=("Segoe UI Semibold", 9), fg=self.TEXT_PRIMARY, bg=self.BG_CARD, selectcolor=self.BG_INPUT,
            activebackground=self.BG_CARD, activeforeground=self.TEXT_PRIMARY, command=self._save_ui_settings
        ).pack(anchor="w", pady=(4, 6))

        self.var_sound = tk.BooleanVar(value=bool(self.config.get("sound_feedback", True)))
        tk.Checkbutton(
            pcard, text="Sons sutis de feedback ao iniciar e parar gravação", variable=self.var_sound,
            font=("Segoe UI Semibold", 9), fg=self.TEXT_PRIMARY, bg=self.BG_CARD, selectcolor=self.BG_INPUT,
            activebackground=self.BG_CARD, activeforeground=self.TEXT_PRIMARY, command=self._save_ui_settings
        ).pack(anchor="w", pady=(0, 6))

    # --- ABA 4: LICENÇA COMERCIAL ---
    def _build_tab_license(self) -> None:
        self.frame_license = tk.Frame(self.tab_container, bg=self.BG_MAIN)

        lcard = tk.Frame(self.frame_license, bg=self.BG_CARD, padx=20, pady=18, highlightthickness=1, highlightbackground=self.BORDER_COL)
        lcard.pack(fill="both", expand=True)

        self.lbl_lic_status_title = tk.Label(lcard, text="👑 Status da Licença Comercial", font=("Segoe UI Semibold", 13), fg=self.TEXT_PRIMARY, bg=self.BG_CARD)
        self.lbl_lic_status_title.pack(anchor="w", pady=(0, 8))

        self.lbl_lic_status_desc = tk.Label(lcard, text="", font=("Segoe UI", 9), fg=self.TEXT_SECONDARY, bg=self.BG_CARD, justify="left")
        self.lbl_lic_status_desc.pack(anchor="w", pady=(0, 12))

        # Box de Detalhes
        det_box = tk.Frame(lcard, bg=self.BG_INPUT, padx=14, pady=12, highlightthickness=1, highlightbackground=self.BORDER_COL)
        det_box.pack(fill="x", pady=(0, 14))

        self.lbl_lic_key_show = tk.Label(det_box, text="", font=("Consolas", 10, "bold"), fg=self.ACCENT_GLOW, bg=self.BG_INPUT)
        self.lbl_lic_key_show.pack(anchor="w")

        mach_id = get_machine_fingerprint()
        mach_row = tk.Frame(det_box, bg=self.BG_INPUT)
        mach_row.pack(fill="x", pady=(6, 0))

        tk.Label(mach_row, text=f"ID do Computador (Machine ID): {mach_id}", font=("Consolas", 8), fg=self.TEXT_MUTED, bg=self.BG_INPUT).pack(side="left")
        btn_copy_mid = tk.Button(
            mach_row, text="Copiar ID", font=("Segoe UI", 7), bg=self.BG_CARD, fg=self.TEXT_SECONDARY,
            bd=0, padx=6, pady=2, cursor="hand2", command=lambda: set_clipboard_text(mach_id)
        )
        btn_copy_mid.pack(side="right")

        # Botões de Ação de Licença
        btn_row = tk.Frame(lcard, bg=self.BG_CARD)
        btn_row.pack(fill="x")

        tk.Button(
            btn_row, text="✦ Inserir / Trocar Chave de Ativação", font=("Segoe UI Semibold", 9), bg=self.ACCENT,
            fg="#FFFFFF", activebackground=self.ACCENT_HOVER, bd=0, padx=14, pady=6, cursor="hand2",
            command=self.show_activation_dialog
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            btn_row, text="Desativar Deste PC", font=("Segoe UI Semibold", 8), bg="#2D161E",
            fg="#FCA5A5", bd=0, padx=10, pady=6, cursor="hand2", command=self._on_deactivate_license
        ).pack(side="left")

    def _update_license_tab_view(self) -> None:
        info = get_license_info()
        if info.get("activated"):
            self.lbl_lic_status_title.configure(text=f"👑 NexFlow {info.get('tier', 'PRO')} — Ativado", fg=self.GOLD)
            self.lbl_lic_status_desc.configure(
                text=f"Licença comercial permanentemente ativa para {info.get('owner', 'Cliente')} neste computador.\n"
                     f"Ativada em: {info.get('activated_at', 'Recente')}"
            )
            key = info.get("key", "")
            masked = key[:16] + "••••-••••" if len(key) >= 16 else key
            self.lbl_lic_key_show.configure(text=f"CHAVE: {masked}")
        else:
            self.lbl_lic_status_title.configure(text="🔒 NexFlow — Cópia Não Ativada", fg=self.STUDIO_RED)
            self.lbl_lic_status_desc.configure(
                text="Para utilizar as funções de ditado com IA e o gravador studio, insira uma chave comercial válida."
            )
            self.lbl_lic_key_show.configure(text="NENHUMA LICENÇA ATIVA")

    def _refresh_license_badge(self) -> None:
        if is_activated():
            info = get_license_info()
            tier = info.get("tier", "PRO")
            self.lbl_license_badge.configure(text=f"● {tier} ATIVADO", bg="#064E3B", fg="#34D399")
        else:
            self.lbl_license_badge.configure(text="🔒 NÃO ATIVADO", bg="#451A26", fg="#FCA5A5")

    # --- DIÁLOGO PREMIUM DE ATIVAÇÃO DE LICENÇA ---
    def show_activation_dialog(self) -> None:
        """Abre uma janela modal elegante estilo Apple para ativação com chave de licença."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Ativação do NexFlow Pro")
        dlg.geometry("480x420")
        dlg.minsize(440, 380)
        dlg.configure(bg="#0D0F18")
        dlg.transient(self.root)
        dlg.grab_set()

        # Centraliza sobre a janela pai
        try:
            px = self.root.winfo_x() + (self.root.winfo_width() - 480) // 2
            py = self.root.winfo_y() + (self.root.winfo_height() - 420) // 2
            dlg.geometry(f"480x420+{px}+{py}")
        except Exception:
            pass

        content = tk.Frame(dlg, bg="#0D0F18", padx=24, pady=20)
        content.pack(fill="both", expand=True)

        try:
            logo_p = get_resource_path(os.path.join("assets", "icon_64.png"))
            if logo_p.exists():
                pil_logo = Image.open(str(logo_p)).convert("RGBA").resize((52, 52), Image.Resampling.LANCZOS)
                dlg._logo_img = ImageTk.PhotoImage(pil_logo)
                tk.Label(content, image=dlg._logo_img, bg="#0D0F18", bd=0).pack(pady=(0, 8))
        except Exception:
            pass

        tk.Label(content, text="Ativar NexFlow Pro", font=("Segoe UI Variable Display", 15, "bold"), fg="#FFFFFF", bg="#0D0F18").pack()
        tk.Label(
            content,
            text="Insira a chave de licença que você recebeu após a compra para desbloquear todas as funcionalidades.",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg="#0D0F18",
            wraplength=380,
            justify="center",
        ).pack(pady=(4, 14))

        # Campo da Chave
        tk.Label(content, text="CHAVE DE LICENÇA (SERIAL):", font=("Segoe UI Semibold", 8), fg=self.ACCENT_GLOW, bg="#0D0F18").pack(anchor="w")

        ent_key = tk.Entry(
            content, bg="#181B2B", fg="#FFFFFF", insertbackground="#FFFFFF", relief="flat",
            font=("Consolas", 10), justify="center", highlightthickness=1, highlightbackground=self.BORDER_COL
        )
        ent_key.pack(fill="x", ipady=8, pady=(4, 8))
        ent_key.focus_set()

        # Nome ou E-mail (Opcional)
        tk.Label(content, text="SEU NOME OU E-MAIL (OPCIONAL):", font=("Segoe UI Semibold", 8), fg=self.TEXT_MUTED, bg="#0D0F18").pack(anchor="w")
        ent_name = tk.Entry(
            content, bg="#181B2B", fg="#FFFFFF", insertbackground="#FFFFFF", relief="flat",
            font=("Segoe UI", 9), highlightthickness=1, highlightbackground=self.BORDER_COL
        )
        ent_name.pack(fill="x", ipady=6, pady=(4, 14))

        lbl_msg = tk.Label(content, text="", font=("Segoe UI", 8), bg="#0D0F18")
        lbl_msg.pack(pady=(0, 8))

        def _do_activate():
            key_val = ent_key.get().strip()
            name_val = ent_name.get().strip()
            ok, msg = activate_license(key_val, name_val)
            if ok:
                lbl_msg.configure(text=f"✓ {msg}", fg=self.SUCCESS)
                self._refresh_license_badge()
                self._update_license_tab_view()
                self.pill.set_state("done", "✓ Licença Ativada!", auto_revert_s=2.0)
                dlg.after(1200, dlg.destroy)
            else:
                lbl_msg.configure(text=f"✕ {msg}", fg=self.STUDIO_RED)

        btn_act = tk.Button(
            content, text="✦ Desbloquear & Ativar NexFlow", font=("Segoe UI Semibold", 10), bg=self.ACCENT,
            fg="#FFFFFF", activebackground=self.ACCENT_HOVER, bd=0, padx=16, ipady=7, cursor="hand2", command=_do_activate
        )
        btn_act.pack(fill="x")

        # Machine ID no rodapé
        mach_id = get_machine_fingerprint()
        tk.Label(content, text=f"Machine ID: {mach_id}", font=("Consolas", 7), fg=self.TEXT_MUTED, bg="#0D0F18").pack(pady=(14, 0))

    def _on_deactivate_license(self) -> None:
        if messagebox.askyesno("Desativar Licença", "Tem certeza que deseja desativar a licença deste computador?"):
            deactivate_license()
            self._refresh_license_badge()
            self._update_license_tab_view()
            messagebox.showinfo("Desativado", "A licença foi removida com sucesso deste PC.")

    def _create_stat_box(self, parent: tk.Frame, col: int, label: str, value: str) -> tk.Label:
        box = tk.Frame(parent, bg=self.BG_CARD, padx=14, pady=10, highlightthickness=1, highlightbackground=self.BORDER_COL)
        box.grid(row=0, column=col, sticky="nsew", padx=4)
        tk.Label(box, text=label, font=("Segoe UI Semibold", 8), fg=self.TEXT_MUTED, bg=self.BG_CARD).pack(anchor="w")
        lbl_val = tk.Label(box, text=value, font=("Segoe UI Variable Display", 13, "bold"), fg=self.TEXT_PRIMARY, bg=self.BG_CARD)
        lbl_val.pack(anchor="w", pady=(2, 0))
        return lbl_val

    def _refresh_history_list(self) -> None:
        self.lst_history.delete(0, "end")
        if not self.history:
            self.lst_history.insert("end", "  Nenhuma transcrição recente.")
            return
        for item in self.history[:15]:
            ts = item.get("timestamp", "")
            txt = item.get("final_text", "").replace("\n", " ")
            self.lst_history.insert("end", f" [{ts}]  {txt}")

    def _refresh_audio_history_list(self) -> None:
        self.lst_audio_history.delete(0, "end")
        self.audio_history = load_audio_history()
        if not self.audio_history:
            self.lst_audio_history.insert("end", "  Nenhum áudio gravado ainda. Pressione Alt + A para gravar!")
            return
        for item in self.audio_history[:25]:
            fn = item.get("filename", "")
            dur = item.get("duration_s", 0)
            sz = item.get("size_kb", 0)
            ts = item.get("timestamp", "")
            self.lst_audio_history.insert("end", f" 🎙️ {fn}  ({dur}s • {sz} KB) — {ts}")

    def _copy_last_transcription(self) -> None:
        if self.history:
            txt = self.history[0].get("final_text", "")
            if txt:
                set_clipboard_text(txt)
                self.pill.set_state("done", "✓ Copiado!", auto_revert_s=1.0)

    def _on_history_double_click(self, event) -> None:
        sel = self.lst_history.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self.history):
            txt = self.history[idx].get("final_text", "")
            if txt:
                set_clipboard_text(txt)
                self.pill.set_state("done", "✓ Copiado!", auto_revert_s=1.0)

    def _clear_placeholder_on_focus(self, event) -> None:
        if getattr(self, "_placeholder_active", False):
            self.txt_playground.delete("1.0", "end")
            self._placeholder_active = False

    def _on_preset_hotkey_selected(self, event=None) -> None:
        sel_label = self.cmb_hotkey.get()
        matched = next((p for p in HOTKEY_PRESETS if p["label"] == sel_label), None)
        if matched:
            self.config["hotkey_codes"] = list(matched["codes"])
            self.config["hotkey_label"] = matched["label"]
            self._save_ui_settings()

    def _start_custom_hotkey_capture(self) -> None:
        self.btn_record_hk.configure(text="Pressione a tecla...", bg="#F59E0B")
        self.root.update_idletasks()

        def _bg():
            codes, label = capture_custom_hotkey(timeout_s=5.0)
            def _done():
                self.btn_record_hk.configure(text="⏺ Gravar Tecla", bg=self.ACCENT)
                if codes and label:
                    self.config["hotkey_codes"] = codes
                    self.config["hotkey_label"] = label
                    self.cmb_hotkey.set(f"Personalizado: {label}")
                    self._save_ui_settings()
            self.root.after(0, _done)
        threading.Thread(target=_bg, daemon=True).start()

    def _save_ui_settings(self) -> None:
        self.config["hotkey_mode"] = self.mode_map.get(self.cmb_mode.get(), "smart")
        self.config["engine_mode"] = self.engine_map.get(self.cmb_engine.get(), "hybrid")
        self.config["cleanup_level"] = self.cleanup_map.get(self.cmb_cleanup.get(), "smart_ai")
        self.config["pill_visibility"] = self.pill_vis_map.get(self.cmb_pill_vis.get(), "always")
        self.config["groq_api_key"] = self.ent_groq_key.get().strip()
        self.config["start_with_windows"] = bool(self.var_autostart.get())
        self.config["sound_feedback"] = bool(self.var_sound.get())
        configure_startup_cross_platform(self.config["start_with_windows"])

        sel_mic_name = self.cmb_mic.get()
        for m in self.mics:
            if m["name"] == sel_mic_name:
                self.config["mic_device_id"] = m["id"]
                self.config["mic_device_name"] = m["name"]
                break

        save_config(self.config)
        hk_label = self.config.get("hotkey_label", "CapsLock")
        is_en = bool(self.config.get("tool_enabled", True))
        self.lbl_stat_shortcut.configure(text=hk_label if is_en else f"{hk_label} (Pausado)")
        self.pill.update_preferences(
            hotkey_label=hk_label,
            visibility_mode=self.config.get("pill_visibility", "always"),
            tool_enabled=is_en,
        )

    def _on_master_toggle(self, enabled: bool) -> None:
        """Acionado via Ctrl + CapsLock para Pausar / Retomar a ferramenta."""
        self.config["tool_enabled"] = enabled
        save_config(self.config)
        play_sound_cue("enable_tool" if enabled else "disable_tool", enabled=self.config.get("sound_feedback", True))

        def _ui():
            hk_label = self.config.get("hotkey_label", "CapsLock")
            self.lbl_stat_shortcut.configure(text=hk_label if enabled else f"{hk_label} (Pausado)")
            self.pill.update_preferences(
                hotkey_label=hk_label,
                visibility_mode=self.config.get("pill_visibility", "always"),
                tool_enabled=enabled,
            )
            if enabled:
                self.pill.set_state("done", "✓ NexFlow Ativado", auto_revert_s=1.2)
            else:
                self.pill.set_state("cancelled", "⏸ NexFlow Pausado", auto_revert_s=1.4)
        self.root.after(0, _ui)

    def _on_pill_moved(self, new_x: int, new_y: int) -> None:
        self.config["pill_x"] = new_x
        self.config["pill_y"] = new_y
        save_config(self.config)

    def _on_transcriber_status(self, msg: str) -> None:
        self.root.after(0, lambda: self.lbl_engine_status.configure(text=f"● {msg}"))

    # --- FLUXO DE GRAVAÇÃO E TRANSCRIÇÃO (DITADO) ---
    def _on_hotkey_start(self, submode: str) -> None:
        # Trava de Segurança Comercial: exige ativação
        if not is_activated():
            self.root.after(0, self.show_activation_dialog)
            return

        if self._is_processing:
            return
        self._target_hwnd = get_foreground_window()
        mic_id = self.config.get("mic_device_id", -1)
        self.recorder.start(device_id=mic_id, allow_auto_silence_stop=(submode != "hold"), sample_rate=16000)
        play_sound_cue("start", enabled=self.config.get("sound_feedback", True))

        pill_state = "recording_locked" if submode == "toggle" else "recording_hold"
        self.root.after(0, lambda: self.pill.set_state(pill_state))

    def _on_hotkey_locked(self) -> None:
        self.recorder.auto_stop_on_silence = True
        self.root.after(0, lambda: self.pill.set_state("recording_locked"))

    def _on_hotkey_cancel(self) -> None:
        self.recorder.cancel()
        play_sound_cue("cancel", enabled=self.config.get("sound_feedback", True))
        self.root.after(0, lambda: self.pill.set_state("cancelled", "✕ Ditado cancelado", auto_revert_s=1.0))

    def _trigger_stop_from_ui(self) -> None:
        if getattr(self, "_is_recording_audio", False):
            self._stop_audio_file_recording()
            return
        self.hotkey_listener.notify_recording_stopped_externally()
        self._on_hotkey_stop()

    def _trigger_cancel_from_ui(self) -> None:
        if getattr(self, "_is_recording_audio", False):
            self._cancel_audio_file_recording()
            return
        self.hotkey_listener.notify_recording_stopped_externally()
        self._on_hotkey_cancel()

    def _on_hotkey_stop(self) -> None:
        if not self.recorder.is_recording or self._is_processing:
            return

        self._is_processing = True
        play_sound_cue("stop", enabled=self.config.get("sound_feedback", True))
        audio_f32, wav_bytes, duration_s = self.recorder.stop()

        self.root.after(0, lambda: self.pill.set_state("processing", "Transcrevendo..."))

        def _worker():
            t0 = time.perf_counter()
            try:
                raw_text, final_text, engine_used = self.transcriber.process_audio(
                    audio_float32=audio_f32,
                    wav_bytes=wav_bytes,
                    duration_s=duration_s,
                    config=self.config,
                    on_stage=lambda st: self.root.after(0, lambda: self.pill.set_state("processing", st)),
                )
                elapsed = time.perf_counter() - t0
                self._last_latency_s = elapsed

                if not final_text:
                    self.root.after(0, lambda: self.pill.set_state("cancelled", "Nenhuma fala detectada", auto_revert_s=1.1))
                    return

                # Injeção multiplataforma no cursor
                ok = inject_text_cross_platform(final_text, target_hwnd=self._target_hwnd)
                play_sound_cue("done", enabled=self.config.get("sound_feedback", True))

                words_count = len(final_text.split())
                self.config["stats_total_words"] = self.config.get("stats_total_words", 0) + words_count
                self.config["stats_total_dictations"] = self.config.get("stats_total_dictations", 0) + 1
                self.config["stats_seconds_recorded"] = round(self.config.get("stats_seconds_recorded", 0.0) + duration_s, 1)
                save_config(self.config)

                self.history = add_history_entry(raw_text, final_text, duration_s, engine_used)

                def _update_ui():
                    self.pill.set_state("done", f"✓ Inserido ({elapsed:.1f}s)", auto_revert_s=1.1)
                    self.lbl_stat_words.configure(text=f"{self.config['stats_total_words']}")
                    self.lbl_stat_speed.configure(text=f"{elapsed:.2f}s • {engine_used}")
                    self._refresh_history_list()
                    if getattr(self, "_placeholder_active", False):
                        self.txt_playground.delete("1.0", "end")
                        self._placeholder_active = False
                    self.txt_playground.insert("end", final_text + " ")

                self.root.after(0, _update_ui)
            except Exception as e:
                print(f"[App] Erro na transcrição: {e}")
                self.root.after(0, lambda: self.pill.set_state("cancelled", "Erro ao transcrever", auto_revert_s=1.8))
            finally:
                self._is_processing = False

        threading.Thread(target=_worker, daemon=True).start()

    # --- FLUXO DO GRAVADOR STUDIO (ALT + A) ---
    def _on_toggle_audio_recording(self) -> None:
        if not is_activated():
            self.root.after(0, self.show_activation_dialog)
            return

        if not getattr(self, "_is_recording_audio", False):
            self._start_audio_file_recording()
        else:
            self._stop_audio_file_recording()

    def _update_audio_btn_text(self, is_recording: bool) -> None:
        if hasattr(self, "btn_rec_audio_ui"):
            if is_recording:
                self.btn_rec_audio_ui.configure(text="⏹ Parar e Salvar (Alt + A)", bg="#DC2626")
            else:
                self.btn_rec_audio_ui.configure(text="⏺ Gravar Áudio (Alt + A)", bg="#9F1239")

    def _start_audio_file_recording(self) -> None:
        if self._is_processing:
            return
        if self.recorder.is_recording:
            self.recorder.cancel()

        self._is_recording_audio = True
        mic_id = self.config.get("mic_device_id", -1)
        sr = int(self.config.get("audio_recorder_sample_rate", 48000))

        self.recorder.start(device_id=mic_id, allow_auto_silence_stop=False, sample_rate=sr)
        play_sound_cue("start", enabled=self.config.get("sound_feedback", True))

        self.root.after(0, lambda: self.pill.set_state("recording_audio", "Gravando Studio (Alt+A)"))
        self.root.after(0, lambda: self._update_audio_btn_text(True))

    def _stop_audio_file_recording(self) -> None:
        if not getattr(self, "_is_recording_audio", False) or not self.recorder.is_recording:
            return

        self._is_recording_audio = False
        self.root.after(0, lambda: self._update_audio_btn_text(False))
        play_sound_cue("stop", enabled=self.config.get("sound_feedback", True))

        audio_f32, wav_bytes, duration_s = self.recorder.stop()
        if duration_s < 0.35 or not wav_bytes:
            self.root.after(0, lambda: self.pill.set_state("cancelled", "Gravação muito curta", auto_revert_s=1.2))
            return

        dest_folder = self._audio_rec_folder
        try:
            dest_folder.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"Gravacao_{timestamp}.wav"
            out_file = dest_folder / filename
            out_file.write_bytes(wav_bytes)

            add_audio_recording_entry(filename=filename, filepath=str(out_file), duration_s=duration_s, size_bytes=len(wav_bytes))
            self.config["stats_audio_recordings_count"] = self.config.get("stats_audio_recordings_count", 0) + 1
            save_config(self.config)

            play_sound_cue("done", enabled=self.config.get("sound_feedback", True))
            self.root.after(0, lambda: self.pill.set_state("done", "✓ Áudio salvo em áudios!", auto_revert_s=2.2))
            self.root.after(0, self._refresh_audio_history_list)
        except Exception as e:
            print(f"[Studio] Erro ao gravar: {e}")
            self.root.after(0, lambda: self.pill.set_state("cancelled", "Erro ao salvar", auto_revert_s=1.5))

    def _cancel_audio_file_recording(self) -> None:
        self._is_recording_audio = False
        self.recorder.cancel()
        self.root.after(0, lambda: self._update_audio_btn_text(False))
        play_sound_cue("cancel", enabled=self.config.get("sound_feedback", True))
        self.root.after(0, lambda: self.pill.set_state("cancelled", "✕ Gravação descartada", auto_revert_s=1.2))

    def _open_audios_folder(self) -> None:
        try:
            open_folder_cross_platform(str(self._audio_rec_folder))
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir a pasta:\n{e}")

    def show_main_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def minimize_to_pill(self) -> None:
        self.root.withdraw()
        self.pill.win.deiconify()
        self.pill.reset_position_to_center()

    def quit_app(self) -> None:
        try:
            self.hotkey_listener.stop()
            self.recorder.cancel()
            self.pill.win.destroy()
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)


def _ensure_single_instance_and_logging() -> None:
    base_dir = Path(__file__).resolve().parent
    log_path = base_dir / "nexflow.log"
    pid_path = base_dir / "app.pid"

    try:
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    except Exception:
        pass

    if pid_path.exists() and is_windows():
        try:
            import subprocess
            old_pid = int(pid_path.read_text(encoding="utf-8").strip())
            if old_pid != os.getpid():
                subprocess.run(["taskkill", "/F", "/PID", str(old_pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(0.15)
        except Exception:
            pass

    try:
        pid_path.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass


def main():
    _ensure_single_instance_and_logging()
    print(f"[Main] Iniciando {APP_NAME} Pro (PID={os.getpid()}, args={sys.argv})")
    root = tk.Tk()
    app = NexFlowApp(root)
    # Se iniciar com argumento --minimized E com licença e chaves válidas, começa direto na pílula
    if "--minimized" in sys.argv:
        if is_activated() and (app.config.get("groq_api_key") or app.config.get("engine_mode") == "local"):
            root.after(200, app.minimize_to_pill)
        else:
            root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
