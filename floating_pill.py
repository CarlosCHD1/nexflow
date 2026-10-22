import math
import os
import time
import tkinter as tk
from typing import Callable, List, Optional
from PIL import Image, ImageDraw, ImageTk

from win32_utils import make_window_non_activating
from config import get_resource_path

TRANSPARENT_KEY = "#010101"


class FloatingPillOverlay:
    """
    Pílula Flutuante Vertical e Discreta estilo Wispr Flow.
    Compacta, elegante, vertical e não intrusiva.
    Renderizada com supersampling 2x via Pillow para curvas perfeitas
    e configurada com WS_EX_NOACTIVATE para nunca roubar o foco do cursor.
    """

    def __init__(
        self,
        root: tk.Tk,
        get_waveform_bars: Callable[[], List[float]],
        get_recording_duration: Callable[[], float],
        on_open_settings: Callable[[], None],
        on_stop_clicked: Callable[[], None],
        on_cancel_clicked: Callable[[], None],
        on_position_changed: Callable[[int, int], None],
        initial_x: Optional[int] = None,
        initial_y: Optional[int] = None,
        hotkey_label: str = "CapsLock",
        visibility_mode: str = "always",
    ):
        self.root = root
        self.get_waveform_bars = get_waveform_bars
        self.get_recording_duration = get_recording_duration
        self.on_open_settings = on_open_settings
        self.on_stop_clicked = on_stop_clicked
        self.on_cancel_clicked = on_cancel_clicked
        self.on_position_changed = on_position_changed

        self.hotkey_label = hotkey_label
        self.visibility_mode = visibility_mode  # "always" ou "active_only"
        self.tool_enabled = True

        # Estados: "idle", "recording_hold", "recording_locked", "processing", "done", "cancelled"
        self.state = "idle"
        self.status_text = ""
        self._anim_phase = 0.0
        self._state_until = 0.0

        # Carrega o logotipo personalizado para a pílula
        self.logo_img = None
        try:
            logo_p = get_resource_path(os.path.join("assets", "icon_32.png"))
            if logo_p.exists():
                self.logo_img = Image.open(str(logo_p)).convert("RGBA")
        except Exception as e:
            print(f"[Pill] Aviso ao carregar logo da pílula: {e}")

        self.win = tk.Toplevel(self.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=TRANSPARENT_KEY)
        try:
            self.win.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
        except Exception:
            pass

        # Dimensões verticais compactas
        self.width = 44
        self.height = 144
        self.canvas = tk.Canvas(
            self.win,
            width=self.width,
            height=self.height,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # Posicionamento inicial (dock lateral discreto à direita da tela)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        default_x = screen_w - self.width - 24
        default_y = (screen_h - self.height) // 2

        self.pos_x = initial_x if initial_x is not None else default_x
        self.pos_y = initial_y if initial_y is not None else default_y

        # Garante que as coordenadas fiquem visíveis na tela
        self.pos_x = max(0, min(screen_w - self.width, self.pos_x))
        self.pos_y = max(0, min(screen_h - self.height, self.pos_y))

        self.win.geometry(f"{self.width}x{self.height}+{self.pos_x}+{self.pos_y}")

        # Suporte a arrastar a pílula e cliques
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._dragged = False
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<ButtonRelease-3>", lambda e: self.on_open_settings())

        self._tk_img: Optional[ImageTk.PhotoImage] = None
        self.win.update_idletasks()
        self._apply_non_activating()

        if self.visibility_mode == "always":
            self.win.deiconify()
            self._apply_non_activating()

        self._tick()

    def _apply_non_activating(self) -> None:
        try:
            hwnd = int(self.win.wm_frame(), 16) if self.win.wm_frame() != "0x0" else self.win.winfo_id()
            make_window_non_activating(hwnd)
            make_window_non_activating(self.win.winfo_id())
        except Exception:
            pass

    def update_preferences(self, hotkey_label: str, visibility_mode: str, tool_enabled: bool = True) -> None:
        self.hotkey_label = hotkey_label
        self.visibility_mode = visibility_mode
        self.tool_enabled = tool_enabled
        if self.state == "idle":
            if self.visibility_mode == "always":
                self.win.deiconify()
                self._apply_non_activating()
            else:
                self.win.withdraw()

    def set_state(self, state: str, status_text: str = "", auto_revert_s: float = 0.0) -> None:
        self.state = state
        self.status_text = status_text
        if auto_revert_s > 0:
            self._state_until = time.perf_counter() + auto_revert_s
        else:
            self._state_until = 0.0

        if state == "idle" and self.visibility_mode == "active_only":
            self.win.withdraw()
        else:
            self.win.deiconify()
            self.win.attributes("-topmost", True)
            self._apply_non_activating()

    def _on_mouse_down(self, event) -> None:
        self._drag_start_x = event.x_root - self.pos_x
        self._drag_start_y = event.y_root - self.pos_y
        self._dragged = False

    def _on_mouse_drag(self, event) -> None:
        new_x = event.x_root - self._drag_start_x
        new_y = event.y_root - self._drag_start_y
        if abs(new_x - self.pos_x) > 3 or abs(new_y - self.pos_y) > 3:
            self._dragged = True
            self.pos_x = new_x
            self.pos_y = new_y
            self.win.geometry(f"{self.width}x{self.height}+{self.pos_x}+{self.pos_y}")

    def _on_mouse_up(self, event) -> None:
        if self._dragged:
            self.on_position_changed(self.pos_x, self.pos_y)
            return

        # Clique sem arrastar
        if self.state in ("recording_hold", "recording_locked"):
            # Se clicou na parte inferior do botão X de cancelar
            if event.y >= self.height - 30:
                self.on_cancel_clicked()
            else:
                self.on_stop_clicked()
        elif self.state == "idle":
            self.on_open_settings()

    def _tick(self) -> None:
        now = time.perf_counter()
        if self._state_until > 0 and now >= self._state_until:
            self._state_until = 0.0
            self.set_state("idle")

        self._anim_phase += 0.16
        if self.win.winfo_viewable():
            self._render_frame()

        delay_ms = 33 if self.state != "idle" else 120
        self.root.after(delay_ms, self._tick)

    def _render_frame(self) -> None:
        scale = 2
        W = self.width * scale
        H = self.height * scale
        cx = W // 2
        cy = H // 2

        img = Image.new("RGBA", (W, H), (1, 1, 1, 0))
        draw = ImageDraw.Draw(img)

        # ----------------------------------------------------
        # ESTADO 1: IDLE (Pílula Vertical Super Discreta)
        # ----------------------------------------------------
        if self.state == "idle":
            is_enabled = getattr(self, "tool_enabled", True)
            pw = 30 * scale
            ph = 76 * scale
            x0 = cx - pw // 2
            y0 = cy - ph // 2
            x1 = x0 + pw
            y1 = y0 + ph
            radius = pw // 2

            # Fundo escuro fosco elegante com borda fina
            border_color = (58, 62, 82, 230) if is_enabled else (125, 85, 35, 230)
            draw.rounded_rectangle(
                [x0, y0, x1, y1],
                radius=radius,
                fill=(16, 17, 24, 245),
                outline=border_color,
                width=2,
            )

            # Ponto indicador no topo (violeta pulsante se ativo, âmbar se pausado)
            dot_y = y0 + 15 * scale
            dot_r = 4.0 * scale
            if is_enabled:
                pulse = int(35 * math.sin(self._anim_phase * 0.6))
                # Halo suave
                draw.ellipse(
                    [cx - dot_r - 2, dot_y - dot_r - 2, cx + dot_r + 2, dot_y + dot_r + 2],
                    fill=(139, 92, 246, 70 + max(0, pulse * 2)),
                )
                draw.ellipse(
                    [cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r],
                    fill=(168 + max(0, pulse), 139, 250, 255),
                )
            else:
                draw.ellipse(
                    [cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r],
                    fill=(245, 158, 11, 255),
                )

            # Logotipo central moderno no estado de repouso (ou barras de áudio se ausente)
            if self.logo_img:
                logo_sz = int(18 * scale)
                logo_resized = self.logo_img.resize((logo_sz, logo_sz), Image.Resampling.LANCZOS)
                if not is_enabled:
                    r, g, b, a = logo_resized.split()
                    a = a.point(lambda p: int(p * 0.4))
                    logo_resized = Image.merge("RGBA", (r, g, b, a))
                img.paste(logo_resized, (int(cx - logo_sz / 2), int(cy - logo_sz / 2)), logo_resized)
            else:
                bar_w = 2.2 * scale
                bar_gap = 2.5 * scale
                bar_mid_h = 13 * scale
                bar_side_h = 7 * scale
                icon_col = (148, 163, 184, 220) if is_enabled else (160, 140, 110, 180)

                # Barra esquerda
                bx_l = cx - bar_w - bar_gap
                draw.rounded_rectangle(
                    [bx_l - bar_w / 2, cy - bar_side_h / 2, bx_l + bar_w / 2, cy + bar_side_h / 2],
                    radius=bar_w / 2,
                    fill=icon_col,
                )
                # Barra central
                draw.rounded_rectangle(
                    [cx - bar_w / 2, cy - bar_mid_h / 2, cx + bar_w / 2, cy + bar_mid_h / 2],
                    radius=bar_w / 2,
                    fill=icon_col,
                )
                # Barra direita
                bx_r = cx + bar_w + bar_gap
                draw.rounded_rectangle(
                    [bx_r - bar_w / 2, cy - bar_side_h / 2, bx_r + bar_w / 2, cy + bar_side_h / 2],
                    radius=bar_w / 2,
                    fill=icon_col,
                )

            # Indicador inferior sutil
            bot_y = y1 - 15 * scale
            if is_enabled:
                sub_r = 1.8 * scale
                draw.ellipse(
                    [cx - sub_r, bot_y - sub_r, cx + sub_r, bot_y + sub_r],
                    fill=(100, 116, 139, 180),
                )
            else:
                # Sinal de pausa ||
                pw_p = 1.5 * scale
                ph_p = 6 * scale
                draw.rectangle([cx - 3 * scale, bot_y - ph_p / 2, cx - 3 * scale + pw_p, bot_y + ph_p / 2], fill=(245, 158, 11, 200))
                draw.rectangle([cx + 1.5 * scale, bot_y - ph_p / 2, cx + 1.5 * scale + pw_p, bot_y + ph_p / 2], fill=(245, 158, 11, 200))

        # ----------------------------------------------------
        # ESTADO 2: GRAVANDO (Vertical Waveform Ativo)
        # ----------------------------------------------------
        elif self.state in ("recording_hold", "recording_locked"):
            is_locked = self.state == "recording_locked"
            pw = 36 * scale
            ph = 136 * scale
            x0 = cx - pw // 2
            y0 = cy - ph // 2
            x1 = x0 + pw
            y1 = y0 + ph
            radius = pw // 2

            border_color = (56, 189, 248, 255) if is_locked else (168, 85, 247, 255)
            glow_color = (56, 189, 248, 60) if is_locked else (168, 85, 247, 60)

            # Borda com brilho neon suave
            draw.rounded_rectangle(
                [x0 - 1, y0 - 1, x1 + 1, y1 + 1],
                radius=radius + 1,
                outline=glow_color,
                width=3,
            )
            draw.rounded_rectangle(
                [x0, y0, x1, y1],
                radius=radius,
                fill=(14, 15, 23, 250),
                outline=border_color,
                width=2,
            )

            # Topo: Ponto gravando piscante
            rec_y = y0 + 16 * scale
            rec_r = 4.0 * scale
            pulse_rec = int(30 * math.sin(self._anim_phase * 1.8))
            rec_color = (56, 189, 248, 255) if is_locked else (244, 63, 94, 255)
            draw.ellipse(
                [cx - rec_r - 2, rec_y - rec_r - 2, cx + rec_r + 2, rec_y + rec_r + 2],
                fill=(rec_color[0], rec_color[1], rec_color[2], 90 + max(0, pulse_rec * 2)),
            )
            draw.ellipse(
                [cx - rec_r, rec_y - rec_r, cx + rec_r, rec_y + rec_r],
                fill=rec_color,
            )

            # Centro: Espectro de Ondas Verticais (7 barras horizontais que expandem com a voz)
            bars = self.get_waveform_bars()
            num_display_bars = 7
            bar_h = 3.2 * scale
            bar_gap = 4.0 * scale
            total_wave_h = num_display_bars * bar_h + (num_display_bars - 1) * bar_gap
            wave_top_y = cy - total_wave_h / 2 + 3 * scale

            for i in range(num_display_bars):
                b_val = bars[i] if i < len(bars) else 0.1
                wave_mod = 0.08 * abs(math.sin(self._anim_phase * 1.5 + i * 0.6))
                lvl = min(1.0, max(0.12, b_val + wave_mod))

                # Largura horizontal da barra expande simetricamente do centro
                bar_w_half = (3.5 + lvl * 10.5) * scale
                by0 = wave_top_y + i * (bar_h + bar_gap)
                by1 = by0 + bar_h

                # Gradiente de cor da barra
                if is_locked:
                    bar_fill = (56, 189, 248, 255) if lvl < 0.55 else (186, 230, 253, 255)
                else:
                    bar_fill = (192, 132, 252, 255) if lvl < 0.55 else (245, 208, 254, 255)

                draw.rounded_rectangle(
                    [cx - bar_w_half, by0, cx + bar_w_half, by1],
                    radius=bar_h / 2,
                    fill=bar_fill,
                )

            # Base: Botão sutil de Cancelar (X)
            btn_y = y1 - 18 * scale
            btn_r = 7.5 * scale
            draw.ellipse(
                [cx - btn_r, btn_y - btn_r, cx + btn_r, btn_y + btn_r],
                fill=(34, 37, 50, 255),
            )
            off = 2.8 * scale
            draw.line([cx - off, btn_y - off, cx + off, btn_y + off], fill=(160, 168, 190, 255), width=int(1.8 * scale))
            draw.line([cx - off, btn_y + off, cx + off, btn_y - off], fill=(160, 168, 190, 255), width=int(1.8 * scale))

        # ----------------------------------------------------
        # ESTADO 3: PROCESSANDO (Orbital IA Suave)
        # ----------------------------------------------------
        elif self.state == "processing":
            pw = 34 * scale
            ph = 96 * scale
            x0 = cx - pw // 2
            y0 = cy - ph // 2
            x1 = x0 + pw
            y1 = y0 + ph
            radius = pw // 2

            draw.rounded_rectangle(
                [x0, y0, x1, y1],
                radius=radius,
                fill=(15, 17, 26, 248),
                outline=(99, 102, 241, 255),
                width=2,
            )

            # Spinner orbital vertical
            spin_r = 8.5 * scale
            for i in range(8):
                ang = self._anim_phase * 1.8 + i * (math.pi / 4)
                px = cx + int(spin_r * math.cos(ang))
                py = cy + int(spin_r * math.sin(ang))
                alpha = int(60 + 195 * ((i + 1) / 8.0))
                pr = 1.8 * scale if i < 6 else 2.6 * scale
                draw.ellipse(
                    [px - pr, py - pr, px + pr, py + pr],
                    fill=(165, 180, 252, alpha),
                )

        # ----------------------------------------------------
        # ESTADO 4: CONCLUÍDO OU CANCELADO
        # ----------------------------------------------------
        elif self.state in ("done", "cancelled"):
            is_ok = self.state == "done"
            pw = 32 * scale
            ph = 76 * scale
            x0 = cx - pw // 2
            y0 = cy - ph // 2
            x1 = x0 + pw
            y1 = y0 + ph
            radius = pw // 2

            outline_col = (52, 211, 153, 255) if is_ok else (248, 113, 113, 255)
            draw.rounded_rectangle(
                [x0, y0, x1, y1],
                radius=radius,
                fill=(15, 20, 24, 250),
                outline=outline_col,
                width=2,
            )

            if is_ok:
                # Checkmark ✓ desenhado vetorizado nítido
                p1 = (cx - 5.5 * scale, cy + 0.5 * scale)
                p2 = (cx - 1.5 * scale, cy + 4.5 * scale)
                p3 = (cx + 6.0 * scale, cy - 3.5 * scale)
                draw.line([p1, p2], fill=(52, 211, 153, 255), width=int(2.2 * scale))
                draw.line([p2, p3], fill=(52, 211, 153, 255), width=int(2.2 * scale))
            else:
                # X cancelado
                off = 4.0 * scale
                draw.line([cx - off, cy - off, cx + off, cy + off], fill=(248, 113, 113, 255), width=int(2.0 * scale))
                draw.line([cx - off, cy + off, cx + off, cy - off], fill=(248, 113, 113, 255), width=int(2.0 * scale))

        # Redimensiona com filtro LANCZOS para curvas e linhas perfeitas
        final_img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)

        # Compõe sobre a cor chave transparente do Windows
        bg_img = Image.new("RGB", (self.width, self.height), (1, 1, 1))
        mask = final_img.split()[3].point(lambda a: 255 if a > 120 else 0)
        bg_img.paste(final_img.convert("RGB"), (0, 0), mask)

        self._tk_img = ImageTk.PhotoImage(bg_img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._tk_img, anchor="nw")

        # Texto de tempo no topo durante a gravação
        if self.state in ("recording_hold", "recording_locked"):
            dur = int(self.get_recording_duration())
            mins, secs = divmod(dur, 60)
            time_str = f"{secs}" if mins == 0 else f"{mins}:{secs:02d}"
            # Exibe os segundos de forma minimalista abaixo do ponto gravando
            self.canvas.create_text(
                self.width // 2,
                self.height // 2 - 38,
                text=time_str,
                fill="#94A3B8",
                font=("Segoe UI Semibold", 8),
            )
