"""Aqua Night components that live on one full-window canvas.

Chrome (buttons, toggles, icons, the cover view, background sprites) is drawn as canvas
items from cached Pillow images. Real Tk widgets are used only for typing/scrolling:
entries, the song table, the results list and the details text.
"""
from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from . import theme as T


def smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def truncate(font, text: str, width: int) -> str:
    if font.measure(text) <= width:
        return text
    while text and font.measure(text + "…") > width:
        text = text[:-1]
    return text + "…"


class ImageCache:
    """Keeps PhotoImages alive and avoids re-rendering identical images."""

    def __init__(self) -> None:
        self._items: dict = {}

    def get(self, key, factory):
        if key not in self._items:
            img, margin = factory()
            self._items[key] = (ImageTk.PhotoImage(img), margin)
        return self._items[key]

    def clear(self, prefix=None) -> None:
        if prefix is None:
            self._items.clear()
        else:
            for key in [k for k in self._items if k[0] == prefix]:
                del self._items[key]


# =========================================================================== buttons
class GlossyButton:
    """Canvas-item pill button with normal/hover/pressed/disabled images.

    Keeps the small ttk.Button-style API the app uses: configure(state=...), cget("state").
    """

    def __init__(self, view, text: str, command, kind: str = "secondary", state: str = "normal") -> None:
        self.view, self.canvas = view, view.canvas
        self.text, self.command, self.kind, self._state = text, command, kind, state
        self.tag = f"btn{id(self)}"
        self.rect = None
        self._hover = self._pressed = self._focus = False
        view.register_hit(self)  # pointer hit-testing uses the real pill rect, not the glow margin

    # --- API used by the app ------------------------------------------------
    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self._state = kw.pop("state")
            self.draw()
        if "text" in kw:
            self.text = kw.pop("text")
            self.draw()

    config = configure

    def cget(self, key):
        return {"state": self._state, "text": self.text}.get(key)

    def invoke(self) -> None:
        if self._state != "disabled" and self.command:
            self.command()

    # --- pointer (called by the view's hit-tester) ---------------------------
    def hit_rect(self):
        return self.rect

    def cursor(self) -> str:
        return "hand2" if self._state != "disabled" else ""

    def on_enter(self) -> None:
        self._set(hover=True)

    def on_leave(self) -> None:
        self._set(hover=False, pressed=False)

    def on_press(self) -> None:
        if self._state != "disabled":
            self._set(pressed=True)

    def on_release(self, inside: bool) -> None:
        was = self._pressed
        self._set(pressed=False)
        if was and inside:
            self.invoke()

    # --- layout -------------------------------------------------------------
    def font(self):
        return self.view.fonts.body(self.view.lerp(13, 15 if self.kind == "primary" else 14), 700)

    def natural_width(self, height: float) -> int:
        pad = (28 if self.kind == "primary" else 22) * self.view.S
        return round(self.font().measure(self.text) + 2 * pad)

    def place(self, x: float, y: float, w: float, h: float) -> None:
        self.rect = (round(x), round(y), round(w), round(h))
        self.draw()

    def hide(self) -> None:
        """Remove from the canvas (no drawing, no hit area, skipped by Tab) until placed again."""
        self.rect = None
        self._hover = self._pressed = False
        self.draw()

    def focus(self, value: bool) -> None:
        self._focus = value
        self.draw()

    def _set(self, **flags) -> None:
        for k, v in flags.items():
            setattr(self, "_" + k, v)
        self.draw()

    def draw(self) -> None:
        c = self.canvas
        c.delete(self.tag)
        if not self.rect:
            return
        x, y, w, h = self.rect
        state = ("disabled" if self._state == "disabled" else "pressed" if self._pressed
                 else "hover" if self._hover else "normal")
        S = self.view.S
        photo, m = self.view.cache.get(("pill", w, h, self.kind, state, S),
                                       lambda: T.render_pill(w, h, self.kind, state, S))
        c.create_image(x - m, y - m, image=photo, anchor="nw", tags=(self.tag, "chrome"))
        dy = 1 if state == "pressed" else 0
        cx, cy = x + w / 2, y + h / 2 + dy
        font = self.font()
        if self.kind == "primary":
            if state != "disabled":
                c.create_text(cx, cy + 1, text=self.text, font=font, fill="#0b3a63", tags=(self.tag, "chrome"))
            fill = "#ffffff" if state != "disabled" else T.mix("#ffffff", "#0b2238", 0.55)
        else:
            fill = T.TEXT_BODY if state != "disabled" else T.mix(T.TEXT_BODY, "#0b2238", 0.55)
        c.create_text(cx, cy, text=self.text, font=font, fill=fill, tags=(self.tag, "chrome"))
        if self._focus:
            self.view.focus_ring(self.tag, x - 3 * S, y - 3 * S, w + 6 * S, h + 6 * S, (h + 6 * S) / 2)


# =========================================================================== toggles
class Toggle:
    """56x30 glossy switch bound to a BooleanVar, with a 120 ms knob slide."""

    def __init__(self, view, text: str, variable: tk.BooleanVar) -> None:
        self.view, self.canvas, self.text, self.var = view, view.canvas, text, variable
        self.tag = f"tgl{id(self)}"
        self.rect = None
        self._pos = 1.0 if variable.get() else 0.0
        self._focus = False
        self._anim = None
        variable.trace_add("write", lambda *_a: self._animate())
        view.register_hit(self)

    def invoke(self) -> None:
        self.var.set(not self.var.get())

    # --- pointer (called by the view's hit-tester) ---------------------------
    def hit_rect(self):
        if not self.rect:
            return None
        return (*self.rect, self.width(), round(30 * self.view.S))

    def cursor(self) -> str:
        return "hand2"

    def on_enter(self) -> None:
        pass

    def on_leave(self) -> None:
        pass

    def on_press(self) -> None:
        pass

    def on_release(self, inside: bool) -> None:
        if inside:
            self.invoke()

    def focus(self, value: bool) -> None:
        self._focus = value
        self.draw()

    def width(self) -> int:
        S = self.view.S
        return round(56 * S + 12 * S + self.view.fonts.body(self.view.lerp(14, 15)).measure(self.text))

    def place(self, x: float, y: float) -> None:
        self.rect = (round(x), round(y))
        self.draw()

    def _animate(self) -> None:
        target = 1.0 if self.var.get() else 0.0
        if self._anim:
            self.canvas.after_cancel(self._anim)
        start, t0 = self._pos, time.monotonic()

        def step():
            t = min(1.0, (time.monotonic() - t0) / 0.12)
            self._pos = start + (target - start) * smooth(t)
            self.draw()
            self._anim = self.canvas.after(20, step) if t < 1 else None
        step()

    def draw(self) -> None:
        c = self.canvas
        c.delete(self.tag)
        if not self.rect:
            return
        S = self.view.S
        x, y = self.rect
        tw, th, kd = round(56 * S), round(30 * S), round(22 * S)
        on = self._pos >= 0.5
        track, m = self.view.cache.get(("track", tw, th, on, S), lambda: T.render_toggle_track(tw, th, on, S))
        c.create_image(x - m, y - m, image=track, anchor="nw", tags=(self.tag, "chrome"))
        knob, km = self.view.cache.get(("knob", kd, S), lambda: T.render_knob(kd, S))
        inset = (th - kd) / 2
        kx = x + inset + (tw - kd - 2 * inset) * self._pos
        c.create_image(kx - km, y + inset - km, image=knob, anchor="nw", tags=(self.tag, "chrome"))
        font = self.view.fonts.body(self.view.lerp(14, 15))
        c.create_text(x + tw + 12 * S, y + th / 2, text=self.text, anchor="w", font=font,
                      fill=T.TEXT_BODY, tags=(self.tag, "chrome"))
        if self._focus:
            self.view.focus_ring(self.tag, x - 4 * S, y - 4 * S, tw + 8 * S, th + 8 * S, (th + 8 * S) / 2)


# =========================================================================== tabs
class TabPill:
    """Small glass tab ('Details' / 'Lyrics') drawn on the canvas; keyboard reachable."""

    def __init__(self, view, text: str, on_select) -> None:
        self.view, self.canvas, self.text, self.on_select = view, view.canvas, text, on_select
        self.tag = f"tab{id(self)}"
        self.rect = None
        self.selected = False
        self._hover = self._focus = False
        self._state = "normal"
        view.register_hit(self)

    def font(self):
        return self.view.fonts.body(self.view.lerp(12, 13), 700)

    def natural_width(self) -> int:
        return round(self.font().measure(self.text) + 26 * self.view.S)

    def hit_rect(self):
        return self.rect

    def cursor(self) -> str:
        return "hand2"

    def on_enter(self) -> None:
        self._hover = True
        self.draw()

    def on_leave(self) -> None:
        self._hover = False
        self.draw()

    def on_press(self) -> None:
        pass

    def on_release(self, inside: bool) -> None:
        if inside:
            self.invoke()

    def invoke(self) -> None:
        self.on_select()

    def focus(self, value: bool) -> None:
        self._focus = value
        self.draw()

    def place(self, x, y, w, h) -> None:
        self.rect = (round(x), round(y), round(w), round(h))
        self.draw()

    def draw(self) -> None:
        c = self.canvas
        c.delete(self.tag)
        if not self.rect:
            return
        x, y, w, h = self.rect
        S = self.view.S
        if self.selected:
            photo, m = self.view.cache.get(("tabpill", w, h, S), lambda: T.render_pill(w, h, "badge", "normal", S))
            c.create_image(x - m, y - m, image=photo, anchor="nw", tags=(self.tag, "chrome"))
        fill = T.TEXT_PRIMARY if self.selected else (T.TEXT_BODY if self._hover else T.TEXT_MUTED)
        c.create_text(x + w / 2, y + h / 2, text=self.text.upper(), font=self.font(), fill=fill,
                      tags=(self.tag, "chrome"))
        if self._focus:
            self.view.focus_ring(self.tag, x - 3 * S, y - 3 * S, w + 6 * S, h + 6 * S, (h + 6 * S) / 2)


# =========================================================================== entries
class Placeholder:
    """Grey hint shown over an empty Entry. Never written into the Entry's variable."""

    def __init__(self, entry: tk.Entry, variable: tk.StringVar, text: str, font) -> None:
        self.entry, self.var = entry, variable
        self.label = tk.Label(entry.master, text=text, bg=T.FIELD_SOLID, fg=T.PLACEHOLDER, font=font,
                              anchor="w", bd=0, padx=0, pady=0, cursor="xterm")
        self.label.bind("<Button-1>", lambda _e: entry.focus_set())
        variable.trace_add("write", lambda *_a: self.update())
        entry.bind("<FocusIn>", lambda _e: self.update(), add="+")
        entry.bind("<FocusOut>", lambda _e: self.update(), add="+")

    def update(self) -> None:
        if self.var.get() or self.entry.focus_get() is self.entry or not self.entry.winfo_ismapped():
            self.label.place_forget()
        else:
            self.label.place(in_=self.entry, x=1, rely=0.5, anchor="w", relwidth=1.0)
            self.label.lift()


# =========================================================================== table & list
class AeroTreeview(ttk.Treeview):
    """Treeview with alternating rows, hover rows and an empty-state hook.

    Row tags never hide the selection colour: selected rows have their tags cleared.
    """

    def __init__(self, master, on_rows_changed=None, **kw) -> None:
        super().__init__(master, **kw)
        self._on_rows_changed = on_rows_changed
        self._hover = ""
        self.bind("<Motion>", self._motion, add="+")
        self.bind("<Leave>", lambda _e: self._set_hover(""), add="+")
        self.bind("<<TreeviewSelect>>", lambda _e: self.retag(), add="+")

    def insert(self, parent, index, iid=None, **kw):
        item = super().insert(parent, index, iid=iid, **kw)
        n = len(self.get_children())
        self.item(item, tags=("odd",) if n % 2 == 0 else ())
        self._changed()
        return item

    def delete(self, *items):
        super().delete(*items)
        self._hover = ""
        self.retag()
        self._changed()

    def _changed(self) -> None:
        if self._on_rows_changed:
            self._on_rows_changed(len(self.get_children()))

    def retag(self) -> None:
        selected = set(self.selection())
        for i, row in enumerate(self.get_children()):
            if row in selected:
                tags = ()
            elif row == self._hover:
                tags = ("hover",)
            else:
                tags = ("odd",) if i % 2 else ()
            if tuple(self.item(row, "tags") or ()) != tags:
                self.item(row, tags=tags)

    def _set_hover(self, row: str) -> None:
        if row != self._hover:
            self._hover = row
            self.retag()

    def _motion(self, e) -> None:
        self._set_hover(self.identify_row(e.y))


class AeroListbox(tk.Listbox):
    """Listbox with hover rows and an empty-state hook."""

    def __init__(self, master, on_rows_changed=None, **kw) -> None:
        super().__init__(master, **kw)
        self._on_rows_changed = on_rows_changed
        self._hover = None
        self.bind("<Motion>", self._motion, add="+")
        self.bind("<Leave>", lambda _e: self._unhover(), add="+")

    def insert(self, index, *elements):
        result = super().insert(index, *elements)
        self._changed()
        return result

    def delete(self, first, last=None):
        result = super().delete(first, last)
        self._hover = None
        self._changed()
        return result

    def _changed(self) -> None:
        if self._on_rows_changed:
            self._on_rows_changed(self.size())

    def _motion(self, e) -> None:
        index = self.nearest(e.y)
        bbox = self.bbox(index) if index >= 0 else None
        inside = bool(bbox) and bbox[1] <= e.y <= bbox[1] + bbox[3]
        if inside and index == self._hover:
            return
        self._unhover()
        if inside:
            self.itemconfigure(index, background=T.TABLE_HOVER)
            self._hover = index

    def _unhover(self) -> None:
        if self._hover is not None and self._hover < self.size():
            try:
                self.itemconfigure(self._hover, background=T.FIELD_SOLID)
            except tk.TclError:
                pass
        self._hover = None


class EmptyState:
    """Centred empty-state overlay (icon + title + hint) placed over a real widget."""

    def __init__(self, view, host: tk.Widget, title: str, hint: str, icon: bool) -> None:
        self.view, self.host, self.title, self.hint, self.icon = view, host, title, hint, icon
        self.canvas = tk.Canvas(host.master, bg=T.FIELD_SOLID, highlightthickness=0, bd=0)
        self.canvas.bind("<Configure>", lambda _e: self.draw())
        self.top = 0
        self.visible = False

    def set_visible(self, visible: bool, top: int = None) -> None:
        if top is not None:
            self.top = top
        self.visible = visible
        if visible and self.host.winfo_ismapped():
            self.canvas.place(in_=self.host, x=0, y=self.top, relwidth=1, relheight=1, height=-self.top)
            tk.Misc.tkraise(self.canvas)  # widget stacking (Canvas.lift would raise a canvas *item*)
            self.draw()
        else:
            self.canvas.place_forget()

    def draw(self) -> None:
        c, v = self.canvas, self.view
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10 or h < 10:
            return
        S = v.S
        title_f, hint_f = v.fonts.heading(v.lerp(16, 18), 600), v.fonts.body(v.lerp(13, 14))
        hint_lines = max(1, math.ceil(hint_f.measure(self.hint) / max(1, min(w - 40 * S, 340 * S))))
        title_h = title_f.metrics("linespace") + 8 * S if self.title else 0
        block = title_h + hint_lines * hint_f.metrics("linespace")
        icon_d = round(v.lerp(64, 96) * S) if self.icon and h > 220 * S else 0
        if icon_d:
            block += icon_d + 14 * S
        y = (h - block) / 2
        if icon_d:
            photo, m = v.cache.get(("emptybubble", icon_d, S), lambda: T.render_empty_bubble(icon_d, S))
            c.create_image(w / 2 - icon_d / 2 - m, y - m, image=photo, anchor="nw")
            y += icon_d + 14 * S
        if self.title:
            c.create_text(w / 2, y, text=self.title, font=title_f, fill=T.TEXT_PRIMARY, anchor="n")
            y += title_h
        if self.hint:
            c.create_text(w / 2, y, text=self.hint, font=hint_f, fill=T.TEXT_MUTED, anchor="n",
                          justify="center", width=min(w - 40 * S, 340 * S))


# =========================================================================== cover
class CoverView:
    """Stands in for the old cover tk.Label: configure(image=..., text=...), winfo_width/height."""

    DEFAULT = "Cover artwork\npreview appears here"

    def __init__(self, view) -> None:
        self.view, self.canvas = view, view.canvas
        self.image = None
        self.text = self.DEFAULT
        self.rect = (0, 0, 1, 1)

    def configure(self, cnf=None, **kw):
        if "image" in kw:
            self.image = kw["image"] or None
        if "text" in kw:
            self.text = kw["text"] or ""
        self.draw()

    config = configure

    def winfo_width(self) -> int:
        return max(1, self.rect[2] - round(24 * self.view.S))

    def winfo_height(self) -> int:
        return max(1, self.rect[3] - round(24 * self.view.S))

    def place(self, x, y, w, h) -> None:
        self.rect = (round(x), round(y), round(w), round(h))
        self.draw()

    def draw(self) -> None:
        c, v = self.canvas, self.view
        c.delete("cover")
        x, y, w, h = self.rect
        if w < 10:
            return
        S = v.S
        if self.image is not None:
            c.create_image(x + w / 2, y + h / 2, image=self.image, tags=("cover", "chrome"))
            return
        font = v.fonts.body(v.lerp(12, 13))
        caption = self.text.replace("Cover artwork preview appears here", self.DEFAULT)
        lines = max(1, caption.count("\n") + 1 + font.measure(caption) // max(1, w - 24 * S))
        text_h = lines * font.metrics("linespace")
        d = round(max(36 * S, min(96 * S, h - text_h - 40 * S)))
        top = y + (h - (d + 12 * S + text_h)) / 2
        photo, m = v.cache.get(("disc", d, S), lambda: T.render_disc(d, S))
        c.create_image(x + w / 2 - d / 2 - m, top - m, image=photo, anchor="nw", tags=("cover", "chrome"))
        c.create_text(x + w / 2, top + d + 12 * S, text=caption, font=font, fill=T.TEXT_MUTED,
                      justify="center", anchor="n", width=w - 24 * S, tags=("cover", "chrome"))


# =========================================================================== keyboard focus
class FocusManager:
    """Tab order across real widgets and canvas-drawn buttons/toggles, with a visible ring."""

    def __init__(self, view) -> None:
        self.view, self.canvas = view, view.canvas
        self.order: list = []
        self.active = None
        root = self.canvas.winfo_toplevel()
        self.root = root
        root.bind_all("<Tab>", lambda e: self._move(e, 1))
        root.bind_all("<Shift-Tab>", lambda e: self._move(e, -1))
        self.canvas.bind("<KeyPress-space>", lambda _e: self._activate())
        self.canvas.bind("<Return>", lambda _e: self._activate())
        self.canvas.bind("<FocusOut>", lambda _e: self._set_active(None))

    @staticmethod
    def _focusable(item) -> bool:
        if isinstance(item, tk.Misc):
            return bool(item.winfo_ismapped())
        return getattr(item, "_state", "normal") != "disabled" and getattr(item, "rect", True) is not None

    def _move(self, event, step: int):
        if event.widget.winfo_toplevel() is not self.root:
            nxt = event.widget.tk_focusNext() if step > 0 else event.widget.tk_focusPrev()
            if nxt:
                nxt.focus_set()
            return "break"
        current = self.active if self.canvas.focus_get() is self.canvas else event.widget
        try:
            idx = self.order.index(current)
        except ValueError:
            idx = -1 if step > 0 else 0
        for _ in range(len(self.order)):
            idx = (idx + step) % len(self.order)
            item = self.order[idx]
            if self._focusable(item):
                if isinstance(item, tk.Misc):
                    self._set_active(None)
                    item.focus_set()
                else:
                    self.canvas.focus_set()
                    self._set_active(item)
                break
        return "break"

    def _set_active(self, item) -> None:
        if self.active is not None and self.active is not item:
            self.active.focus(False)
        self.active = item
        if item is not None:
            item.focus(True)

    def _activate(self):
        if self.active is not None:
            self.active.invoke()
        return "break"


# =========================================================================== background animation
SPRITES = (  # kind, size, (fx, fy), anchors, cycle, delay, motion, colours
    ("glow", 260, (0.06, 0.14), "lt", 14, 0, "pulse", ((0, 200, 255), 0.45, 10)),
    ("glow", 320, (0.04, 0.02), "rt", 18, -6, "pulse", ((110, 120, 255), 0.40, 12)),
    ("glow", 280, (0.62, 0.04), "lb", 16, -3, "pulse", ((0, 255, 210), 0.28, 12)),
    ("bubble", 90, (0.18, 0.62), "lt", 13, 0, "A", ((140, 225, 255), (20, 120, 200), 0.75, 0.28, 0.10, True)),
    ("bubble", 54, (0.44, 0.30), "lt", 11, -4, "B", ((140, 225, 255), (20, 120, 200), 0.70, 0.25, 0.0, True)),
    ("bubble", 130, (0.22, 0.48), "rt", 17, -8, "A", ((160, 170, 255), (60, 80, 200), 0.60, 0.22, 0.08, True)),
    ("bubble", 40, (0.08, 0.10), "lb", 9, -2, "B", ((120, 255, 220), (0, 160, 140), 0.80, 0.25, 0.0, False)),
    ("bubble", 70, (0.08, 0.18), "rb", 15, -10, "B", ((140, 225, 255), (20, 120, 200), 0.70, 0.25, 0.0, True)),
    ("bubble", 64, (0.30, 0.06), "lt", 19, -12, "A", ((140, 225, 255), (20, 120, 200), 0.65, 0.22, 0.0, False)),
)
ALPHA_STEPS = 14
SCALE_STEPS = 4


def _segments(p: float, points) -> float:
    """Piecewise eased interpolation through (pos, value) keyframes."""
    for (p0, v0), (p1, v1) in zip(points, points[1:]):
        if p <= p1:
            return v0 + (v1 - v0) * smooth((p - p0) / (p1 - p0) if p1 > p0 else 1)
    return points[-1][1]


class BubbleBackground:
    """Drifting bubbles and pulsing glows: one after() loop, pre-rendered sprites, pausable."""

    FRAME_MS = 40

    def __init__(self, view, enabled_var: tk.BooleanVar) -> None:
        self.view, self.canvas, self.enabled = view, view.canvas, enabled_var
        self.items = [None] * len(SPRITES)
        self.keys = [None] * len(SPRITES)
        self.photos: dict = {}
        self._job = None
        self._unfocused_since = None
        self.status_pulse = None  # callable(phase) supplied by the view
        root = self.canvas.winfo_toplevel()
        self.root = root
        root.bind("<Unmap>", lambda e: e.widget is root and self.pause(), add="+")
        root.bind("<Map>", lambda e: e.widget is root and self.resume(), add="+")
        root.bind("<FocusIn>", lambda _e: self._focus_in(), add="+")
        root.bind("<FocusOut>", lambda _e: self._focus_out(), add="+")
        enabled_var.trace_add("write", lambda *_a: self.resume() if enabled_var.get() else self.pause(static=True))

    # --- sprite images -------------------------------------------------------
    def _photo(self, i: int, alpha_idx: int, scale_idx: int):
        key = (i, alpha_idx, scale_idx, self.view.S)
        if key not in self.photos:
            kind, size, _pos, _anch, _cyc, _del, motion, spec = SPRITES[i]
            S = self.view.S
            base_key = ("base", i, scale_idx, S)
            if base_key not in self.photos:
                if kind == "glow":
                    img, _m = T.render_glow_sprite(size * S, spec[0], spec[1], spec[2] * S)
                else:
                    lo, hi = (0.85, 1.08) if motion == "A" else (1.0, 1.15)
                    sc = lo + (hi - lo) * scale_idx / (SCALE_STEPS - 1)
                    img = T.render_bubble_sprite(size * S * sc, *spec)
                self.photos[base_key] = img
            img = T.multiply_alpha(self.photos[base_key], alpha_idx / (ALPHA_STEPS - 1))
            self.photos[key] = ImageTk.PhotoImage(img)
        return self.photos[key]

    def reset(self) -> None:
        """Called after a re-layout/resize: rebuild positions next frame (sizes depend on scale only)."""
        for item in self.items:
            if item:
                self.canvas.delete(item)
        self.items = [None] * len(SPRITES)
        self.keys = [None] * len(SPRITES)
        self.frame(time.monotonic())

    # --- motion ----------------------------------------------------------------
    def _state(self, i: int, now: float, static: bool):
        kind, size, (fx, fy), anchors, cycle, delay, motion, _spec = SPRITES[i]
        W, H = self.canvas.winfo_width(), self.canvas.winfo_height()
        S = self.view.S
        left = fx * W if anchors[0] == "l" else W - fx * W - size * S
        top = fy * H if anchors[1] == "t" else H - fy * H - size * S
        cx, cy = left + size * S / 2, top + size * S / 2
        if static:
            return cx, cy, 0.45, 1 if motion != "pulse" else 0
        p = ((now - delay) / cycle) % 1.0
        if motion == "pulse":
            return cx, cy, 0.35 + 0.40 * smooth(1 - abs(2 * p - 1)), 0
        e = smooth(p)
        if motion == "A":
            dx, dy, sc = 60 * e, 40 - 160 * e, e
            op = _segments(p, ((0, 0), (0.25, 1), (0.6, 0.85), (1, 0)))
        else:
            dx, dy, sc = -80 * e, -90 * e, e
            op = _segments(p, ((0, 0), (0.3, 0.9), (0.7, 0.7), (1, 0)))
        return cx + dx * S, cy + dy * S, op, round(sc * (SCALE_STEPS - 1))

    def frame(self, now: float, static: bool = False) -> None:
        c = self.canvas
        for i in range(len(SPRITES)):
            x, y, op, sidx = self._state(i, now, static)
            aidx = round(op * (ALPHA_STEPS - 1))
            if aidx <= 0:
                if self.items[i]:
                    c.itemconfigure(self.items[i], state="hidden")
                continue
            key = (aidx, sidx)
            photo = self._photo(i, aidx, sidx)
            if self.items[i] is None:
                self.items[i] = c.create_image(x, y, image=photo, tags=("sprite",))
                c.tag_raise("sprite", "bg")
                c.tag_lower("sprite", "panel")
            else:
                if self.keys[i] != key:
                    c.itemconfigure(self.items[i], image=photo)
                c.coords(self.items[i], x, y)
                c.itemconfigure(self.items[i], state="normal")
            self.keys[i] = key
        if self.status_pulse:
            self.status_pulse(None if static else (now % 2.0) / 2.0)

    # --- loop control -----------------------------------------------------------
    def _running_allowed(self) -> bool:
        if not self.enabled.get():
            return False
        try:
            if self.root.state() == "iconic":
                return False
        except tk.TclError:
            return False
        if self._unfocused_since and time.monotonic() - self._unfocused_since > 10:
            return False
        return True

    def _tick(self) -> None:
        self._job = None
        if not self._running_allowed():
            return
        self.frame(time.monotonic())
        self._job = self.canvas.after(self.FRAME_MS, self._tick)

    def resume(self) -> None:
        if self._job is None and self._running_allowed():
            self._tick()

    def pause(self, static: bool = False) -> None:
        if self._job is not None:
            self.canvas.after_cancel(self._job)
            self._job = None
        if static:
            self.frame(time.monotonic(), static=True)

    def _focus_in(self) -> None:
        self._unfocused_since = None
        self.resume()

    def _focus_out(self) -> None:
        if self._unfocused_since is None:
            self._unfocused_since = time.monotonic()
