import ctypes
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from typing import Dict, Any, List

from config import load_config, save_config, load_history, add_history_entry, get_resource_path
from PIL import Image, ImageTk
from audio_recorder import AudioRecorder, list_microphones
from transcriber import HybridTranscriber, LOCAL_MODELS_CATALOG
from win32_utils import (
    GlobalHotkeyListener,
    HOTKEY_PRESETS,
    capture_custom_hotkey,
    configure_windows_startup,
    get_foreground_window,
    inject_text_at_cursor,
    play_sound_cue,
    set_clipboard_text,
)
from floating_pill import FloatingPillOverlay

# Ativa DPI Awareness no Windows para fontes super nítidas
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class WisprFlowFreeApp:
    # Paleta Dark Mode inspirada no Wispr Flow
    BG_MAIN = "#0B0C10"
    BG_CARD = "#13151E"
    BG_INPUT = "#1C1F2E"
    BORDER_COL = "#262A3D"
    ACCENT = "#8B5CF6"
    ACCENT_HOVER = "#7C3AED"
    TEXT_PRIMARY = "#F8FAFC"
    TEXT_SECONDARY = "#94A3B8"
    SUCCESS = "#10B981"
    WARNING = "#F59E0B"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.config: Dict[str, Any] = load_config()
        self.history: List[Dict[str, Any]] = load_history()
        self.mics = list_microphones()

        # Garante que a inicialização automática com o Windows esteja configurada conforme preferência
        configure_windows_startup(bool(self.config.get("start_with_windows", True)))

        self.recorder = AudioRecorder(on_auto_silence_stop=self._trigger_stop_from_ui)
        self.transcriber = HybridTranscriber(on_status_change=self._on_transcriber_status)
        self._is_processing = False
        self._last_latency_s = 0.0
        self._target_hwnd: int = 0

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

        # Inicia o listener global de atalhos de teclado + Hook Ctrl+CapsLock
        self.hotkey_listener = GlobalHotkeyListener(
            get_hotkey_codes=lambda: self.config.get("hotkey_codes", [0x14]),
            get_hotkey_mode=lambda: self.config.get("hotkey_mode", "smart"),
            on_start_recording=self._on_hotkey_start,
            on_stop_recording=self._on_hotkey_stop,
            on_cancel_recording=self._on_hotkey_cancel,
            on_toggle_locked=self._on_hotkey_locked,
            on_master_toggle=self._on_master_toggle,
            initial_tool_enabled=bool(self.config.get("tool_enabled", True)),
        )
        self.hotkey_listener.start()

        # Pré-carrega o modelo local na GPU GTX 1660 SUPER em segundo plano
        if self.config.get("engine_mode", "hybrid") in ("hybrid", "local"):
            self.transcriber.preload_local_model_async(
                self.config.get("local_model", "mobiuslabsgmbh/faster-whisper-large-v3-turbo")
            )

    def _setup_main_window(self) -> None:
        self.root.title("Wispr Flow Free — Ditado Inteligente por Voz")
        self.root.geometry("820x740")
        self.root.minsize(760, 680)
        self.root.configure(bg=self.BG_MAIN)

        # Ícone da janela e da barra de tarefas
        try:
            ico_path = get_resource_path(os.path.join("assets", "icon.ico"))
            if ico_path.exists():
                self.root.iconbitmap(str(ico_path))
        except Exception as e:
            print(f"[UI] Aviso ao aplicar iconbitmap: {e}")

        try:
            png_path = get_resource_path(os.path.join("assets", "icon_64.png"))
            if png_path.exists():
                self._app_icon_photo = ImageTk.PhotoImage(Image.open(str(png_path)))
                self.root.iconphoto(True, self._app_icon_photo)
        except Exception as e:
            print(f"[UI] Aviso ao aplicar iconphoto: {e}")

        # Centraliza na tela
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - 820) // 2
        y = max(30, (sh - 740) // 2 - 20)
        self.root.geometry(f"820x740+{x}+{y}")

        # Ao clicar no X da janela, minimiza para a pílula flutuante para continuar funcionando
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_pill)

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
        # Container principal com barra de rolagem suave se necessário
        top_bar = tk.Frame(self.root, bg="#10121A", padx=20, pady=12)
        top_bar.pack(fill="x")

        # Cabeçalho com Logo oficial
        brand_col = tk.Frame(top_bar, bg="#10121A")
        brand_col.pack(side="left")

        try:
            logo_p = get_resource_path(os.path.join("assets", "logo.png"))
            if logo_p.exists():
                pil_logo = Image.open(str(logo_p)).convert("RGBA").resize((38, 38), Image.Resampling.LANCZOS)
                self._header_logo_img = ImageTk.PhotoImage(pil_logo)
                lbl_logo = tk.Label(brand_col, image=self._header_logo_img, bg="#10121A", bd=0)
                lbl_logo.pack(side="left", padx=(0, 12))
        except Exception as e:
            print(f"[UI] Aviso ao carregar logo no header: {e}")

        title_col = tk.Frame(brand_col, bg="#10121A")
        title_col.pack(side="left")

        tk.Label(
            title_col,
            text="Wispr Flow Free",
            font=("Segoe UI Variable Display", 16, "bold"),
            fg=self.TEXT_PRIMARY,
            bg="#10121A",
        ).pack(anchor="w")

        self.lbl_engine_status = tk.Label(
            title_col,
            text="● Inicializando motor híbrido (Groq Cloud + GPU GTX 1660 SUPER)...",
            font=("Segoe UI", 9),
            fg="#A78BFA",
            bg="#10121A",
        )
        self.lbl_engine_status.pack(anchor="w", pady=(2, 0))

        # Botões de ação no topo direito
        btn_frame = tk.Frame(top_bar, bg="#10121A")
        btn_frame.pack(side="right")

        tk.Button(
            btn_frame,
            text="Minimizar p/ Pílula Flutuante",
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
            btn_frame,
            text="Sair Completamente",
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

        # Corpo principal
        body = tk.Frame(self.root, bg=self.BG_MAIN, padx=22, pady=12)
        body.pack(fill="both", expand=True)

        # Barra de Métricas Rápidas
        stats_row = tk.Frame(body, bg=self.BG_MAIN)
        stats_row.pack(fill="x", pady=(0, 10))
        for i in range(3):
            stats_row.columnconfigure(i, weight=1)

        self.lbl_stat_words = self._create_stat_box(
            stats_row, 0, "PALAVRAS DITADAS", f"{self.config.get('stats_total_words', 0)}"
        )
        self.lbl_stat_shortcut = self._create_stat_box(
            stats_row, 1, "ATALHO ATIVO", self.config.get("hotkey_label", "Ctrl + Win")
        )
        self.lbl_stat_speed = self._create_stat_box(
            stats_row, 2, "VELOCIDADE / MOTOR", "Pronto (< 0.6s)"
        )

        # Grid de 2 Colunas para Configurações
        grid_frame = tk.Frame(body, bg=self.BG_MAIN)
        grid_frame.pack(fill="x", pady=(0, 10))
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        # --- COLUNA ESQUERDA: Atalho, Modo e Microfone ---
        left_card = tk.Frame(
            grid_frame, bg=self.BG_CARD, padx=16, pady=14, highlightthickness=1, highlightbackground=self.BORDER_COL
        )
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        tk.Label(
            left_card,
            text="⌨️ Atalho de Voz & Acionamento",
            font=("Segoe UI Semibold", 11),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            left_card,
            text="Escolha um atalho rápido ou grave sua tecla favorita:",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_CARD,
        ).pack(anchor="w")

        hk_row = tk.Frame(left_card, bg=self.BG_CARD)
        hk_row.pack(fill="x", pady=(4, 10))

        preset_labels = [p["label"] for p in HOTKEY_PRESETS]
        self.cmb_hotkey = ttk.Combobox(
            hk_row, values=preset_labels, state="readonly", style="Dark.TCombobox", width=26
        )
        # Seleciona o preset correspondente ou exibe o customizado
        current_codes = self.config.get("hotkey_codes", [0x11, 0x5B])
        matched_preset = next(
            (p["label"] for p in HOTKEY_PRESETS if p["codes"] == current_codes),
            f"Personalizado: {self.config.get('hotkey_label', 'Ctrl + Win')}",
        )
        self.cmb_hotkey.set(matched_preset)
        self.cmb_hotkey.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.cmb_hotkey.bind("<<ComboboxSelected>>", self._on_preset_hotkey_selected)

        self.btn_record_hk = tk.Button(
            hk_row,
            text="⏺ Gravar Tecla",
            font=("Segoe UI Semibold", 9),
            bg=self.ACCENT,
            fg="#FFFFFF",
            activebackground=self.ACCENT_HOVER,
            activeforeground="#FFFFFF",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._start_custom_hotkey_capture,
        )
        self.btn_record_hk.pack(side="right")

        tk.Label(
            left_card,
            text="Comportamento ao pressionar o atalho:",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_CARD,
        ).pack(anchor="w", pady=(2, 4))

        self.mode_map = {
            "Inteligente (Segurar = Push-to-Talk | Toque = Mãos Livres)": "smart",
            "Segurar para Falar (Soltar para transcrever)": "hold",
            "Apertar Ligar / Apertar Desligar (Toggle)": "toggle",
        }
        inv_mode_map = {v: k for k, v in self.mode_map.items()}
        self.cmb_mode = ttk.Combobox(
            left_card,
            values=list(self.mode_map.keys()),
            state="readonly",
            style="Dark.TCombobox",
        )
        self.cmb_mode.set(inv_mode_map.get(self.config.get("hotkey_mode", "smart"), list(self.mode_map.keys())[0]))
        self.cmb_mode.pack(fill="x", pady=(0, 10))
        self.cmb_mode.bind("<<ComboboxSelected>>", lambda e: self._save_ui_settings())

        tk.Label(
            left_card,
            text="Microfone de Entrada:",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_CARD,
        ).pack(anchor="w", pady=(0, 4))

        mic_names = [m["name"] for m in self.mics]
        self.cmb_mic = ttk.Combobox(
            left_card, values=mic_names, state="readonly", style="Dark.TCombobox"
        )
        cur_mic_id = self.config.get("mic_device_id", -1)
        cur_mic_label = next((m["name"] for m in self.mics if m["id"] == cur_mic_id), mic_names[0])
        self.cmb_mic.set(cur_mic_label)
        self.cmb_mic.pack(fill="x", pady=(0, 10))
        self.cmb_mic.bind("<<ComboboxSelected>>", lambda e: self._save_ui_settings())

        tk.Label(
            left_card,
            text="Exibição da Pílula Flutuante:",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_CARD,
        ).pack(anchor="w", pady=(0, 4))

        self.pill_vis_map = {
            "Sempre visível na tela (Pílula Vertical Discreta)": "always",
            "Aparecer somente enquanto estiver gravando/processando": "active_only",
        }
        inv_pill_map = {v: k for k, v in self.pill_vis_map.items()}
        self.cmb_pill_vis = ttk.Combobox(
            left_card,
            values=list(self.pill_vis_map.keys()),
            state="readonly",
            style="Dark.TCombobox",
        )
        self.cmb_pill_vis.set(
            inv_pill_map.get(self.config.get("pill_visibility", "always"), list(self.pill_vis_map.keys())[0])
        )
        self.cmb_pill_vis.pack(fill="x", pady=(0, 8))
        self.cmb_pill_vis.bind("<<ComboboxSelected>>", lambda e: self._save_ui_settings())

        # Indicador do Ctrl + CapsLock e Inicialização com o Windows
        tk.Label(
            left_card,
            text="💡 Dica: Aperte Ctrl + CapsLock a qualquer momento para Pausar/Ativar a ferramenta (libera o CapsLock normal).",
            font=("Segoe UI", 8),
            fg="#A78BFA",
            bg=self.BG_CARD,
            wraplength=340,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        self.var_autostart = tk.BooleanVar(value=bool(self.config.get("start_with_windows", True)))
        chk_autostart = tk.Checkbutton(
            left_card,
            text="Iniciar automaticamente junto com o Windows",
            variable=self.var_autostart,
            font=("Segoe UI Semibold", 9),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
            selectcolor=self.BG_INPUT,
            activebackground=self.BG_CARD,
            activeforeground=self.TEXT_PRIMARY,
            cursor="hand2",
            command=self._save_ui_settings,
        )
        chk_autostart.pack(anchor="w")

        # --- COLUNA DIREITA: Motor Híbrido, IA e Limpeza ---
        right_card = tk.Frame(
            grid_frame, bg=self.BG_CARD, padx=16, pady=14, highlightthickness=1, highlightbackground=self.BORDER_COL
        )
        right_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        tk.Label(
            right_card,
            text="🧠 Motor Híbrido & Limpeza Inteligente",
            font=("Segoe UI Semibold", 11),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            right_card,
            text="Motor de Transcrição:",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_CARD,
        ).pack(anchor="w", pady=(0, 4))

        self.engine_map = {
            "Híbrido (Groq Cloud Grátis + GPU Local GTX 1660 SUPER)": "hybrid",
            "100% Local Offline na Placa de Vídeo (GTX 1660 SUPER)": "local",
            "Apenas Nuvem (Groq Cloud API)": "groq",
        }
        inv_engine_map = {v: k for k, v in self.engine_map.items()}
        self.cmb_engine = ttk.Combobox(
            right_card, values=list(self.engine_map.keys()), state="readonly", style="Dark.TCombobox"
        )
        self.cmb_engine.set(
            inv_engine_map.get(self.config.get("engine_mode", "hybrid"), list(self.engine_map.keys())[0])
        )
        self.cmb_engine.pack(fill="x", pady=(0, 10))
        self.cmb_engine.bind("<<ComboboxSelected>>", lambda e: self._save_ui_settings())

        tk.Label(
            right_card,
            text="Modelo Local na GPU (Faster-Whisper CUDA):",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_CARD,
        ).pack(anchor="w", pady=(0, 4))

        self.local_model_map = {m["label"]: m["id"] for m in LOCAL_MODELS_CATALOG}
        inv_local_model = {v: k for k, v in self.local_model_map.items()}
        self.cmb_local_model = ttk.Combobox(
            right_card, values=list(self.local_model_map.keys()), state="readonly", style="Dark.TCombobox"
        )
        self.cmb_local_model.set(
            inv_local_model.get(
                self.config.get("local_model", "mobiuslabsgmbh/faster-whisper-large-v3-turbo"),
                list(self.local_model_map.keys())[0],
            )
        )
        self.cmb_local_model.pack(fill="x", pady=(0, 10))
        self.cmb_local_model.bind("<<ComboboxSelected>>", lambda e: self._on_local_model_changed())

        tk.Label(
            right_card,
            text="Nível de Limpeza & Formatação Automática:",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_CARD,
        ).pack(anchor="w", pady=(0, 4))

        self.cleanup_map = {
            "Completa (Remove 'ééé', 'tipo', gagueiras, auto-correções e pontua)": "smart_ai",
            "Limpeza Rápida (Remove muletas e palavras repetidas)": "clean_fillers",
            "Literal (Sem filtro — apenas o que o Whisper ouvir)": "raw",
        }
        inv_cleanup = {v: k for k, v in self.cleanup_map.items()}
        self.cmb_cleanup = ttk.Combobox(
            right_card, values=list(self.cleanup_map.keys()), state="readonly", style="Dark.TCombobox"
        )
        self.cmb_cleanup.set(
            inv_cleanup.get(self.config.get("cleanup_level", "smart_ai"), list(self.cleanup_map.keys())[0])
        )
        self.cmb_cleanup.pack(fill="x", pady=(0, 10))
        self.cmb_cleanup.bind("<<ComboboxSelected>>", lambda e: self._save_ui_settings())

        tk.Label(
            right_card,
            text="Estilo de Pontuação / Tom:",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_CARD,
        ).pack(anchor="w", pady=(0, 4))

        self.tone_map = {
            "Natural e Fluido (Qualquer campo de texto)": "natural",
            "Profissional / Formal (E-mails, Docs, Relatórios)": "professional",
            "Mensagem Rápida (WhatsApp / Slack — leve e direto)": "chat",
        }
        inv_tone = {v: k for k, v in self.tone_map.items()}
        self.cmb_tone = ttk.Combobox(
            right_card, values=list(self.tone_map.keys()), state="readonly", style="Dark.TCombobox"
        )
        self.cmb_tone.set(inv_tone.get(self.config.get("writing_tone", "natural"), list(self.tone_map.keys())[0]))
        self.cmb_tone.pack(fill="x", pady=(0, 10))
        self.cmb_tone.bind("<<ComboboxSelected>>", lambda e: self._save_ui_settings())

        # Campo opcional da Groq API Key
        key_header = tk.Frame(right_card, bg=self.BG_CARD)
        key_header.pack(fill="x")
        tk.Label(
            key_header,
            text="Chave Groq Cloud Grátis (Opcional p/ Llama 3.3 70B):",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_CARD,
        ).pack(side="left")

        lbl_link = tk.Label(
            key_header,
            text="Gerar grátis ↗",
            font=("Segoe UI Semibold", 8, "underline"),
            fg="#A78BFA",
            bg=self.BG_CARD,
            cursor="hand2",
        )
        lbl_link.pack(side="right")
        lbl_link.bind("<Button-1>", lambda e: webbrowser.open("https://console.groq.com/keys"))

        key_row = tk.Frame(right_card, bg=self.BG_CARD)
        key_row.pack(fill="x", pady=(4, 0))

        self.ent_groq_key = tk.Entry(
            key_row,
            bg=self.BG_INPUT,
            fg=self.TEXT_PRIMARY,
            insertbackground=self.TEXT_PRIMARY,
            relief="flat",
            font=("Consolas", 9),
            show="•",
        )
        self.ent_groq_key.insert(0, self.config.get("groq_api_key", ""))
        self.ent_groq_key.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))

        tk.Button(
            key_row,
            text="Salvar Chave",
            font=("Segoe UI Semibold", 8),
            bg=self.ACCENT,
            fg="#FFFFFF",
            activebackground=self.ACCENT_HOVER,
            activeforeground="#FFFFFF",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._save_ui_settings,
        ).pack(side="right")

        # --- ÁREA DE TESTE IMEDIATO + HISTÓRICO DE TRANSCRIÇÕES ---
        bottom_card = tk.Frame(
            body, bg=self.BG_CARD, padx=16, pady=12, highlightthickness=1, highlightbackground=self.BORDER_COL
        )
        bottom_card.pack(fill="both", expand=True)

        test_hdr = tk.Frame(bottom_card, bg=self.BG_CARD)
        test_hdr.pack(fill="x", pady=(0, 6))

        tk.Label(
            test_hdr,
            text="🎙️ Campo de Teste Rápido (Clique abaixo, segure seu atalho e fale!)",
            font=("Segoe UI Semibold", 10),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(side="left")

        tk.Button(
            test_hdr,
            text="Copiar Última Transcrição",
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
            bottom_card,
            height=4,
            bg=self.BG_INPUT,
            fg=self.TEXT_PRIMARY,
            insertbackground="#A78BFA",
            relief="flat",
            font=("Segoe UI", 10),
            padx=10,
            pady=8,
            wrap="word",
        )
        self.txt_playground.pack(fill="x", pady=(0, 8))
        self.txt_playground.insert(
            "1.0",
            "Clique aqui, pressione seu atalho (padrão: Ctrl + Win) e fale naturalmente! O texto aparecerá aqui ou em qualquer aplicativo onde seu cursor estiver (WhatsApp, navegador, Word, VS Code...).",
        )
        self.txt_playground.bind("<FocusIn>", self._clear_placeholder_on_focus)
        self._placeholder_active = True

        tk.Label(
            bottom_card,
            text="Últimas falas transcritas e corrigidas:",
            font=("Segoe UI", 9),
            fg=self.TEXT_SECONDARY,
            bg=self.BG_CARD,
        ).pack(anchor="w", pady=(0, 4))

        self.lst_history = tk.Listbox(
            bottom_card,
            bg=self.BG_INPUT,
            fg=self.TEXT_SECONDARY,
            selectbackground=self.ACCENT,
            selectforeground="#FFFFFF",
            relief="flat",
            font=("Segoe UI", 9),
            highlightthickness=0,
            bd=0,
        )
        self.lst_history.pack(fill="both", expand=True)
        self.lst_history.bind("<Double-Button-1>", self._on_history_double_click)
        self._refresh_history_list()

    def _create_stat_box(self, parent: tk.Widget, col: int, title: str, value: str) -> tk.Label:
        padx = (0, 6) if col == 0 else ((6, 6) if col == 1 else (6, 0))
        box = tk.Frame(
            parent, bg=self.BG_CARD, padx=14, pady=10, highlightthickness=1, highlightbackground=self.BORDER_COL
        )
        box.grid(row=0, column=col, sticky="ew", padx=padx)
        tk.Label(
            box, text=title, font=("Segoe UI Semibold", 8), fg=self.TEXT_SECONDARY, bg=self.BG_CARD
        ).pack(anchor="w")
        lbl_val = tk.Label(
            box, text=value, font=("Segoe UI Variable Display", 13, "bold"), fg=self.TEXT_PRIMARY, bg=self.BG_CARD
        )
        lbl_val.pack(anchor="w", pady=(2, 0))
        return lbl_val

    def _clear_placeholder_on_focus(self, event) -> None:
        if self._placeholder_active:
            self.txt_playground.delete("1.0", "end")
            self._placeholder_active = False

    def _on_preset_hotkey_selected(self, event) -> None:
        sel = self.cmb_hotkey.get()
        for preset in HOTKEY_PRESETS:
            if preset["label"] == sel:
                self.config["hotkey_codes"] = preset["codes"]
                # Extrai apenas o nome curto antes do parêntese
                short_label = preset["label"].split(" (")[0].strip()
                self.config["hotkey_label"] = short_label
                self._save_ui_settings()
                break

    def _start_custom_hotkey_capture(self) -> None:
        self.hotkey_listener.set_paused(True)
        self.btn_record_hk.configure(text="Pressione as teclas...", bg=self.WARNING, fg="#000000")

        def _done(codes: List[int], label: str):
            def _ui():
                self.config["hotkey_codes"] = codes
                self.config["hotkey_label"] = label
                self.cmb_hotkey.set(f"Personalizado: {label}")
                self.btn_record_hk.configure(text="⏺ Gravar Tecla", bg=self.ACCENT, fg="#FFFFFF")
                self._save_ui_settings()
                self.hotkey_listener.set_paused(False)
            self.root.after(0, _ui)

        def _cancelled():
            def _ui():
                self.btn_record_hk.configure(text="⏺ Gravar Tecla", bg=self.ACCENT, fg="#FFFFFF")
                self.hotkey_listener.set_paused(False)
            self.root.after(0, _ui)

        capture_custom_hotkey(on_complete=_done, on_cancel=_cancelled)

    def _on_local_model_changed(self) -> None:
        self._save_ui_settings()
        if self.config.get("engine_mode", "hybrid") in ("hybrid", "local"):
            self.transcriber.preload_local_model_async(self.config["local_model"])

    def _save_ui_settings(self) -> None:
        self.config["hotkey_mode"] = self.mode_map.get(self.cmb_mode.get(), "smart")
        self.config["engine_mode"] = self.engine_map.get(self.cmb_engine.get(), "hybrid")
        self.config["local_model"] = self.local_model_map.get(
            self.cmb_local_model.get(), "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
        )
        self.config["cleanup_level"] = self.cleanup_map.get(self.cmb_cleanup.get(), "smart_ai")
        self.config["writing_tone"] = self.tone_map.get(self.cmb_tone.get(), "natural")
        self.config["pill_visibility"] = self.pill_vis_map.get(self.cmb_pill_vis.get(), "always")
        self.config["groq_api_key"] = self.ent_groq_key.get().strip()
        self.config["start_with_windows"] = bool(self.var_autostart.get())
        configure_windows_startup(self.config["start_with_windows"])

        sel_mic_name = self.cmb_mic.get()
        for m in self.mics:
            if m["name"] == sel_mic_name:
                self.config["mic_device_id"] = m["id"]
                self.config["mic_device_name"] = m["name"]
                break

        save_config(self.config)
        hk_label = self.config.get("hotkey_label", "CapsLock")
        is_en = bool(self.config.get("tool_enabled", True))
        self.lbl_stat_shortcut.configure(
            text=hk_label if is_en else f"{hk_label} (Pausado)"
        )
        self.pill.update_preferences(
            hotkey_label=hk_label,
            visibility_mode=self.config.get("pill_visibility", "always"),
            tool_enabled=is_en,
        )

    def _on_master_toggle(self, enabled: bool) -> None:
        """Acionado ao pressionar Ctrl + CapsLock para Ativar ou Desativar a ferramenta."""
        self.config["tool_enabled"] = enabled
        save_config(self.config)
        play_sound_cue(
            "enable_tool" if enabled else "disable_tool",
            enabled=self.config.get("sound_feedback", True),
        )

        def _ui():
            hk_label = self.config.get("hotkey_label", "CapsLock")
            self.lbl_stat_shortcut.configure(
                text=hk_label if enabled else f"{hk_label} (Pausado)"
            )
            self.pill.update_preferences(
                hotkey_label=hk_label,
                visibility_mode=self.config.get("pill_visibility", "always"),
                tool_enabled=enabled,
            )
            if enabled:
                self.pill.set_state("done", "✓ Flow Ativado (CapsLock)", auto_revert_s=1.2)
            else:
                self.pill.set_state("cancelled", "⏸ Flow Desativado (Caps normal)", auto_revert_s=1.4)

        self.root.after(0, _ui)

    def _on_pill_moved(self, new_x: int, new_y: int) -> None:
        self.config["pill_x"] = new_x
        self.config["pill_y"] = new_y
        save_config(self.config)

    def _on_transcriber_status(self, msg: str) -> None:
        self.root.after(0, lambda: self.lbl_engine_status.configure(text=f"● {msg}"))

    # --- FLUXO DE GRAVAÇÃO E TRANSCRIÇÃO ---
    def _on_hotkey_start(self, submode: str) -> None:
        if self._is_processing:
            return
        self._target_hwnd = get_foreground_window()
        mic_id = self.config.get("mic_device_id", -1)
        print(f"[App] Iniciando gravação (submode={submode}, mic={mic_id}, target_hwnd={self._target_hwnd})")
        # Se estiver segurando (hold), desativa auto-stop por silêncio até soltar; se deu toque rápido, ativa auto-stop!
        self.recorder.start(device_id=mic_id, allow_auto_silence_stop=(submode != "hold"))
        play_sound_cue("start", enabled=self.config.get("sound_feedback", True))

        pill_state = "recording_locked" if submode == "toggle" else "recording_hold"
        self.root.after(0, lambda: self.pill.set_state(pill_state))

    def _on_hotkey_locked(self) -> None:
        self.recorder.auto_stop_on_silence = True
        self.root.after(0, lambda: self.pill.set_state("recording_locked"))

    def _on_hotkey_cancel(self) -> None:
        print("[App] Gravação cancelada")
        self.recorder.cancel()
        play_sound_cue("cancel", enabled=self.config.get("sound_feedback", True))
        self.root.after(0, lambda: self.pill.set_state("cancelled", "✕ Ditado cancelado", auto_revert_s=1.0))

    def _trigger_stop_from_ui(self) -> None:
        self.hotkey_listener.notify_recording_stopped_externally()
        self._on_hotkey_stop()

    def _trigger_cancel_from_ui(self) -> None:
        self.hotkey_listener.notify_recording_stopped_externally()
        self._on_hotkey_cancel()

    def _on_hotkey_stop(self) -> None:
        if not self.recorder.is_recording or self._is_processing:
            return

        self._is_processing = True
        play_sound_cue("stop", enabled=self.config.get("sound_feedback", True))
        audio_f32, wav_bytes, duration_s = self.recorder.stop()
        print(f"[App] Parou gravação: duration={duration_s:.2f}s, samples={audio_f32.size}")

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
                print(f"[App] Transcrição ({elapsed:.2f}s, {engine_used}): raw={repr(raw_text)} -> final={repr(final_text)}")

                if not final_text:
                    self.root.after(
                        0,
                        lambda: self.pill.set_state(
                            "cancelled", "Nenhuma fala detectada", auto_revert_s=1.1
                        ),
                    )
                    return

                # Injeta o texto diretamente onde o cursor está!
                ok = inject_text_at_cursor(
                    final_text,
                    restore_clipboard=bool(self.config.get("restore_clipboard", False)),
                    target_hwnd=self._target_hwnd,
                )
                print(f"[App] Texto injetado no cursor (ok={ok}, hwnd={self._target_hwnd})")
                play_sound_cue("done", enabled=self.config.get("sound_feedback", True))

                # Atualiza estatísticas e histórico
                words_count = len(final_text.split())
                self.config["stats_total_words"] = self.config.get("stats_total_words", 0) + words_count
                self.config["stats_total_dictations"] = self.config.get("stats_total_dictations", 0) + 1
                self.config["stats_seconds_recorded"] = round(
                    self.config.get("stats_seconds_recorded", 0.0) + duration_s, 1
                )
                save_config(self.config)
                self.history = add_history_entry(raw_text, final_text, duration_s, engine_used)

                def _update_ui():
                    self.pill.set_state(
                        "done", f"✓ Inserido ({elapsed:.1f}s)", auto_revert_s=1.1
                    )
                    self.lbl_stat_words.configure(text=f"{self.config['stats_total_words']}")
                    self.lbl_stat_speed.configure(text=f"{elapsed:.2f}s • {engine_used}")
                    self._refresh_history_list()

                self.root.after(0, _update_ui)

            except Exception as e:
                print(f"[App] Erro na transcrição: {e}")
                self.root.after(
                    0,
                    lambda: self.pill.set_state(
                        "cancelled", "Erro ao transcrever", auto_revert_s=1.8
                    ),
                )
            finally:
                self._is_processing = False

        threading.Thread(target=_worker, daemon=True).start()

    def _refresh_history_list(self) -> None:
        self.lst_history.delete(0, "end")
        if not self.history:
            self.lst_history.insert("end", "  Nenhuma transcrição ainda — segure seu atalho e fale para começar!")
            return
        for item in self.history[:25]:
            ts = item.get("timestamp", "")
            eng = item.get("engine", "")
            txt = item.get("final_text", "").replace("\n", " ↵ ")
            self.lst_history.insert("end", f" [{ts} • {eng}]  {txt}")

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
                self.pill.set_state("done", "✓ Copiado do histórico!", auto_revert_s=1.0)

    def minimize_to_pill(self) -> None:
        """Oculta a janela de configurações e garante que a pílula flutuante fique visível."""
        self.root.withdraw()
        self.pill.win.deiconify()
        self.pill._apply_non_activating()

    def show_main_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self) -> None:
        self.hotkey_listener.stop()
        self.recorder.cancel()
        self.root.destroy()
        sys.exit(0)


def _ensure_single_instance_and_logging() -> None:
    from pathlib import Path
    import subprocess

    base_dir = Path(__file__).resolve().parent
    log_path = base_dir / "wisprflow.log"
    pid_path = base_dir / "app.pid"

    try:
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    except Exception:
        pass

    if pid_path.exists():
        try:
            old_pid = int(pid_path.read_text(encoding="utf-8").strip())
            if old_pid != os.getpid():
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(old_pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(0.15)
        except Exception:
            pass

    try:
        pid_path.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass


def main():
    _ensure_single_instance_and_logging()
    print(f"[Main] Iniciando Wispr Flow Free (PID={os.getpid()}, args={sys.argv})")
    root = tk.Tk()
    app = WisprFlowFreeApp(root)
    # Se iniciar com argumento --minimized E já tiver uma chave ou motor local, começa direto só com a pílula flutuante
    if "--minimized" in sys.argv:
        if app.config.get("groq_api_key") or app.config.get("engine_mode") == "local":
            root.after(200, app.minimize_to_pill)
        else:
            root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
