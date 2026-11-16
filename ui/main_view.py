"""Aqua Night main window: one full-window canvas plus the few real input widgets.

The view exposes the same objects the app logic already uses:
  path_entry, table, match_list, details, cover_label, search_button, cover_button
"""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from . import theme as T
from .aero_widgets import (AeroListbox, AeroTreeview, BubbleBackground, CoverView, EmptyState,
                           FocusManager, GlossyButton, ImageCache, Placeholder, TabPill, Toggle, truncate)

LYRICS_HINT = "Look up the lyrics for this match."

SUBTITLE = "Find verified song details and cover art, review them, then write them into your MP3s."


def _rr_points(x, y, w, h, r):
    r = max(0, min(r, w / 2, h / 2))
    pts = []
    for cx, cy, start in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        for i in range(9):
            a = math.radians(start + 90 * i / 8)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


class AquaNightView:
    def __init__(self, root: tk.Tk, *, app_name: str, folder: tk.StringVar, status: tk.StringVar,
                 fill_empty: tk.BooleanVar, save_png: tk.BooleanVar, query_title: tk.StringVar,
                 query_artist: tk.StringVar, on_choose, on_scan, on_search, on_cover, on_lyrics, on_apply,
                 on_track_selected, on_candidate_selected) -> None:
        self.root, self.app_name, self.status = root, app_name, status
        self.S = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.f = 1.0  # density: 0 = compact, 1 = full spec sizes
        self.fonts = T.Fonts(root, self.S)
        self.cache = ImageCache()
        self._hits: list = []
        self._hovered = None
        self._pressed = None
        self._split = 1.25 / 2.25
        self._drag = None
        self._render_job = None
        self._bg_key = None
        self._static_photos: dict = {}
        self._file_count = 0
        settings = T.load_settings()
        self.animate = tk.BooleanVar(value=bool(settings.get("animate_background", T.system_animations_enabled())))
        self.animate.trace_add("write", lambda *_a: T.save_setting("animate_background", self.animate.get()))

        S = self.S
        root.configure(bg=T.BG_MID)
        try:
            root.iconbitmap(default=str(T.asset("app.ico")))
        except tk.TclError:
            pass
        # Open centred inside the usable screen area (above the taskbar), never partly hidden.
        ax, ay, aw, ah = T.work_area(root)
        title_bar = round(32 * S)
        w = min(round(1320 * S), int(aw * 0.94))
        h = min(round(900 * S), ah - title_bar - round(16 * S))
        x = ax + max(0, (aw - w) // 2)
        y = ay + max(0, (ah - h - title_bar) // 2)
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.minsize(round(980 * S), round(640 * S))

        c = self.canvas = tk.Canvas(root, bg=T.BG_MID, highlightthickness=0, bd=0, takefocus=0)
        c.pack(fill="both", expand=True)
        c.bind("<Configure>", lambda _e: self.schedule_render())
        c.bind("<Motion>", self._on_motion)
        c.bind("<Leave>", lambda _e: self._set_hover(None))
        c.bind("<ButtonPress-1>", self._on_press)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_release)

        self._style()

        # ---- real widgets -------------------------------------------------
        body = self.fonts.body
        self.path_entry = self._entry(folder)
        self.title_entry = self._entry(query_title)
        self.artist_entry = self._entry(query_artist)
        self._placeholders = [Placeholder(self.path_entry, folder, "No folder selected", body(15)),
                              Placeholder(self.title_entry, query_title, "Song title", body(15)),
                              Placeholder(self.artist_entry, query_artist, "Artist name", body(15))]

        cols = ("title", "artist", "album", "year")
        self.table = AeroTreeview(c, on_rows_changed=self._rows_changed, columns=cols, show="headings",
                                  selectmode="browse", style="Aero.Treeview")
        for col in cols:
            self.table.heading(col, text=col.title().upper(), anchor="e" if col == "year" else "w")
            self.table.column(col, width=100, minwidth=45, stretch=col != "year",
                              anchor="e" if col == "year" else "w")
        self.table.tag_configure("odd", background=T.TABLE_ODD)
        self.table.tag_configure("hover", background=T.TABLE_HOVER)
        self.table.bind("<<TreeviewSelect>>", on_track_selected, add="+")
        self.table.bind("<Configure>", self._fit_columns, add="+")
        self.table_scroll = ttk.Scrollbar(c, orient="vertical", command=self.table.yview,
                                          style="Aero.Vertical.TScrollbar")
        self.table.configure(yscrollcommand=self.table_scroll.set)
        self.table_empty = EmptyState(self, self.table, "No songs loaded yet",
                                      "Choose a folder of MP3s and press Scan folder. "
                                      "Tracks will list here with their current tags.", icon=True)

        self.match_list = AeroListbox(c, on_rows_changed=self._results_changed, height=4, activestyle="none",
                                      font=body(14), borderwidth=0, relief="flat", highlightthickness=0,
                                      bg=T.FIELD_SOLID, fg=T.TEXT_BODY, selectbackground=T.SELECT_BG,
                                      selectforeground="#ffffff")
        self.match_list.bind("<<ListboxSelect>>", on_candidate_selected)
        self.list_scroll = ttk.Scrollbar(c, orient="vertical", command=self.match_list.yview,
                                         style="Aero.Vertical.TScrollbar")
        self.match_list.configure(yscrollcommand=self.list_scroll.set)
        self.results_empty = EmptyState(self, self.match_list, "", "Catalog results appear here", icon=False)

        self.details = tk.Text(c, height=9, width=24, wrap="word", font=body(14), relief="flat", borderwidth=0,
                               highlightthickness=0, bg=T.FIELD_SOLID, fg=T.TEXT_BODY, state="disabled",
                               padx=0, pady=0, spacing1=2, selectbackground=T.SELECT_BG, insertwidth=0)
        # Lyrics share the details box (Details / Lyrics tabs); read-only like the details text.
        self.lyrics = tk.Text(c, height=9, width=24, wrap="word", font=body(14), relief="flat", borderwidth=0,
                              highlightthickness=0, bg=T.FIELD_SOLID, fg=T.TEXT_BODY, state="disabled",
                              padx=0, pady=0, spacing1=2, selectbackground=T.SELECT_BG, insertwidth=0)
        self.lyrics_scroll = ttk.Scrollbar(c, orient="vertical", command=self.lyrics.yview,
                                           style="Aero.Vertical.TScrollbar")
        self.lyrics.configure(yscrollcommand=self.lyrics_scroll.set)
        self._tab = "details"

        self._windows = {}
        for name, widget in (("path", self.path_entry), ("title", self.title_entry), ("artist", self.artist_entry),
                             ("table", self.table), ("scroll", self.table_scroll), ("list", self.match_list),
                             ("listscroll", self.list_scroll),
                             ("details", self.details), ("lyrics", self.lyrics), ("lyricsscroll", self.lyrics_scroll)):
            self._windows[name] = c.create_window(0, 0, window=widget, anchor="nw", tags=("win",))

        # ---- canvas-drawn controls ------------------------------------------
        self.choose_button = GlossyButton(self, "Choose folder…", on_choose, "secondary")
        self.scan_button = GlossyButton(self, "Scan folder", on_scan, "primary")
        self.search_button = GlossyButton(self, "Search catalog", on_search, "secondary", state="disabled")
        self.cover_button = GlossyButton(self, "Get cover preview", on_cover, "secondary", state="disabled")
        self.lyrics_button = GlossyButton(self, "Get lyrics", on_lyrics, "secondary", state="disabled")
        self.apply_button = GlossyButton(self, "Apply to selected MP3", on_apply, "primary")
        self.tabs = {"details": TabPill(self, "Details", lambda: self.select_tab("details")),
                     "lyrics": TabPill(self, "Lyrics", lambda: self.select_tab("lyrics"))}
        self.toggles = [Toggle(self, "Only fill blank fields", fill_empty),
                        Toggle(self, "Also save a PNG copy under Album Art", save_png),
                        Toggle(self, "Animate background", self.animate)]
        self.cover_label = CoverView(self)

        self.focus = FocusManager(self)
        self.focus.order = [self.path_entry, self.choose_button, self.scan_button, self.table, self.title_entry,
                            self.artist_entry, self.match_list, self.search_button, self.cover_button,
                            self.lyrics_button, self.tabs["details"], self.tabs["lyrics"],
                            self.apply_button, *self.toggles]
        self.show_lyrics(None)

        self.bubbles = BubbleBackground(self, self.animate)
        self.bubbles.status_pulse = self._status_pulse
        status.trace_add("write", lambda *_a: self._draw_status_text())
        self.schedule_render(0)

    # ================================================================== lyrics / tabs
    def show_lyrics(self, text, message: str | None = None) -> None:
        """Fill the Lyrics tab. Text: show it and switch to the tab. None: the tab shows a hint (or
        ``message``, e.g. not found) with the Get lyrics button; only a message switches to it."""
        self._lyrics_loaded = bool(text)
        self._lyrics_msg = message or LYRICS_HINT
        self.lyrics.configure(state="normal")
        self.lyrics.delete("1.0", "end")
        if text:
            self.lyrics.insert("1.0", text)
        self.lyrics.configure(state="disabled")
        self.lyrics.yview_moveto(0)
        self.select_tab("lyrics" if (text or message) else "details")

    def select_tab(self, name: str) -> None:
        self._tab = name
        for key, tab in self.tabs.items():
            tab.selected = key == name
            tab.draw()
        c, S = self.canvas, self.S
        loaded = getattr(self, "_lyrics_loaded", False)
        show = {"details": ("details",), "lyrics": ("lyrics", "lyricsscroll") if loaded else ()}[name]
        for win in ("details", "lyrics", "lyricsscroll"):
            c.itemconfigure(self._windows[win], state="normal" if win in show else "hidden")
        # Lyrics tab with nothing loaded: a short hint plus the Get lyrics button, inside the box.
        c.delete("lyricsmsg")
        area = getattr(self, "_lyrics_area", None)
        if name != "lyrics" or loaded or not area:
            self.lyrics_button.hide()
            return
        x, y, w, h, btn_h = area
        btn_h = min(btn_h, max(28 * S, h - 4 * S))
        font = self.fonts.body(self.lerp(13, 14))
        ls = font.metrics("linespace")
        msg_room = h - btn_h - 8 * S
        lines = max(1, math.ceil(font.measure(self._lyrics_msg) / max(1, w - 8 * S)))
        if lines * ls <= msg_room:  # only when the whole message fits above the button
            c.create_text(x + w / 2, y + (msg_room - lines * ls) / 2, text=self._lyrics_msg, font=font,
                          fill=T.TEXT_MUTED, anchor="n", justify="center", width=w - 8 * S,
                          tags=("chrome", "lyricsmsg"))
        bw = self.lyrics_button.natural_width(btn_h)
        self.lyrics_button.place(x + (w - bw) / 2, y + h - btn_h, bw, btn_h)

    # ================================================================== helpers
    def lerp(self, a: float, b: float) -> float:
        return a + (b - a) * self.f

    def register_hit(self, obj) -> None:
        self._hits.append(obj)

    def _entry(self, var: tk.StringVar) -> tk.Entry:
        return tk.Entry(self.canvas, textvariable=var, relief="flat", bd=0, highlightthickness=0,
                        bg=T.FIELD_SOLID, fg=T.TEXT_BODY, insertbackground=T.ACCENT, insertwidth=max(1, round(self.S)),
                        selectbackground=T.SELECT_BG, selectforeground="#ffffff", disabledbackground=T.FIELD_SOLID,
                        font=self.fonts.body(15))

    def _style(self) -> None:
        S, body = self.S, self.fonts.body
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Aero.Treeview", background=T.FIELD_SOLID, fieldbackground=T.FIELD_SOLID,
                        foreground=T.TEXT_BODY, rowheight=round(32 * S), font=body(14), borderwidth=0, relief="flat")
        style.layout("Aero.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.map("Aero.Treeview", background=[("selected", T.SELECT_BG)], foreground=[("selected", "#ffffff")])
        style.configure("Aero.Treeview.Heading", background=T.TABLE_HEADING, foreground=T.TEXT_LABEL,
                        font=body(13, 700), relief="flat", borderwidth=0, padding=(round(14 * S), round(9 * S)))
        style.map("Aero.Treeview.Heading", background=[("active", T.TABLE_HEADING_ACTIVE)])
        style.layout("Aero.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure("Aero.Vertical.TScrollbar", troughcolor=T.FIELD_SOLID, background=T.SCROLL_THUMB,
                        bordercolor=T.FIELD_SOLID, lightcolor=T.SCROLL_THUMB, darkcolor=T.SCROLL_THUMB,
                        gripcount=0, arrowsize=round(8 * S), relief="flat")
        style.map("Aero.Vertical.TScrollbar", background=[("active", "#3a7aa3")])

    def focus_ring(self, tag, x, y, w, h, r) -> None:
        self.canvas.create_polygon(_rr_points(x, y, w, h, r), fill="", outline=T.FOCUS,
                                   width=max(2, round(2 * self.S)), tags=(tag, "chrome"))

    def _photo(self, key, factory):
        return self.cache.get(key, factory)

    # ================================================================== rows / counts
    def _rows_changed(self, n: int) -> None:
        self._file_count = n
        self.table_empty.set_visible(n == 0)
        self.canvas.itemconfigure("filecount", text=f"{n} file{'s' if n != 1 else ''}")

    def _results_changed(self, n: int) -> None:
        self.results_empty.set_visible(n == 0)

    def _fit_columns(self, event) -> None:
        S = self.S
        year = round(80 * S)
        spare = max(3 * 45, event.width - year)
        for col, share in (("title", 2.0), ("artist", 1.4), ("album", 1.4)):
            self.table.column(col, width=int(spare * share / 4.8))
        self.table.column("year", width=year)

    # ================================================================== pointer
    def _hit(self, x, y):
        for obj in reversed(self._hits):
            r = obj.hit_rect()
            if r and r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]:
                return obj
        return None

    def _in_splitter(self, x, y) -> bool:
        L = getattr(self, "L", None)
        if not L:
            return False
        lx, ly, lw, lh = L["left"]
        rx = L["right"][0]
        return lx + lw <= x <= rx and ly <= y <= ly + lh

    def _set_hover(self, obj) -> None:
        if obj is self._hovered:
            return
        if self._hovered is not None:
            self._hovered.on_leave()
        self._hovered = obj
        if obj is not None:
            obj.on_enter()

    def _on_motion(self, e) -> None:
        if self._drag is not None:
            return
        obj = self._hit(e.x, e.y)
        self._set_hover(obj)
        cursor = obj.cursor() if obj else ("sb_h_double_arrow" if self._in_splitter(e.x, e.y) else "")
        if self.canvas.cget("cursor") != cursor:
            self.canvas.configure(cursor=cursor)

    def _on_press(self, e) -> None:
        obj = self._hit(e.x, e.y)
        self._pressed = obj
        if obj is not None:
            obj.on_press()
        elif self._in_splitter(e.x, e.y):
            self._drag = e.x
        else:
            self.canvas.focus_set()  # clicking empty chrome takes focus off the entries, like before

    def _on_drag(self, e) -> None:
        if self._drag is None:
            return
        L = self.L
        total = L["right"][0] + L["right"][2] - L["left"][0] - L["gap"]
        ratio = (e.x - L["left"][0] - L["gap"] / 2) / max(1, total)
        self._split = max(0.36, min(0.68, ratio))
        self.canvas.delete("splitguide")
        y0, h = L["left"][1], L["left"][3]
        self.canvas.create_line(e.x, y0 + 12 * self.S, e.x, y0 + h - 12 * self.S, fill=T.ACCENT,
                                width=max(2, round(2 * self.S)), tags=("splitguide",))

    def _on_release(self, e) -> None:
        if self._drag is not None:
            self._drag = None
            self.canvas.delete("splitguide")
            self.schedule_render(0)
            return
        obj, self._pressed = self._pressed, None
        if obj is not None:
            obj.on_release(self._hit(e.x, e.y) is obj)

    # ================================================================== layout
    def schedule_render(self, delay: int = 150) -> None:
        if self._render_job is not None:
            self.canvas.after_cancel(self._render_job)
        self._render_job = self.canvas.after(delay, self.render)

    def _layout(self, W: int, H: int) -> dict:
        S = self.S
        self.f = max(0.0, min(1.0, (H / S - 640) / (900 - 640)))
        lp = self.lerp
        P, G = lp(16, 28) * S, lp(12, 20) * S
        L = {"P": P, "G": G}
        L["header"] = (P, P, W - 2 * P, lp(78, 124) * S)
        hy = P + L["header"][3] + G
        row_h = lp(40, 50) * S
        L["row"] = (P, hy, W - 2 * P, row_h)
        status_h = lp(40, 50) * S
        L["status"] = (P, H - P - status_h, W - 2 * P, status_h)
        opt_h = 30 * S
        oy = L["status"][1] - lp(10, 16) * S - opt_h
        L["options"] = (P, oy, W - 2 * P, opt_h)
        top = hy + row_h + G
        bottom = oy - lp(10, 16) * S
        gap = G
        L["gap"] = gap
        avail_w = W - 2 * P - gap
        lw = avail_w * self._split
        L["left"] = (P, top, lw, bottom - top)
        L["right"] = (P + lw + gap, top, avail_w - lw, bottom - top)
        return L

    # ================================================================== render
    def render(self) -> None:
        self._render_job = None
        c = self.canvas
        W, H = c.winfo_width(), c.winfo_height()
        if W < 50 or H < 50:
            return
        S = self.S
        L = self.L = self._layout(W, H)
        lp = self.lerp
        body, heading = self.fonts.body, self.fonts.heading

        # ---- background (cached by size) -------------------------------------
        if self._bg_key != (W, H):
            self._bg_img = T.render_background(W, H)
            self._bg_photo = ImageTk.PhotoImage(self._bg_img)
            self._bg_key = (W, H)
            self._glass_cache = {}
        c.delete("bg", "panel", "chrome", "static")
        c.create_image(0, 0, image=self._bg_photo, anchor="nw", tags=("bg",))
        c.tag_lower("bg")

        def glass(name, rect, gloss=False, pill=False, radius=26):
            key = (name, tuple(round(v) for v in rect), gloss, pill)
            if key not in self._glass_cache:
                img, m = T.render_glass(self._bg_img, rect, radius * S, S, gloss=gloss, pill=pill)
                self._glass_cache[key] = (ImageTk.PhotoImage(img), m)
            photo, m = self._glass_cache[key]
            c.create_image(rect[0] - m, rect[1] - m, image=photo, anchor="nw", tags=("panel",))

        def inset(rect, radius, **kw):
            x, y, w, h = (round(v) for v in rect)
            photo, _ = self._photo(("inset", w, h, radius, tuple(sorted(kw.items())), S),
                                   lambda: (T.render_inset(w, h, radius * S, S, **kw), 0))
            c.create_image(x, y, image=photo, anchor="nw", tags=("static",))

        def field(rect, radius):
            x, y, w, h = (round(v) for v in rect)
            photo, _ = self._photo(("field", w, h, round(radius), S), lambda: (T.render_field(w, h, radius, S), 0))
            c.create_image(x, y, image=photo, anchor="nw", tags=("static",))

        def icon(key, factory, x, y, anchor="nw"):
            photo, m = self._photo(key, factory)
            c.create_image(x - m, y - m, image=photo, anchor=anchor, tags=("static",))

        def place(name, x, y, w, h):
            c.coords(self._windows[name], round(x), round(y))
            c.itemconfigure(self._windows[name], width=max(1, round(w)), height=max(1, round(h)))

        # ---- glass panels ------------------------------------------------------
        glass("header", L["header"], gloss=True)
        glass("left", L["left"])
        glass("right", L["right"])
        glass("status", L["status"], gloss=True, pill=True)

        # ---- header --------------------------------------------------------------
        hx, hy, hw, hh = L["header"]
        logo_h = round(lp(52, 88) * S)
        logo_w = round(logo_h * 86 / 88)
        lx = hx + lp(16, 24) * S
        icon(("logo", logo_w, logo_h, S), lambda: T.render_logo(logo_w, logo_h, S), lx, hy + (hh - logo_h) / 2)
        title_px = lp(24, 34)
        tf, sf = heading(title_px, 700), body(lp(13, 15))
        tx = lx + logo_w + lp(14, 20) * S
        block = tf.metrics("linespace") + 4 * S + sf.metrics("linespace")
        ty = hy + (hh - block) / 2
        glow_px = round(title_px * S)
        icon(("titleglow", glow_px, S), lambda: T.render_text_glow(self.app_name, glow_px, S), tx, ty)
        c.create_text(tx, ty, text=self.app_name, font=tf, fill=T.TEXT_PRIMARY, anchor="nw", tags=("chrome",))
        badge_f = body(13, 700)
        bw = round(badge_f.measure("v2.0 Beta") + 46 * S)
        bh = round(30 * S)
        bx = hx + hw - lp(16, 24) * S - bw
        by = hy + (hh - bh) / 2
        ring = round(34 * S)
        rx = bx - 14 * S - ring
        sub_room = rx - 20 * S - tx
        c.create_text(tx + 1, ty + tf.metrics("linespace") + 4 * S, text=truncate(sf, SUBTITLE, sub_room),
                      font=sf, fill=T.TEXT_SUB, anchor="nw", tags=("chrome",))
        icon(("ring", ring, S), lambda: T.render_ring(ring, S), rx, hy + (hh - ring) / 2)
        icon(("badge", bw, bh, S), lambda: T.render_pill(bw, bh, "badge", "normal", S), bx, by)
        dot = round(8 * S)
        icon(("okdot", dot, S), lambda: T.render_dot(dot, T.ACCENT_OK, S), bx + 14 * S, by + (bh - dot) / 2)
        c.create_text(bx + 14 * S + dot + 8 * S, by + bh / 2, text="v2.0 Beta", font=badge_f, fill=T.TEXT_BODY,
                      anchor="w", tags=("chrome",))

        # ---- folder row -------------------------------------------------------------
        rx0, ry, rw, rh = L["row"]
        bgap = 12 * S
        scan_w = self.scan_button.natural_width(rh)
        choose_w = self.choose_button.natural_width(rh)
        self.scan_button.place(rx0 + rw - scan_w, ry, scan_w, rh)
        self.choose_button.place(rx0 + rw - scan_w - bgap - choose_w, ry, choose_w, rh)
        fw = rw - scan_w - choose_w - 2 * bgap
        field((rx0, ry, fw, rh), rh / 2)
        isz = round(20 * S)
        icon(("folder", isz, S), lambda: (T.render_folder_icon(isz, S), 0), rx0 + 18 * S, ry + (rh - isz) / 2)
        eh = self.fonts.body(15).metrics("linespace") + 4
        place("path", rx0 + 18 * S + isz + 10 * S, ry + (rh - eh) / 2, fw - 18 * S - isz - 10 * S - 18 * S, eh)

        # ---- left panel ----------------------------------------------------------------
        pp, ig = lp(14, 22) * S, lp(9, 16) * S
        x, y, w, h = L["left"]
        self._section(x + pp, y + pp, "Songs in folder", ("#38d6ff", "#0b6fa8", (80, 220, 255, 204)))
        hrow = lp(22, 26) * S
        c.create_text(x + w - pp, y + pp + hrow / 2, text=f"{self._file_count} file{'s' if self._file_count != 1 else ''}",
                      font=body(13), fill=T.TEXT_MUTED, anchor="e", tags=("chrome", "filecount"))
        hint_f = body(lp(13, 14))
        hint_h = hint_f.metrics("linespace")
        box = (x + pp, y + pp + hrow + ig, w - 2 * pp, h - 2 * pp - hrow - ig - hint_h - ig * 0.8)
        inset(box, 18)
        c.create_text(x + pp, y + h - pp - hint_h / 2, text="Select a song to find matching catalog records.",
                      font=hint_f, fill=T.TEXT_MUTED, anchor="w", tags=("chrome",))
        k = 6 * S  # keep square widget corners inside the rounded box
        sbw = round(10 * S)
        place("table", box[0] + k, box[1] + k, box[2] - 2 * k - sbw - 2 * S, box[3] - 2 * k)
        place("scroll", box[0] + box[2] - k - sbw, box[1] + k, sbw, box[3] - 2 * k)
        heading_h = body(13, 700).metrics("linespace") + round(18 * S) + 2

        # ---- right panel ----------------------------------------------------------------
        x, y, w, h = L["right"]
        ix, iw = x + pp, w - 2 * pp
        cy = y + pp
        self._section(ix, cy, "Catalog matches", ("#7aa0ff", "#2a4cc0", (120, 150, 255, 204)))
        cy += hrow + ig
        lab_f = body(13, 700)
        col = (iw - 14 * S) / 2
        field_h = lp(36, 44) * S
        for i, (label, name) in enumerate((("Search title", "title"), ("Artist", "artist"))):
            fx = ix + i * (col + 14 * S)
            c.create_text(fx + 2, cy, text=label, font=lab_f, fill=T.TEXT_LABEL, anchor="nw", tags=("chrome",))
            fy = cy + lab_f.metrics("linespace") + 6 * S
            field((fx, fy, col, field_h), 14 * S)
            place(name, fx + 16 * S, fy + (field_h - eh) / 2, col - 32 * S, eh)
        cy = cy + lab_f.metrics("linespace") + 6 * S + field_h + ig
        sec_h, apply_h = lp(34, 42) * S, lp(38, 46) * S
        bottom = y + h - pp
        rg = lp(8, 16) * S  # tighter vertical rhythm in the catalog column on shorter windows
        cy -= ig - rg
        # The results list keeps at least 4 visible rows (it's where you pick a match); the
        # details/cover row takes the rest (its text scrolls).
        line = body(14).metrics("linespace") + 1
        box_pad = 20 * S + 2
        want_rows = 4
        review_target = min(col, 290 * S)
        # Reference layout (buttons on their own row under the results) when the window is tall
        # enough; otherwise stack the two buttons beside the results list to free ~65px of height.
        buttons = (self.search_button, self.cover_button)  # Get lyrics lives inside the Lyrics tab
        row_w = sum(b.natural_width(sec_h) for b in buttons) + 10 * S
        avail_full = bottom - cy - (rg + sec_h + rg + rg + apply_h)
        side = avail_full < want_rows * line + box_pad + 200 * S or row_w > iw
        stack_h = 2 * sec_h + 8 * S
        avail = bottom - cy - ((rg + rg + apply_h) if side else (rg + sec_h + rg + rg + apply_h))
        review_min = lp(88, 120) * S
        floor_h = max(line + box_pad, stack_h if side else 0)
        results_h = max(want_rows * line + box_pad, floor_h)
        if avail - results_h < review_min:              # very small window: shrink the list
            results_h = max(floor_h, avail - review_min)
        review_h = min(review_target, avail - results_h)
        results_h = avail - review_h                    # any spare height also goes to the list
        rows = max(1, int((results_h - box_pad) // line))
        snapped = max(floor_h, rows * line + box_pad)   # whole rows only, leftover to the review row
        review_h += results_h - snapped
        results_h = snapped
        self._result_rows = rows
        btn_w = max(b.natural_width(sec_h) for b in buttons)
        list_w = iw - (btn_w + 12 * S if side else 0)
        inset((ix, cy, list_w, results_h), 18, dashed=True, inner_shadow=False)
        lsw = round(10 * S)
        fit = max(1, int((results_h - box_pad) // line))   # whole rows only: no half-cut last row
        list_h = fit * line + 2
        list_y = cy + (results_h - list_h) / 2
        place("list", ix + 12 * S, list_y, list_w - 24 * S - lsw - 4 * S, list_h)
        place("listscroll", ix + list_w - 12 * S - lsw, list_y, lsw, list_h)
        if side:
            by = cy + (results_h - stack_h) / 2
            for i, b in enumerate(buttons):
                b.place(ix + iw - btn_w, by + i * (sec_h + 8 * S), btn_w, sec_h)
            cy += results_h + rg
        else:
            cy += results_h + rg
            bx_ = ix
            for b in buttons:
                bw_ = b.natural_width(sec_h)
                b.place(bx_, cy, bw_, sec_h)
                bx_ += bw_ + 10 * S
            cy += sec_h + rg
        inset((ix, cy, col, review_h), 18, fill=(8, 31, 51, 255))
        # Details / Lyrics tabs across the top of the box, then the active text below.
        pad_d = lp(10, 16) * S
        tab_h = round(lp(24, 28) * S)
        tx_ = ix + 10 * S
        for key in ("details", "lyrics"):
            tab = self.tabs[key]
            tw_ = tab.natural_width()
            tab.place(tx_, cy + lp(8, 12) * S, tw_, tab_h)
            tx_ += tw_ + 6 * S
        dtop = cy + lp(8, 12) * S + tab_h + lp(6, 10) * S
        text_h = max(10, cy + review_h - pad_d - dtop)
        for widget in (self.details, self.lyrics):
            widget.configure(font=body(lp(13, 14)), spacing1=round(lp(0, 2) * S))
        place("details", ix + 16 * S, dtop, col - 32 * S, text_h)
        place("lyrics", ix + 16 * S, dtop, col - 32 * S - lsw - 6 * S, text_h)
        place("lyricsscroll", ix + col - 12 * S - lsw, dtop, lsw, text_h)
        self._lyrics_area = (ix + 16 * S, dtop, col - 32 * S, text_h, sec_h)
        self.select_tab(self._tab)
        cover_rect = (ix + col + 14 * S, cy, col, review_h)
        inset(cover_rect, 18, fill=(0, 14, 30, 120), radial=True)
        self.cover_label.place(*cover_rect)
        ah = apply_h
        aw = self.apply_button.natural_width(ah)
        self.apply_button.place(ix + iw - aw, bottom - ah, aw, ah)
        shield = round(16 * S)
        icon(("shield", shield, S), lambda: (T.render_shield_icon(shield, S), 0), ix, bottom - ah / 2 - shield / 2)
        c.create_text(ix + shield + 8 * S, bottom - ah / 2, text=truncate(body(lp(13, 14)),
                      "Original is backed up before saving.", iw - aw - shield - 24 * S),
                      font=body(lp(13, 14)), fill=T.TEXT_MUTED, anchor="w", tags=("chrome",))

        # ---- options row -------------------------------------------------------------------
        ox, oy, ow, oh = L["options"]
        t1, t2, t3 = self.toggles
        t1.place(ox + 6 * S, oy)
        t2.place(ox + 6 * S + t1.width() + 28 * S, oy)
        t3.place(ox + ow - 6 * S - t3.width(), oy)

        # ---- status bar ------------------------------------------------------------------
        sx, sy, sw2, sh2 = L["status"]
        self._status_dot = (sx + 26 * S, sy + sh2 / 2)
        self._status_bg = T.mix("#123a57", "#0b2238", 0.4)
        self._draw_status_text()

        # ---- real widgets visible, empty states, stacking ----------------------------------
        self.table_empty.set_visible(len(self.table.get_children()) == 0, top=heading_h)
        self.results_empty.set_visible(self.match_list.size() == 0, top=0)
        for p in self._placeholders:
            p.update()
        c.tag_raise("panel", "bg")
        c.tag_raise("static", "panel")
        c.tag_raise("chrome", "static")
        self.bubbles.reset()
        if self.animate.get():
            self.bubbles.resume()
        else:
            self.bubbles.pause(static=True)

    def _section(self, x, y, text, sphere) -> None:
        S, c = self.S, self.canvas
        d = round(14 * S)
        hrow = self.lerp(22, 26) * S
        inner, outer, glow = sphere
        photo, m = self._photo(("sphere", d, inner, S), lambda: T.render_sphere(d, inner, outer, glow, S))
        c.create_image(x - m, y + (hrow - d) / 2 - m, image=photo, anchor="nw", tags=("static",))
        c.create_text(x + d + 12 * S, y + hrow / 2, text=text, font=self.fonts.heading(self.lerp(17, 20), 600),
                      fill=T.TEXT_PRIMARY, anchor="w", tags=("chrome",))

    # ================================================================== status
    def _draw_status_text(self) -> None:
        L = getattr(self, "L", None)
        if not L:
            return
        c, S = self.canvas, self.S
        c.delete("statustext")
        sx, sy, sw, sh = L["status"]
        font = self.fonts.body(self.lerp(14, 15))
        c.create_text(sx + 44 * S, sy + sh / 2, text=truncate(font, self.status.get(), sw - 70 * S), font=font,
                      fill=T.TEXT_LABEL, anchor="w", tags=("chrome", "statustext"))
        self._status_pulse(None)

    def _status_pulse(self, phase) -> None:
        if not getattr(self, "_status_dot", None):
            return
        c, S = self.canvas, self.S
        x, y = self._status_dot
        c.delete("pulse")
        r = 5 * S
        if phase is not None and phase < 0.7:
            t = phase / 0.7
            rr = r + 10 * S * t
            col = T.mix("#5adcff", self._status_bg, 0.3 + 0.7 * t)
            c.create_oval(x - rr, y - rr, x + rr, y + rr, fill=col, outline="", tags=("chrome", "pulse"))
        c.create_oval(x - r, y - r, x + r, y + r, fill=T.ACCENT, outline="", tags=("chrome", "pulse"))
