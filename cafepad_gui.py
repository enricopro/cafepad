#!/usr/bin/env python3
"""
======================================================================
  CaféPad Desktop GUI — Nintendo Wii U Pro Controller Manager
  Minimalist, Card-First Desktop Interface & Hardware Diagnostics
  (Continuous Curvature, Tactile Pills & Modern Typography)
======================================================================
"""

import sys
import os
import time
import math
import threading
import subprocess
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageDraw

# Core driver integration
from cafepad import (
    PlayerWorker,
    WiiUProController,
    load_saved_macs,
    save_mac,
    remove_mac,
    scan_for_controller,
    get_agent_manager,
    load_config,
    save_config_key,
    __version__,
)

# ====================================================================
# "Warm Modern Slate" Design Tokens (Dieter Rams & Human Interface System)
# ====================================================================
BG_BASE = "#121316"          # Deep warm charcoal base
BG_CARD = "#1a1c22"          # Elevated device cards
BG_CARD_HOVER = "#21242d"    # Card hover highlight
BG_SURFACE = "#252833"       # Inset buttons & secondary surfaces
BG_SURFACE_HOVER = "#2e3240" # Button hover
BG_INSET = "#0c0d10"         # Recessed wells and segmented tracks

BORDER = "#252730"           # 1px structural border
BORDER_FOCUS = "#3d4252"     # Subtle card border highlight

TEXT_PRIMARY = "#f4f5f8"     # Crisp, readable high-contrast white
TEXT_SECONDARY = "#9ba1b0"   # Neutral slate for metadata
TEXT_MUTED = "#5a6070"       # Faint helper captions & timestamps

ACCENT_BRAND = "#e07a38"     # Warm espresso / roasted amber brand accent
ACCENT_BLUE = "#3b82f6"      # Primary action blue
ACCENT_BLUE_HOVER = "#60a5fa"
ACCENT_GREEN = "#10b981"     # Online status & healthy battery
ACCENT_AMBER = "#f59e0b"     # Low battery & rumble feedback
ACCENT_RED = "#ef4444"       # Disconnect / forget device
ACCENT_CYAN = "#00f0ff"      # Live diagnostic crosshairs

PLAYER_ACCENTS = ["#00f0ff", "#f43f5e", "#10b981", "#f59e0b"]
PLAYER_BGS = ["#0e1726", "#261217", "#0e241b", "#261c0e"]
PLAYER_BORDERS = ["#1d2e4a", "#4a1c26", "#16452f", "#4a3316"]


# ====================================================================
# Modern Typography Tokens (Montserrat & Cantarell/Noto Sans)
# ====================================================================
def _resolve_best_font(preferred_list, default="sans-serif"):
    try:
        available = tkfont.families()
        for f in preferred_list:
            if f in available:
                return f
    except Exception:
        pass
    return default

# Font hierarchy
FONT_TITLE = _resolve_best_font(["Montserrat", "Cantarell", "Noto Sans", "Liberation Sans"], "sans-serif")
FONT_BODY = _resolve_best_font(["Cantarell", "Noto Sans", "Liberation Sans", "DejaVu Sans"], "sans-serif")


# ====================================================================
# Image Rendering & Caching for Antialiased Rounded Shapes
# ====================================================================
_IMG_CACHE = {}

def get_assets_dir():
    """
    Locates the assets directory robustly, handling symlinks (e.g. ~/.local/bin/cafepad-gui),
    installed data directories, and developer workspaces.
    """
    candidates = [
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "assets"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"),
        "/usr/local/share/cafepad/assets",
        "/usr/share/cafepad/assets",
        os.path.expanduser("~/.local/share/cafepad/assets"),
        os.path.expanduser("~/Documents/workspace/cafepad/assets"),
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "assets"),
    ]
    for cand in candidates:
        if os.path.isdir(cand) and (
            os.path.exists(os.path.join(cand, "brand_lockup.png"))
            or os.path.exists(os.path.join(cand, "icon-128.png"))
        ):
            return cand
    return candidates[0]


def get_rounded_rect_img(w, h, r, bg_hex, fill_hex, border_hex=None, border_w=1):
    """Generates an antialiased rounded pill/rectangle background image."""
    key = (w, h, r, bg_hex, fill_hex, border_hex, border_w)
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]
    scale = 3  # 3x supersampling for silky-smooth curved corners
    img = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [1, 1, w * scale - 2, h * scale - 2],
        radius=r * scale,
        fill=fill_hex,
        outline=border_hex,
        width=border_w * scale if border_hex else 0
    )
    img = img.resize((w, h), Image.Resampling.LANCZOS)
    pimg = ImageTk.PhotoImage(img)
    _IMG_CACHE[key] = pimg
    return pimg


def draw_canvas_rounded_rect(canvas, x1, y1, x2, y2, r=6, **kwargs):
    """Draws a smooth rounded rectangle directly on a Tkinter Canvas."""
    pts = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kwargs)


# ====================================================================
# Reusable Rounded Components: Badges, Buttons, and Surface Cards
# ====================================================================
class PillBadge(tk.Label):
    """
    Tactile, antialiased rounded pill badge / chip for status, player slots,
    and metadata indicators (Apple HIG / Material 3 chip design).
    """
    def __init__(
        self,
        parent,
        text="",
        bg=BG_CARD,
        badge_bg=BG_SURFACE,
        border=BORDER,
        fg=TEXT_PRIMARY,
        font=None,
        padx=10,
        height=24,
        radius=None,
        **kwargs
    ):
        self.parent_bg = bg
        self.badge_bg = badge_bg
        self.border_col = border
        self.badge_fg = fg
        self.badge_font = font or (FONT_TITLE, 8, "bold")
        self.pad_x = padx
        self.badge_h = height
        self.badge_r = radius if radius is not None else (height // 2)
        self.badge_text = text
        super().__init__(
            parent,
            bg=bg,
            font=self.badge_font,
            compound="center",
            bd=0,
            highlightthickness=0,
            **kwargs
        )
        self._update()

    def _update(self):
        f = tkfont.Font(font=self.badge_font)
        text_w = f.measure(self.badge_text)
        w = max(self.badge_h, text_w + self.pad_x * 2)
        img = get_rounded_rect_img(w, self.badge_h, self.badge_r, self.parent_bg, self.badge_bg, self.border_col)
        self._img = img
        super().configure(image=img, text=self.badge_text, fg=self.badge_fg)

    def configure(self, **kwargs):
        if "text" in kwargs:
            self.badge_text = kwargs.pop("text")
        if "fg" in kwargs:
            self.badge_fg = kwargs.pop("fg")
        if "badge_bg" in kwargs:
            self.badge_bg = kwargs.pop("badge_bg")
        if "border" in kwargs:
            self.border_col = kwargs.pop("border")
        if "bg" in kwargs:
            self.parent_bg = kwargs.pop("bg")
            super().configure(bg=self.parent_bg)
        if kwargs:
            super().configure(**kwargs)
        self._update()


class PillButton(tk.Label):
    """
    Tactile, antialiased rounded pill button supporting hover, click,
    disabled states, and dynamic label updates.
    """
    def __init__(
        self,
        parent,
        text="",
        command=None,
        bg=BG_BASE,
        btn_bg=BG_SURFACE,
        btn_hover=BG_SURFACE_HOVER,
        btn_press=BG_INSET,
        border="#2b2f3d",
        fg=TEXT_PRIMARY,
        font=None,
        padx=14,
        height=30,
        radius=None,
        state="normal",
        **kwargs
    ):
        self.parent = parent
        self.parent_bg = bg
        self.btn_bg = btn_bg
        self.btn_hover = btn_hover
        self.btn_press = btn_press
        self.btn_border = border
        self.btn_fg = fg
        self.btn_font = font or (FONT_TITLE, 9, "bold")
        self.btn_padx = padx
        self.btn_h = height
        self.btn_r = radius if radius is not None else (height // 2)
        self.command = command
        self._state = state
        self._is_hovered = False
        self._is_pressed = False
        self.btn_text = text

        super().__init__(
            parent,
            bg=self.parent_bg,
            font=self.btn_font,
            compound="center",
            bd=0,
            highlightthickness=0,
            takefocus=1 if state == "normal" else 0,
            **kwargs
        )
        self._update_appearance()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<KeyPress-space>", lambda e: self._trigger_command())
        self.bind("<KeyPress-Return>", lambda e: self._trigger_command())

    def _update_appearance(self):
        f = tkfont.Font(font=self.btn_font)
        text_w = f.measure(self.btn_text)
        btn_w = max(self.btn_h, text_w + self.btn_padx * 2)

        if self._state == "disabled":
            fill = "#181a22"
            border = "#20232d"
            txt_fg = TEXT_MUTED
            cur = "arrow"
        elif self._is_pressed:
            fill = self.btn_press
            border = self.btn_border
            txt_fg = self.btn_fg
            cur = "hand2"
        elif self._is_hovered:
            fill = self.btn_hover
            border = "#3d4255"
            txt_fg = self.btn_fg
            cur = "hand2"
        else:
            fill = self.btn_bg
            border = self.btn_border
            txt_fg = self.btn_fg
            cur = "hand2"

        img = get_rounded_rect_img(btn_w, self.btn_h, self.btn_r, self.parent_bg, fill, border)
        self._current_img = img
        super().configure(image=img, text=self.btn_text, fg=txt_fg, cursor=cur)

    def configure(self, **kwargs):
        if "text" in kwargs:
            self.btn_text = kwargs.pop("text")
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            super().configure(takefocus=1 if self._state == "normal" else 0)
        if "command" in kwargs:
            self.command = kwargs.pop("command")
        if "font" in kwargs:
            self.btn_font = kwargs.pop("font")
        if "fg" in kwargs:
            self.btn_fg = kwargs.pop("fg")
        if "bg" in kwargs:
            self.parent_bg = kwargs.pop("bg")
            super().configure(bg=self.parent_bg)
        if "btn_bg" in kwargs:
            self.btn_bg = kwargs.pop("btn_bg")
        if "btn_hover" in kwargs:
            self.btn_hover = kwargs.pop("btn_hover")
        if "btn_press" in kwargs:
            self.btn_press = kwargs.pop("btn_press")
        if "border" in kwargs:
            self.btn_border = kwargs.pop("border")
        if kwargs:
            super().configure(**kwargs)
        self._update_appearance()

    def _on_enter(self, e):
        if self._state != "disabled":
            self._is_hovered = True
            self._update_appearance()

    def _on_leave(self, e):
        self._is_hovered = False
        self._is_pressed = False
        self._update_appearance()

    def _on_press(self, e):
        if self._state != "disabled":
            self._is_pressed = True
            self._update_appearance()

    def _on_release(self, e):
        if self._state != "disabled" and self._is_pressed:
            self._is_pressed = False
            self._update_appearance()
            if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
                self._trigger_command()

    def _trigger_command(self):
        if self._state != "disabled" and self.command:
            self.command()


class RoundedCard(tk.Canvas):
    """
    Continuous-curvature elevated hardware surface card.
    Draws antialiased 18px-24px rounded corners with subtle border highlight
    and hosts inner widgets via a native child window.
    """
    def __init__(
        self,
        parent,
        bg_base=BG_BASE,
        card_bg=BG_CARD,
        border_col=BORDER,
        radius=18,
        padx=18,
        pady=16,
        auto_height=True,
        auto_width=False,
        min_height=0,
        min_width=0,
        **kwargs
    ):
        super().__init__(parent, bg=bg_base, bd=0, highlightthickness=0, **kwargs)
        self.bg_base = bg_base
        self.card_bg = card_bg
        self.border_col = border_col
        self.radius = radius
        self.pad_x = padx
        self.pad_y = pady
        self.auto_height = auto_height
        self.auto_width = auto_width
        self.min_height = min_height
        self.min_width = min_width
        self._img_ref = None

        self.inner = tk.Frame(self, bg=card_bg)
        self.window_id = self.create_window(padx, pady, window=self.inner, anchor="nw")

        if self.auto_height or self.auto_width:
            self.inner.bind("<Configure>", self._on_inner_configure, add="+")
        self.bind("<Configure>", self._on_card_configure)

    def _on_inner_configure(self, event=None):
        changes = {}
        if self.auto_height:
            req_h = max(self.min_height, self.inner.winfo_reqheight() + self.pad_y * 2)
            if req_h != self.winfo_height() and req_h > self.pad_y * 2:
                changes["height"] = req_h
        if self.auto_width:
            req_w = max(self.min_width, self.inner.winfo_reqwidth() + self.pad_x * 2)
            if req_w != self.winfo_width() and req_w > self.pad_x * 2:
                changes["width"] = req_w
        if changes:
            self.configure(**changes)

    def _on_card_configure(self, event):
        w = event.width
        h = event.height
        if w < 10 or h < 10:
            return
        inner_w = max(10, w - self.pad_x * 2)
        inner_h = max(10, h - self.pad_y * 2)

        window_cfg = {}
        if not self.auto_height:
            window_cfg["height"] = inner_h
        if not self.auto_width:
            window_cfg["width"] = inner_w
        if window_cfg:
            self.itemconfigure(self.window_id, **window_cfg)

        if (w, h) == getattr(self, "_last_drawn_size", None):
            return
        self._last_drawn_size = (w, h)

        img = get_rounded_rect_img(w, h, self.radius, self.bg_base, self.card_bg, self.border_col)
        self._img_ref = img
        self.delete("card_bg")
        self.create_image(0, 0, image=self._img_ref, anchor="nw", tags="card_bg")
        self.tag_lower("card_bg")


# ====================================================================
# Main Application Controller
# ====================================================================
class CafePadGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CaféPad — Wii U Pro Controller on Linux")
        self.root.geometry("780x570")
        self.root.minsize(700, 480)
        self.root.configure(bg=BG_BASE)

        self.workers = {}          # slot (int) -> PlayerWorker
        self.current_view = "home" # "home", "diagnostics", "pairing", "settings"
        self.diag_player_id = 0    # Currently inspected player in diagnostic sheet
        self.scanning = False
        self.card_views = {}
        self._rendered_macs = []

        cfg = load_config()
        self.nintendo_layout = bool(cfg.get("nintendo_layout", False))
        self.autostart_active = self._check_autostart_status()

        # Pre-load brand logo assets in various sizes
        self._hdr_icon = None
        self._card_icon = None
        self._hero_icon = None
        self._wizard_icon = None
        self._brand_lockup_img = None
        try:
            assets_dir = get_assets_dir()
            icon_path = os.path.join(assets_dir, "icon-128.png")
            lockup_path = os.path.join(assets_dir, "brand_lockup.png")

            if os.path.exists(lockup_path):
                self._brand_lockup_img = ImageTk.PhotoImage(Image.open(lockup_path))

            if os.path.exists(icon_path):
                self._icon_photo = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, self._icon_photo)

                pil_orig = Image.open(icon_path)
                self._hdr_icon = ImageTk.PhotoImage(pil_orig.resize((70, 70), Image.Resampling.LANCZOS))
                self._card_icon = ImageTk.PhotoImage(pil_orig.resize((42, 42), Image.Resampling.LANCZOS))
                self._hero_icon = ImageTk.PhotoImage(pil_orig.resize((84, 84), Image.Resampling.LANCZOS))
                self._wizard_icon = ImageTk.PhotoImage(pil_orig.resize((60, 60), Image.Resampling.LANCZOS))
        except Exception as e:
            sys.stderr.write(f"[CaféPad GUI] Warning loading assets: {e}\n")

        # Ensure BlueZ automated reverse-MAC agent is active for Nintendo pairing
        get_agent_manager().start()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Main Layout Container
        self.container = tk.Frame(self.root, bg=BG_BASE)
        self.container.pack(fill="both", expand=True)

        self._build_header()
        self._build_content_area()
        self._build_footer()

        self._start_controller_workers()
        self._show_home_view()

        # Start non-blocking UI update loop
        self._update_loop()

    # ================================================================
    # Structural Layout: Header & Footer
    # ================================================================
    def _build_header(self):
        self.header = tk.Frame(self.container, bg=BG_BASE, padx=24, pady=14)
        self.header.pack(fill="x")

        # Left: Tactile App Branding with Unified Logo + Title Lockup
        brand_frame = tk.Frame(self.header, bg=BG_BASE)
        brand_frame.pack(side="left")

        if self._brand_lockup_img:
            lbl_brand = tk.Label(
                brand_frame,
                image=self._brand_lockup_img,
                bg=BG_BASE,
                cursor="hand2",
                bd=0,
                highlightthickness=0,
            )
            lbl_brand.pack(side="left")
            lbl_brand.bind("<Button-1>", lambda e: self._show_home_view())
        else:
            if self._hdr_icon:
                lbl_icon = tk.Label(brand_frame, image=self._hdr_icon, bg=BG_BASE, cursor="hand2")
                lbl_icon.pack(side="left", padx=(0, 16))
                lbl_icon.bind("<Button-1>", lambda e: self._show_home_view())

            titles = tk.Frame(brand_frame, bg=BG_BASE)
            titles.pack(side="left")

            lbl_app_name = tk.Label(
                titles,
                text="CaféPad",
                font=(FONT_TITLE, 22, "bold"),
                fg=TEXT_PRIMARY,
                bg=BG_BASE,
                cursor="hand2",
            )
            lbl_app_name.pack(anchor="w")
            lbl_app_name.bind("<Button-1>", lambda e: self._show_home_view())

            tk.Label(
                titles,
                text="Wii U Pro Controller on Linux",
                font=(FONT_BODY, 14),
                fg=TEXT_SECONDARY,
                bg=BG_BASE,
            ).pack(anchor="w")

        # Right: Quick Global Actions
        self.hdr_actions = tk.Frame(self.header, bg=BG_BASE)
        self.hdr_actions.pack(side="right")

        self.btn_pair = PillButton(
            self.hdr_actions,
            text="＋ Pair Controller",
            bg=BG_BASE,
            btn_bg=ACCENT_BLUE,
            btn_hover=ACCENT_BLUE_HOVER,
            btn_press="#2563eb",
            border="#3b82f6",
            fg="#ffffff",
            font=(FONT_TITLE, 9, "bold"),
            padx=16,
            height=34,
            radius=17,
            command=self._start_pairing_flow,
        )
        self.btn_pair.pack(side="right", padx=(8, 0))

        self.btn_settings = PillButton(
            self.hdr_actions,
            text="⚙ Settings",
            bg=BG_BASE,
            btn_bg=BG_SURFACE,
            btn_hover=BG_SURFACE_HOVER,
            btn_press=BG_INSET,
            border="#2e3342",
            fg=TEXT_SECONDARY,
            font=(FONT_TITLE, 9, "bold"),
            padx=14,
            height=34,
            radius=17,
            command=self._toggle_settings_view,
        )
        self.btn_settings.pack(side="right")

    def _build_content_area(self):
        self.content_frame = tk.Frame(self.container, bg=BG_BASE, padx=24, pady=0)
        self.content_frame.pack(fill="both", expand=True)

    def _build_footer(self):
        self.footer = tk.Frame(self.container, bg=BG_BASE, padx=24, pady=6)
        self.footer.pack(fill="x", side="bottom")

        self.lbl_footer_status = tk.Label(
            self.footer,
            text="",
            font=(FONT_BODY, 9),
            fg=TEXT_SECONDARY,
            bg=BG_BASE,
        )
        self.lbl_footer_status.pack(side="left")

    # ================================================================
    # View 1: Card-First Home View (My Controllers)
    # ================================================================
    def _show_home_view(self):
        self.current_view = "home"
        for w in self.content_frame.winfo_children():
            w.destroy()

        self.btn_pair.configure(state="normal")
        self.btn_settings.configure(text="⚙ Settings")

        macs = load_saved_macs()

        # If zero controllers are paired, show welcoming tactile empty state
        if not macs:
            self._render_empty_state()
            return

        # Section Header Row
        hdr_row = tk.Frame(self.content_frame, bg=BG_BASE)
        hdr_row.pack(fill="x", pady=(0, 10))

        conn_count = sum(1 for w in self.workers.values() if w.controller.connected)
        count_str = f"{conn_count} Active" if conn_count > 0 else "All Sleeping"

        tk.Label(
            hdr_row,
            text="MY CONTROLLERS",
            font=(FONT_TITLE, 8, "bold"),
            fg=TEXT_MUTED,
            bg=BG_BASE,
        ).pack(side="left", padx=(0, 8))

        self.lbl_hdr_count = PillBadge(
            hdr_row,
            text=count_str,
            bg=BG_BASE,
            badge_bg="#15241d" if conn_count > 0 else "#191b24",
            border="#1f3d2f" if conn_count > 0 else "#252835",
            fg=ACCENT_GREEN if conn_count > 0 else TEXT_MUTED,
            font=(FONT_TITLE, 8, "bold"),
            padx=8,
            height=20,
            radius=10,
        )
        self.lbl_hdr_count.pack(side="left")

        # Scrollable container for cards
        self.cards_container = tk.Frame(self.content_frame, bg=BG_BASE)
        self.cards_container.pack(fill="both", expand=True)

        self._render_controller_cards()

    def _render_empty_state(self):
        empty_card = RoundedCard(
            self.content_frame,
            bg_base=BG_BASE,
            card_bg=BG_CARD,
            border_col=BORDER,
            radius=24,
            padx=32,
            pady=36,
            auto_height=True,
        )
        empty_card.pack(fill="x", pady=24)

        if self._hero_icon:
            tk.Label(empty_card.inner, image=self._hero_icon, bg=BG_CARD).pack(pady=(0, 16))

        tk.Label(
            empty_card.inner,
            text="No Controllers Connected",
            font=(FONT_TITLE, 15, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_CARD,
        ).pack(pady=(0, 6))

        tk.Label(
            empty_card.inner,
            text="Pair your Nintendo Wii U Pro Controller to play with pure native Bluetooth.\nZero dongles required.",
            font=(FONT_BODY, 10),
            fg=TEXT_SECONDARY,
            bg=BG_CARD,
            justify="center",
        ).pack(pady=(0, 20))

        btn_get_started = PillButton(
            empty_card.inner,
            text="＋ Pair Controller",
            bg=BG_CARD,
            btn_bg=ACCENT_BLUE,
            btn_hover=ACCENT_BLUE_HOVER,
            btn_press="#2563eb",
            border="#3b82f6",
            fg="#ffffff",
            font=(FONT_TITLE, 10, "bold"),
            padx=22,
            height=36,
            radius=18,
            command=self._start_pairing_flow,
        )
        btn_get_started.pack()

        tk.Label(
            empty_card.inner,
            text="Press the red SYNC button on the back of your controller to make it discoverable.",
            font=(FONT_BODY, 8),
            fg=TEXT_MUTED,
            bg=BG_CARD,
        ).pack(pady=(16, 0))

    def _render_controller_cards(self):
        for w in self.cards_container.winfo_children():
            w.destroy()

        self.card_views = {}
        macs = load_saved_macs()
        self._rendered_macs = list(macs)

        if not macs:
            self._show_home_view()
            return

        for slot_idx, mac in enumerate(macs[:4]):
            worker = self.workers.get(slot_idx)
            is_connected = bool(worker and worker.controller.connected)
            state = worker.current_state if is_connected else None

            # Elevated Hardware Card with 18px Continuous Curvature
            card = RoundedCard(
                self.cards_container,
                bg_base=BG_BASE,
                card_bg=BG_CARD,
                border_col=BORDER,
                radius=18,
                padx=18,
                pady=16,
            )
            card.pack(fill="x", pady=8)

            # Horizontal Content Row: Left has Controller Logo Thumbnail, Right has details
            content_row = tk.Frame(card.inner, bg=BG_CARD)
            content_row.pack(fill="x")

            if self._card_icon:
                lbl_thumb = tk.Label(content_row, image=self._card_icon, bg=BG_CARD)
                lbl_thumb.pack(side="left", padx=(0, 16), anchor="n", pady=2)

            details = tk.Frame(content_row, bg=BG_CARD)
            details.pack(side="left", fill="both", expand=True)

            # Row 1 of details: Header (Player Badge, Name, Connection Status, Battery)
            r1 = tk.Frame(details, bg=BG_CARD)
            r1.pack(fill="x")

            # Player Color Badge (PillBadge)
            p_accent = PLAYER_ACCENTS[slot_idx % 4]
            p_bg = PLAYER_BGS[slot_idx % 4]
            p_border = PLAYER_BORDERS[slot_idx % 4]
            lbl_pbadge = PillBadge(
                r1,
                text=f"P{slot_idx + 1}",
                bg=BG_CARD,
                badge_bg=p_bg,
                border=p_border,
                fg=p_accent,
                font=(FONT_TITLE, 9, "bold"),
                padx=10,
                height=24,
                radius=12,
            )
            lbl_pbadge.pack(side="left")

            # Human-readable title
            tk.Label(
                r1,
                text="Wii U Pro Controller",
                font=(FONT_TITLE, 11, "bold"),
                fg=TEXT_PRIMARY,
                bg=BG_CARD,
            ).pack(side="left", padx=10)

            # Connection Status Pill (PillBadge)
            if is_connected:
                st_txt = "● Connected"
                st_fg = ACCENT_GREEN
                st_bg = "#11261d"
                st_border = "#1a382b"
            else:
                st_txt = "○ Sleeping"
                st_fg = TEXT_SECONDARY
                st_bg = "#181a22"
                st_border = "#252835"

            lbl_status = PillBadge(
                r1,
                text=st_txt,
                bg=BG_CARD,
                badge_bg=st_bg,
                border=st_border,
                fg=st_fg,
                font=(FONT_TITLE, 8, "bold"),
                padx=10,
                height=24,
                radius=12,
            )
            lbl_status.pack(side="left", padx=4)

            # Battery / sleep badge container on right
            bat_container = tk.Frame(r1, bg=BG_CARD)
            bat_container.pack(side="right")

            lbl_sleep = PillBadge(
                bat_container,
                text="Press any button to connect",
                bg=BG_CARD,
                badge_bg="#161820",
                border="#232634",
                fg=TEXT_MUTED,
                font=(FONT_BODY, 8),
                padx=10,
                height=24,
                radius=12,
            )

            # Battery PillBadge
            bat_val = max(1, min(4, state.battery)) if state else 4
            bat_pct = f"{bat_val * 25}%"
            bolt = "⚡ " if (state and state.is_charging) else "🔋 "
            bat_col = ACCENT_AMBER if bat_val <= 1 else ACCENT_GREEN
            bat_bg = "#221a12" if bat_val <= 1 else "#11261d"
            bat_border = "#3d2b1b" if bat_val <= 1 else "#1a382b"

            lbl_bat = PillBadge(
                bat_container,
                text=f"{bolt}{bat_pct}",
                bg=BG_CARD,
                badge_bg=bat_bg,
                border=bat_border,
                fg=bat_col,
                font=(FONT_TITLE, 8, "bold"),
                padx=10,
                height=24,
                radius=12,
            )

            if is_connected and state:
                lbl_bat.pack(side="right")
            else:
                lbl_sleep.pack(side="right")

            # Row 2: Secondary Metadata (Active Profile & MAC Address)
            r2 = tk.Frame(details, bg=BG_CARD)
            r2.pack(fill="x", pady=(6, 12))

            profile_name = "Nintendo Face Buttons (A=A, B=B)" if self.nintendo_layout else "Xbox 360 Physical Position"
            lbl_profile = tk.Label(
                r2,
                text=f"Profile: {profile_name}",
                font=(FONT_BODY, 9),
                fg=TEXT_SECONDARY,
                bg=BG_CARD,
            )
            lbl_profile.pack(side="left")

            tk.Label(
                r2,
                text=f"•  {mac}",
                font=("Monospace", 8),
                fg=TEXT_MUTED,
                bg=BG_CARD,
            ).pack(side="left", padx=8)

            # Row 3: Action Buttons (Rumble, Diagnostics, Layout Toggle, Forget)
            r3 = tk.Frame(details, bg=BG_CARD)
            r3.pack(fill="x")

            btn_rumble = PillButton(
                r3,
                text="⚡ Test Rumble",
                bg=BG_CARD,
                btn_bg=BG_SURFACE,
                btn_hover=BG_SURFACE_HOVER,
                btn_press=BG_INSET,
                border="#2e3342",
                fg=TEXT_PRIMARY if is_connected else TEXT_MUTED,
                font=(FONT_TITLE, 9, "bold"),
                padx=12,
                height=28,
                radius=14,
                state="normal" if is_connected else "disabled",
                command=lambda pid=slot_idx: self._trigger_rumble(pid),
            )
            btn_rumble.pack(side="left", padx=(0, 8))

            btn_diag = PillButton(
                r3,
                text="🎮 Test Inputs...",
                bg=BG_CARD,
                btn_bg=BG_SURFACE,
                btn_hover=BG_SURFACE_HOVER,
                btn_press=BG_INSET,
                border="#2e3342",
                fg=TEXT_PRIMARY if is_connected else TEXT_MUTED,
                font=(FONT_TITLE, 9, "bold"),
                padx=12,
                height=28,
                radius=14,
                state="normal" if is_connected else "disabled",
                command=lambda pid=slot_idx: self._show_diagnostics_view(pid),
            )
            btn_diag.pack(side="left", padx=(0, 8))

            target_layout = "Xbox" if self.nintendo_layout else "Nintendo"
            btn_layout = PillButton(
                r3,
                text=f"Switch to {target_layout}",
                bg=BG_CARD,
                btn_bg=BG_SURFACE,
                btn_hover=BG_SURFACE_HOVER,
                btn_press=BG_INSET,
                border="#2e3342",
                fg=TEXT_SECONDARY,
                font=(FONT_TITLE, 9, "bold"),
                padx=12,
                height=28,
                radius=14,
                command=self._toggle_layout,
            )
            btn_layout.pack(side="left")

            btn_remove = PillButton(
                r3,
                text="Remove",
                bg=BG_CARD,
                btn_bg="#211519",
                btn_hover="#341820",
                btn_press="#180e12",
                border="#3d1922",
                fg=ACCENT_RED,
                font=(FONT_TITLE, 9, "bold"),
                padx=10,
                height=28,
                radius=14,
                command=lambda m=mac, pid=slot_idx: self._confirm_remove_controller(m, pid),
            )
            btn_remove.pack(side="right")

            self.card_views[slot_idx] = {
                "card": card,
                "lbl_status": lbl_status,
                "lbl_sleep": lbl_sleep,
                "lbl_bat": lbl_bat,
                "lbl_profile": lbl_profile,
                "btn_rumble": btn_rumble,
                "btn_diag": btn_diag,
                "btn_layout": btn_layout,
            }

    def _refresh_card_views(self):
        macs = load_saved_macs()
        if macs != getattr(self, "_rendered_macs", None):
            self._render_controller_cards()
            return

        conn_count = 0
        for slot_idx, mac in enumerate(macs[:4]):
            worker = self.workers.get(slot_idx)
            is_connected = bool(worker and worker.controller.connected)
            if is_connected:
                conn_count += 1
            state = worker.current_state if is_connected else None
            view = self.card_views.get(slot_idx)
            if not view:
                continue

            # Update status pill in-place
            if is_connected:
                view["lbl_status"].configure(
                    text="● Connected",
                    badge_bg="#11261d",
                    border="#1a382b",
                    fg=ACCENT_GREEN,
                )
            else:
                view["lbl_status"].configure(
                    text="○ Sleeping",
                    badge_bg="#181a22",
                    border="#252835",
                    fg=TEXT_SECONDARY,
                )

            # Update battery / sleep label in-place
            if is_connected and state:
                view["lbl_sleep"].pack_forget()
                bat_val = max(1, min(4, state.battery))
                bat_pct = f"{bat_val * 25}%"
                bolt = "⚡ " if state.is_charging else "🔋 "
                bat_col = ACCENT_AMBER if bat_val <= 1 else ACCENT_GREEN
                bat_bg = "#221a12" if bat_val <= 1 else "#11261d"
                bat_border = "#3d2b1b" if bat_val <= 1 else "#1a382b"
                view["lbl_bat"].configure(
                    text=f"{bolt}{bat_pct}",
                    badge_bg=bat_bg,
                    border=bat_border,
                    fg=bat_col,
                )
                if not view["lbl_bat"].winfo_ismapped():
                    view["lbl_bat"].pack(side="right")
            else:
                view["lbl_bat"].pack_forget()
                if not view["lbl_sleep"].winfo_ismapped():
                    view["lbl_sleep"].pack(side="right")

            # Update profile label in-place
            profile_name = "Nintendo Face Buttons (A=A, B=B)" if self.nintendo_layout else "Xbox 360 Physical Position"
            view["lbl_profile"].configure(text=f"Profile: {profile_name}")

            # Update layout switch button in-place
            target_layout = "Xbox" if self.nintendo_layout else "Nintendo"
            view["btn_layout"].configure(text=f"Switch to {target_layout}")

            # Update action buttons state in-place
            view["btn_rumble"].configure(
                fg=TEXT_PRIMARY if is_connected else TEXT_MUTED,
                state="normal" if is_connected else "disabled",
            )
            view["btn_diag"].configure(
                fg=TEXT_PRIMARY if is_connected else TEXT_MUTED,
                state="normal" if is_connected else "disabled",
            )

        if hasattr(self, "lbl_hdr_count"):
            count_str = f"{conn_count} Active" if conn_count > 0 else "All Sleeping"
            self.lbl_hdr_count.configure(
                text=count_str,
                badge_bg="#15241d" if conn_count > 0 else "#191b24",
                border="#1f3d2f" if conn_count > 0 else "#252835",
                fg=ACCENT_GREEN if conn_count > 0 else TEXT_MUTED,
            )

    # ================================================================
    # View 2: On-Demand Diagnostic Sheet
    # ================================================================
    def _show_diagnostics_view(self, player_id):
        self.current_view = "diagnostics"
        self.diag_player_id = player_id
        for w in self.content_frame.winfo_children():
            w.destroy()

        self.btn_pair.configure(state="disabled")

        # Diagnostic Navigation Bar
        diag_nav = tk.Frame(self.content_frame, bg=BG_BASE)
        diag_nav.pack(fill="x", pady=(0, 12))

        btn_back = PillButton(
            diag_nav,
            text="← Back to Controllers",
            bg=BG_BASE,
            btn_bg=BG_SURFACE,
            btn_hover=BG_SURFACE_HOVER,
            btn_press=BG_INSET,
            border="#2e3342",
            fg=TEXT_PRIMARY,
            font=(FONT_TITLE, 9, "bold"),
            padx=14,
            height=30,
            radius=15,
            command=self._show_home_view,
        )
        btn_back.pack(side="left")

        p_accent = PLAYER_ACCENTS[player_id % 4]
        p_bg = PLAYER_BGS[player_id % 4]
        p_border = PLAYER_BORDERS[player_id % 4]
        PillBadge(
            diag_nav,
            text=f"Player {player_id + 1} — Hardware Diagnostics",
            bg=BG_BASE,
            badge_bg=p_bg,
            border=p_border,
            fg=p_accent,
            font=(FONT_TITLE, 9, "bold"),
            padx=12,
            height=28,
            radius=14,
        ).pack(side="left", padx=12)

        btn_rumble_diag = PillButton(
            diag_nav,
            text="⚡ Test Rumble",
            bg=BG_BASE,
            btn_bg=BG_SURFACE,
            btn_hover=BG_SURFACE_HOVER,
            btn_press=BG_INSET,
            border="#2e3342",
            fg=TEXT_PRIMARY,
            font=(FONT_TITLE, 9, "bold"),
            padx=12,
            height=30,
            radius=15,
            command=lambda: self._trigger_rumble(player_id),
        )
        btn_rumble_diag.pack(side="right", padx=(8, 0))

        mode_desc = "Nintendo Layout" if self.nintendo_layout else "Xbox 360 Physical"
        self.lbl_diag_mode = PillBadge(
            diag_nav,
            text=mode_desc,
            bg=BG_BASE,
            badge_bg="#171922",
            border="#242838",
            fg=TEXT_SECONDARY,
            font=(FONT_TITLE, 8),
            padx=10,
            height=28,
            radius=14,
        )
        self.lbl_diag_mode.pack(side="right")

        # High-Fidelity Diagnostic Canvas Arena in Rounded Card (20px radius)
        canvas_wrapper = RoundedCard(
            self.content_frame,
            bg_base=BG_BASE,
            card_bg="#0e0f14",
            border_col=BORDER,
            radius=20,
            padx=6,
            pady=6,
            auto_height=False,
        )
        canvas_wrapper.pack(fill="both", expand=True)

        self.diag_canvas = tk.Canvas(canvas_wrapper.inner, bg="#0e0f14", highlightthickness=0)
        self.diag_canvas.pack(fill="both", expand=True)
        self.diag_canvas.bind("<Configure>", lambda e: self._draw_diagnostics())

    def _draw_diagnostics(self):
        if self.current_view != "diagnostics" or not hasattr(self, "diag_canvas"):
            return

        self.diag_canvas.delete("all")
        w = self.diag_canvas.winfo_width()
        h = self.diag_canvas.winfo_height()
        if w < 100 or h < 100:
            return

        cx, cy = w / 2, h / 2 + 10

        worker = self.workers.get(self.diag_player_id)
        is_online = bool(worker and worker.controller.connected)
        state = worker.current_state if is_online else None

        buttons = state.buttons if state else []
        lx = state.lx if state else 0.0
        ly = state.ly if state else 0.0
        rx = state.rx if state else 0.0
        ry = state.ry if state else 0.0

        scale = min(w / 580.0, h / 440.0, 1.25)

        # Sleeping prompt when disconnected
        if not is_online:
            self.diag_canvas.create_text(
                cx, cy - 175 * scale,
                text="Controller Sleeping • Press any button to connect",
                font=(FONT_TITLE, int(10 * scale), "bold"),
                fill=ACCENT_AMBER,
            )

        # 1. Authentic Smooth Controller Body Silhouette
        body_pts = [
            cx - 70 * scale, cy - 130 * scale,
            cx - 130 * scale, cy - 128 * scale,
            cx - 170 * scale, cy - 110 * scale,
            cx - 200 * scale, cy - 80 * scale,
            cx - 220 * scale, cy - 30 * scale,
            cx - 230 * scale, cy + 30 * scale,
            cx - 225 * scale, cy + 90 * scale,
            cx - 205 * scale, cy + 145 * scale,
            cx - 175 * scale, cy + 175 * scale,
            cx - 145 * scale, cy + 180 * scale,
            cx - 120 * scale, cy + 155 * scale,
            cx - 100 * scale, cy + 95 * scale,
            cx - 70 * scale, cy + 65 * scale,
            cx - 40 * scale, cy + 80 * scale,
            cx, cy + 85 * scale,
            cx + 40 * scale, cy + 80 * scale,
            cx + 70 * scale, cy + 65 * scale,
            cx + 100 * scale, cy + 95 * scale,
            cx + 120 * scale, cy + 155 * scale,
            cx + 145 * scale, cy + 180 * scale,
            cx + 175 * scale, cy + 175 * scale,
            cx + 205 * scale, cy + 145 * scale,
            cx + 225 * scale, cy + 90 * scale,
            cx + 230 * scale, cy + 30 * scale,
            cx + 220 * scale, cy - 30 * scale,
            cx + 200 * scale, cy - 80 * scale,
            cx + 170 * scale, cy - 110 * scale,
            cx + 130 * scale, cy - 128 * scale,
            cx + 70 * scale, cy - 130 * scale,
        ]

        self.diag_canvas.create_polygon(body_pts, fill="#161822", outline="#292e3e", width=2, smooth=True)

        # 2. Shoulder Triggers with Rounded Bumpers
        triggers = [
            ("ZL", cx - 170 * scale, cy - 150 * scale, cx - 105 * scale, cy - 128 * scale, "ZL" in buttons),
            ("L",  cx - 100 * scale, cy - 146 * scale, cx - 45 * scale,  cy - 128 * scale, "L" in buttons),
            ("R",  cx + 45 * scale,  cy - 146 * scale, cx + 100 * scale, cy - 128 * scale, "R" in buttons),
            ("ZR", cx + 105 * scale, cy - 150 * scale, cx + 170 * scale, cy - 128 * scale, "ZR" in buttons),
        ]
        trig_r = int(6 * scale)
        for tname, x0, y0, x1, y1, pressed in triggers:
            t_fill = ACCENT_CYAN if (pressed and is_online) else "#1d202c"
            t_outline = ACCENT_CYAN if (pressed and is_online) else "#32384c"
            t_fg = "#000000" if (pressed and is_online) else TEXT_SECONDARY
            draw_canvas_rounded_rect(self.diag_canvas, x0, y0, x1, y1, r=trig_r, fill=t_fill, outline=t_outline, width=1)
            self.diag_canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=tname, font=(FONT_TITLE, int(8 * scale), "bold"), fill=t_fg)

        # 3. Twin Sticks (Wii U Pro: Top Left & Top Right)
        sticks = [
            (-1, "L", lx, ly, "L3" in buttons),
            (1,  "R", rx, ry, "R3" in buttons),
        ]
        for sign, label, stick_x, stick_y, pressed in sticks:
            sx = cx + sign * 125 * scale
            sy = cy - 45 * scale
            sr = 44 * scale

            # Well & deadzone guides
            self.diag_canvas.create_oval(sx - sr, sy - sr, sx + sr, sy + sr, fill="#101117", outline="#2b3042", width=2)
            self.diag_canvas.create_oval(sx - sr * 0.45, sy - sr * 0.45, sx + sr * 0.45, sy + sr * 0.45, outline="#1a1d26", width=1)
            self.diag_canvas.create_line(sx - sr + 6, sy, sx + sr - 6, sy, fill="#1d202c")
            self.diag_canvas.create_line(sx, sy - sr + 6, sx, sy + sr - 6, fill="#1d202c")

            # Stick cap
            cap_r = 16 * scale
            cap_x = sx + (stick_x * (sr - cap_r))
            cap_y = sy - (stick_y * (sr - cap_r))

            cap_glow = ACCENT_CYAN if pressed else PLAYER_ACCENTS[self.diag_player_id % 4]
            cap_fill = ACCENT_CYAN if pressed else "#222533"
            self.diag_canvas.create_oval(cap_x - cap_r, cap_y - cap_r, cap_x + cap_r, cap_y + cap_r, fill=cap_fill, outline=cap_glow, width=2)
            self.diag_canvas.create_oval(cap_x - cap_r * 0.35, cap_y - cap_r * 0.35, cap_x + cap_r * 0.35, cap_y + cap_r * 0.35, fill=cap_glow, outline="")

            # Live values
            self.diag_canvas.create_text(sx, sy + sr + 14 * scale, text=f"{label} [{stick_x:+0.2f}, {stick_y:+0.2f}]", font=("Monospace", int(8 * scale)), fill=TEXT_SECONDARY)

        # 4. Nintendo Plus (+) D-Pad (Bottom-Left)
        dp_cx, dp_cy = cx - 125 * scale, cy + 55 * scale
        d_len, d_thick = 26 * scale, 17 * scale

        self.diag_canvas.create_oval(dp_cx - 32 * scale, dp_cy - 32 * scale, dp_cx + 32 * scale, dp_cy + 32 * scale, fill="#11131a", outline="#232734")
        dp_arms = [
            ("UP",    dp_cx - d_thick/2, dp_cy - d_len, dp_cx + d_thick/2, dp_cy - d_thick/2, "UP" in buttons),
            ("DOWN",  dp_cx - d_thick/2, dp_cy + d_thick/2, dp_cx + d_thick/2, dp_cy + d_len, "DOWN" in buttons),
            ("LEFT",  dp_cx - d_len, dp_cy - d_thick/2, dp_cx - d_thick/2, dp_cy + d_thick/2, "LEFT" in buttons),
            ("RIGHT", dp_cx + d_thick/2, dp_cy - d_thick/2, dp_cx + d_len, dp_cy + d_thick/2, "RIGHT" in buttons),
        ]
        self.diag_canvas.create_rectangle(dp_cx - d_thick/2, dp_cy - d_thick/2, dp_cx + d_thick/2, dp_cy + d_thick/2, fill="#1f2330", outline="")
        for dname, x0, y0, x1, y1, pressed in dp_arms:
            fill_c = ACCENT_CYAN if (pressed and is_online) else "#1f2330"
            out_c = ACCENT_CYAN if (pressed and is_online) else "#353a4c"
            draw_canvas_rounded_rect(self.diag_canvas, x0, y0, x1, y1, r=int(3 * scale), fill=fill_c, outline=out_c)

        self.diag_canvas.create_text(dp_cx, dp_cy - d_len + 8 * scale, text="▲", font=(FONT_TITLE, int(6 * scale)), fill=TEXT_SECONDARY)
        self.diag_canvas.create_text(dp_cx, dp_cy + d_len - 8 * scale, text="▼", font=(FONT_TITLE, int(6 * scale)), fill=TEXT_SECONDARY)
        self.diag_canvas.create_text(dp_cx - d_len + 8 * scale, dp_cy, text="◀", font=(FONT_TITLE, int(6 * scale)), fill=TEXT_SECONDARY)
        self.diag_canvas.create_text(dp_cx + d_len - 8 * scale, dp_cy, text="▶", font=(FONT_TITLE, int(6 * scale)), fill=TEXT_SECONDARY)

        # 5. Face Buttons ABXY Diamond (Bottom-Right)
        abxy_cx, abxy_cy = cx + 125 * scale, cy + 55 * scale
        btn_r = 13 * scale
        spread = 28 * scale

        if self.nintendo_layout:
            face_defs = [
                ("X", 0, -spread, "#0ea5e9", "X" in buttons),
                ("A", spread, 0, "#f43f5e", "A" in buttons),
                ("B", 0, spread, "#f59e0b", "B" in buttons),
                ("Y", -spread, 0, "#10b981", "Y" in buttons),
            ]
        else:
            face_defs = [
                ("Y", 0, -spread, "#f59e0b", "X" in buttons),
                ("B", spread, 0, "#f43f5e", "A" in buttons),
                ("A", 0, spread, "#10b981", "B" in buttons),
                ("X", -spread, 0, "#0ea5e9", "Y" in buttons),
            ]

        for bname, ox, oy, accent_col, is_pressed in face_defs:
            bx = abxy_cx + ox
            by = abxy_cy + oy
            fill = accent_col if (is_pressed and is_online) else "#1f2330"
            outline = accent_col if (is_pressed and is_online) else "#373d50"
            txt_fg = "#ffffff" if (is_pressed and is_online) else TEXT_PRIMARY

            self.diag_canvas.create_oval(bx - btn_r, by - btn_r, bx + btn_r, by + btn_r, fill=fill, outline=outline, width=2)
            self.diag_canvas.create_text(bx, by, text=bname, font=(FONT_TITLE, int(10 * scale), "bold"), fill=txt_fg)

        # 6. Center Buttons (-, HOME, +)
        min_pressed = "-" in buttons and is_online
        self.diag_canvas.create_oval(
            cx - 50 * scale - 9 * scale, cy - 6 * scale, cx - 50 * scale + 9 * scale, cy + 12 * scale,
            fill=ACCENT_CYAN if min_pressed else "#1f2330",
            outline=ACCENT_CYAN if min_pressed else "#373d50",
        )
        self.diag_canvas.create_text(cx - 50 * scale, cy + 3 * scale, text="—", font=(FONT_TITLE, int(9 * scale), "bold"), fill=TEXT_PRIMARY)

        home_pressed = "HOME" in buttons and is_online
        self.diag_canvas.create_oval(
            cx - 15 * scale, cy - 10 * scale, cx + 15 * scale, cy + 20 * scale,
            fill=ACCENT_CYAN if home_pressed else "#111824",
            outline=ACCENT_CYAN,
            width=2,
        )
        self.diag_canvas.create_text(cx, cy + 5 * scale, text="⌂", font=(FONT_TITLE, int(12 * scale)), fill=ACCENT_CYAN)

        plus_pressed = "+" in buttons and is_online
        self.diag_canvas.create_oval(
            cx + 50 * scale - 9 * scale, cy - 6 * scale, cx + 50 * scale + 9 * scale, cy + 12 * scale,
            fill=ACCENT_CYAN if plus_pressed else "#1f2330",
            outline=ACCENT_CYAN if plus_pressed else "#373d50",
        )
        self.diag_canvas.create_text(cx + 50 * scale, cy + 3 * scale, text="+", font=(FONT_TITLE, int(11 * scale), "bold"), fill=TEXT_PRIMARY)

        # 7. Player LEDs
        led_y = cy + 105 * scale
        for i in range(4):
            lx = cx + (i - 1.5) * 18 * scale
            is_lit = (i == self.diag_player_id) and is_online
            col = ACCENT_CYAN if is_lit else "#13151e"
            glow = ACCENT_CYAN if is_lit else "#242734"
            self.diag_canvas.create_oval(lx - 4 * scale, led_y - 4 * scale, lx + 4 * scale, led_y + 4 * scale, fill=col, outline=glow, width=1)

    # ================================================================
    # View 3: Guided Pairing Wizard
    # ================================================================
    def _start_pairing_flow(self):
        if self.scanning:
            return

        self.current_view = "pairing"
        self.scanning = True
        for w in self.content_frame.winfo_children():
            w.destroy()

        self.btn_pair.configure(state="disabled")

        pairing_card = RoundedCard(
            self.content_frame,
            bg_base=BG_BASE,
            card_bg=BG_CARD,
            border_col=BORDER,
            radius=24,
            padx=32,
            pady=36,
            auto_height=True,
        )
        pairing_card.pack(fill="x", pady=24)

        if self._wizard_icon:
            tk.Label(pairing_card.inner, image=self._wizard_icon, bg=BG_CARD).pack(pady=(0, 14))

        tk.Label(
            pairing_card.inner,
            text="Pairing New Controller",
            font=(FONT_TITLE, 15, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_CARD,
        ).pack(pady=(0, 6))

        self.lbl_pair_step = tk.Label(
            pairing_card.inner,
            text="Press and hold the red SYNC button on the back of your controller.\nMake sure the 4 blue LEDs at the bottom are flashing rapidly.",
            font=(FONT_BODY, 10),
            fg=TEXT_SECONDARY,
            bg=BG_CARD,
            justify="center",
        )
        self.lbl_pair_step.pack(pady=(0, 20))

        # Status badge as a rounded PillBadge
        self.lbl_pair_status = PillBadge(
            pairing_card.inner,
            text="⏳ Sweeping 2.4 GHz radio for discovery packets...",
            bg=BG_CARD,
            badge_bg="#241e14",
            border="#40321a",
            fg=ACCENT_AMBER,
            font=(FONT_TITLE, 10, "bold"),
            padx=16,
            height=34,
            radius=17,
        )
        self.lbl_pair_status.pack(pady=(0, 24))

        btn_cancel = PillButton(
            pairing_card.inner,
            text="Cancel",
            bg=BG_CARD,
            btn_bg=BG_SURFACE,
            btn_hover=BG_SURFACE_HOVER,
            btn_press=BG_INSET,
            border="#2e3342",
            fg=TEXT_SECONDARY,
            font=(FONT_TITLE, 9, "bold"),
            padx=18,
            height=32,
            radius=16,
            command=self._cancel_pairing,
        )
        btn_cancel.pack()

        # Run over-the-air scan in background
        ignore_macs = [w.mac for w in self.workers.values() if w.controller.connected]
        threading.Thread(target=self._run_pair_search, args=(ignore_macs,), daemon=True).start()

    def _run_pair_search(self, ignore_macs):
        new_mac = scan_for_controller(timeout_seconds=25, quiet=True, ignore_macs=ignore_macs)
        if not self.scanning:
            return

        if new_mac:
            macs = load_saved_macs()
            if new_mac not in macs:
                save_mac(new_mac)
                macs.append(new_mac)

            slot = macs.index(new_mac)
            self.root.after(0, lambda: self.lbl_pair_status.configure(
                text=f"✓ Found {new_mac}! Connecting Player {slot + 1}...",
                badge_bg="#11261d",
                border="#1a382b",
                fg=ACCENT_GREEN,
            ))

            # Connect immediately while SYNC LEDs are blinking
            c = WiiUProController(mac=new_mac, player_id=slot)
            ok = c.connect(timeout=8, quiet=True)

            self.root.after(0, lambda: self._on_pair_completed(new_mac, slot, c if ok else None))
        else:
            self.root.after(0, self._on_pair_timed_out)

    def _on_pair_completed(self, new_mac, slot, controller):
        self.scanning = False
        if slot < 4:
            if slot in self.workers:
                try:
                    self.workers[slot].stop()
                except Exception:
                    pass
                del self.workers[slot]

            w = PlayerWorker(
                new_mac,
                player_id=slot,
                nintendo_layout=self.nintendo_layout,
                quiet=True,
                controller=controller,
            )
            w.start()
            self.workers[slot] = w

            if controller and controller.connected:
                w.trigger_rumble_test(0.3)
                self.lbl_footer_status.configure(text=f"✓ Player {slot + 1} Connected and Ready!")

        self._show_home_view()

    def _on_pair_timed_out(self):
        self.scanning = False
        if self.current_view == "pairing":
            self.lbl_pair_status.configure(
                text="No controller detected. Make sure LEDs were blinking rapidly.",
                badge_bg="#261418",
                border="#401822",
                fg=ACCENT_RED,
            )
            self.root.after(2500, self._show_home_view)

    def _cancel_pairing(self):
        self.scanning = False
        self._show_home_view()

    # ================================================================
    # View 4: Clean Settings View
    # ================================================================
    def _toggle_settings_view(self):
        if self.current_view == "settings":
            self._show_home_view()
        else:
            self.current_view = "settings"
            for w in self.content_frame.winfo_children():
                w.destroy()

            self.btn_settings.configure(text="← Back")

            st_box = tk.Frame(self.content_frame, bg=BG_BASE, pady=6)
            st_box.pack(fill="both", expand=True)

            tk.Label(
                st_box,
                text="PREFERENCES & MAPPINGS",
                font=(FONT_TITLE, 8, "bold"),
                fg=TEXT_MUTED,
                bg=BG_BASE,
            ).pack(anchor="w", pady=(0, 10))

            # Setting Card 1: Button Layout Toggle (18px radius)
            c1 = RoundedCard(
                st_box,
                bg_base=BG_BASE,
                card_bg=BG_CARD,
                border_col=BORDER,
                radius=18,
                padx=20,
                pady=18,
                auto_height=True,
                min_height=96,
            )
            c1.pack(fill="x", pady=6)

            tk.Label(c1.inner, text="Button Layout Mapping", font=(FONT_TITLE, 11, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD).pack(anchor="w")
            tk.Label(
                c1.inner,
                text="Choose between standard PC Xbox button positions or original Nintendo letterings.",
                font=(FONT_BODY, 9),
                fg=TEXT_SECONDARY,
                bg=BG_CARD,
            ).pack(anchor="w", pady=(2, 14))

            # Segmented Pill Container with Rounded Well Track
            seg = RoundedCard(
                c1.inner,
                bg_base=BG_CARD,
                card_bg=BG_INSET,
                border_col="#1d2028",
                radius=16,
                padx=4,
                pady=4,
                auto_height=True,
                auto_width=True,
            )
            seg.pack(anchor="w")

            self.lbl_opt_xbox = PillButton(
                seg.inner,
                text="Xbox 360 Style (Bottom is A)",
                bg=BG_INSET,
                btn_bg=BG_SURFACE if not self.nintendo_layout else BG_INSET,
                btn_hover=BG_SURFACE_HOVER if not self.nintendo_layout else "#15171d",
                btn_press=BG_INSET,
                border="#2e3342" if not self.nintendo_layout else BG_INSET,
                fg=TEXT_PRIMARY if not self.nintendo_layout else TEXT_SECONDARY,
                font=(FONT_TITLE, 9, "bold" if not self.nintendo_layout else "normal"),
                padx=16,
                height=30,
                radius=14,
                command=lambda: self._set_layout(False),
            )
            self.lbl_opt_xbox.pack(side="left")

            self.lbl_opt_nin = PillButton(
                seg.inner,
                text="Nintendo Style (Right is A)",
                bg=BG_INSET,
                btn_bg=BG_SURFACE if self.nintendo_layout else BG_INSET,
                btn_hover=BG_SURFACE_HOVER if self.nintendo_layout else "#15171d",
                btn_press=BG_INSET,
                border="#2e3342" if self.nintendo_layout else BG_INSET,
                fg=TEXT_PRIMARY if self.nintendo_layout else TEXT_SECONDARY,
                font=(FONT_TITLE, 9, "bold" if self.nintendo_layout else "normal"),
                padx=16,
                height=30,
                radius=14,
                command=lambda: self._set_layout(True),
            )
            self.lbl_opt_nin.pack(side="left", padx=(4, 0))

            # Setting Card 2: System Autostart (18px radius)
            c2 = RoundedCard(
                st_box,
                bg_base=BG_BASE,
                card_bg=BG_CARD,
                border_col=BORDER,
                radius=18,
                padx=20,
                pady=18,
                auto_height=True,
                min_height=96,
            )
            c2.pack(fill="x", pady=10)

            # Right-aligned action toggle packed FIRST to guarantee full button visibility at any width
            self.btn_auto_toggle = PillButton(
                c2.inner,
                text="Enabled" if self.autostart_active else "Disabled",
                bg=BG_CARD,
                btn_bg="#11261d" if self.autostart_active else BG_SURFACE,
                btn_hover="#173629" if self.autostart_active else BG_SURFACE_HOVER,
                btn_press="#0d1f17" if self.autostart_active else BG_INSET,
                border="#1a382b" if self.autostart_active else "#2e3342",
                fg=ACCENT_GREEN if self.autostart_active else TEXT_MUTED,
                font=(FONT_TITLE, 9, "bold"),
                padx=16,
                height=30,
                radius=15,
                command=self._toggle_autostart,
            )
            self.btn_auto_toggle.pack(side="right", padx=(16, 0))

            c2_left = tk.Frame(c2.inner, bg=BG_CARD)
            c2_left.pack(side="left", fill="both", expand=True)

            tk.Label(c2_left, text="Launch at System Login", font=(FONT_TITLE, 11, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD).pack(anchor="w")
            lbl_c2_desc = tk.Label(
                c2_left,
                text="Enable background user service to auto-connect controllers when powered on.",
                font=(FONT_BODY, 9),
                fg=TEXT_SECONDARY,
                bg=BG_CARD,
                justify="left",
            )
            lbl_c2_desc.pack(anchor="w", pady=(2, 0))
            c2_left.bind("<Configure>", lambda e, lbl=lbl_c2_desc: lbl.configure(wraplength=max(150, e.width)))

    def _set_layout(self, is_nintendo: bool):
        self.nintendo_layout = bool(is_nintendo)
        save_config_key("nintendo_layout", self.nintendo_layout)
        for w in self.workers.values():
            w.set_nintendo_layout(self.nintendo_layout)

        if hasattr(self, "lbl_opt_xbox") and hasattr(self, "lbl_opt_nin"):
            self.lbl_opt_xbox.configure(
                btn_bg=BG_SURFACE if not self.nintendo_layout else BG_INSET,
                btn_hover=BG_SURFACE_HOVER if not self.nintendo_layout else "#15171d",
                border="#2e3342" if not self.nintendo_layout else BG_INSET,
                fg=TEXT_PRIMARY if not self.nintendo_layout else TEXT_SECONDARY,
                font=(FONT_TITLE, 9, "bold" if not self.nintendo_layout else "normal"),
            )
            self.lbl_opt_nin.configure(
                btn_bg=BG_SURFACE if self.nintendo_layout else BG_INSET,
                btn_hover=BG_SURFACE_HOVER if self.nintendo_layout else "#15171d",
                border="#2e3342" if self.nintendo_layout else BG_INSET,
                fg=TEXT_PRIMARY if self.nintendo_layout else TEXT_SECONDARY,
                font=(FONT_TITLE, 9, "bold" if self.nintendo_layout else "normal"),
            )

        if self.current_view == "home":
            self._refresh_card_views()
        elif self.current_view == "diagnostics" and hasattr(self, "lbl_diag_mode"):
            mode_desc = "Nintendo Layout" if self.nintendo_layout else "Xbox 360 Physical"
            self.lbl_diag_mode.configure(text=mode_desc)

        desc = "Nintendo (A=A, B=B)" if self.nintendo_layout else "Xbox 360 Physical Position"
        self.lbl_footer_status.configure(text=f"Layout switched to {desc}.")

    def _toggle_layout(self):
        self._set_layout(not self.nintendo_layout)

    def _toggle_autostart(self):
        self.autostart_active = not self.autostart_active
        action = "enable" if self.autostart_active else "disable"
        try:
            subprocess.run(["systemctl", "--user", action, "cafepad"], check=True)
            self.btn_auto_toggle.configure(
                text="Enabled" if self.autostart_active else "Disabled",
                btn_bg="#11261d" if self.autostart_active else BG_SURFACE,
                btn_hover="#173629" if self.autostart_active else BG_SURFACE_HOVER,
                border="#1a382b" if self.autostart_active else "#2e3342",
                fg=ACCENT_GREEN if self.autostart_active else TEXT_MUTED,
            )
            self.lbl_footer_status.configure(text=f"Systemd login service {action}d.")
        except Exception as e:
            self.lbl_footer_status.configure(text=f"Could not update service: {e}")

    # ================================================================
    # Controller Operations & Workers
    # ================================================================
    def _start_controller_workers(self):
        macs = load_saved_macs()
        for idx in range(4):
            mac = macs[idx] if idx < len(macs) else None
            if mac and idx not in self.workers:
                w = PlayerWorker(mac, player_id=idx, nintendo_layout=self.nintendo_layout, quiet=True)
                w.start()
                self.workers[idx] = w

    def _trigger_rumble(self, player_id):
        w = self.workers.get(player_id)
        if w and w.controller.connected:
            w.trigger_rumble_test(0.6)
            self.lbl_footer_status.configure(text=f"Rumbled Player {player_id + 1}!")

    def _confirm_remove_controller(self, mac, player_id):
        # Dismiss any previous active modal
        if hasattr(self, "_active_modal") and self._active_modal and self._active_modal.winfo_exists():
            self._active_modal.destroy()

        overlay = tk.Frame(self.container, bg="#0b0c0f")
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._active_modal = overlay

        def _close():
            self.root.unbind("<Escape>")
            if overlay.winfo_exists():
                overlay.destroy()
            self._active_modal = None

        def _do_remove():
            _close()
            remove_mac(mac)
            if player_id in self.workers:
                try:
                    self.workers[player_id].stop()
                except Exception:
                    pass
                del self.workers[player_id]

            self.lbl_footer_status.configure(text=f"Removed controller {mac}.")
            self._show_home_view()

        # Clicking the backdrop cancels
        overlay.bind("<Button-1>", lambda e: _close() if e.widget == overlay else None)
        self.root.bind("<Escape>", lambda e: _close())

        modal_card = RoundedCard(
            overlay,
            bg_base="#0b0c0f",
            card_bg=BG_CARD,
            border_col="#2d313e",
            radius=22,
            padx=36,
            pady=28,
            auto_height=True,
            auto_width=True,
        )
        modal_card.place(relx=0.5, rely=0.46, anchor="center")

        if self._card_icon:
            tk.Label(modal_card.inner, image=self._card_icon, bg=BG_CARD).pack(pady=(0, 12))

        tk.Label(
            modal_card.inner,
            text="Remove Controller?",
            font=(FONT_TITLE, 14, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_CARD,
        ).pack(pady=(0, 6))

        tk.Label(
            modal_card.inner,
            text=f"Forget Player {player_id + 1} ({mac})?\nThis controller will be disconnected and removed from saved devices.",
            font=(FONT_BODY, 9),
            fg=TEXT_SECONDARY,
            bg=BG_CARD,
            justify="center",
        ).pack(pady=(0, 22))

        btn_row = tk.Frame(modal_card.inner, bg=BG_CARD)
        btn_row.pack()

        btn_cancel = PillButton(
            btn_row,
            text="Cancel",
            bg=BG_CARD,
            btn_bg=BG_SURFACE,
            btn_hover=BG_SURFACE_HOVER,
            btn_press=BG_INSET,
            border="#2e3342",
            fg=TEXT_SECONDARY,
            font=(FONT_TITLE, 9, "bold"),
            padx=18,
            height=32,
            radius=16,
            command=_close,
        )
        btn_cancel.pack(side="left", padx=(0, 10))

        btn_remove = PillButton(
            btn_row,
            text="Remove Controller",
            bg=BG_CARD,
            btn_bg="#38151c",
            btn_hover="#4d1b26",
            btn_press="#250e13",
            border="#5c1f2e",
            fg=ACCENT_RED,
            font=(FONT_TITLE, 9, "bold"),
            padx=18,
            height=32,
            radius=16,
            command=_do_remove,
        )
        btn_remove.pack(side="left")

    def _check_autostart_status(self):
        try:
            res = subprocess.run(
                ["systemctl", "--user", "is-enabled", "cafepad"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return "enabled" in res.stdout
        except Exception:
            return False

    # ================================================================
    # Lightweight Non-Blocking Update Loop
    # ================================================================
    def _update_loop(self):
        # 1. 30 FPS diagnostics only when active
        if self.current_view == "diagnostics":
            self._draw_diagnostics()

        # 2. In-place card status refresh without widget destruction
        now = time.time()
        if self.current_view == "home" and getattr(self, "_last_home_refresh", 0) + 0.8 < now:
            self._last_home_refresh = now
            self._refresh_card_views()

        self.root.after(33, self._update_loop)

    def _on_closing(self):
        for w in list(self.workers.values()):
            try:
                w.stop()
            except Exception:
                pass
        try:
            get_agent_manager().stop()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = CafePadGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
