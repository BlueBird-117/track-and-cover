"""Aqua Night theme: colour tokens, font registration and Pillow renderers.

Everything here is pure presentation. All sizes passed to the render functions are
device pixels (already multiplied by the UI scale factor).
"""
from __future__ import annotations

import ctypes
import json
import math
import os
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# --------------------------------------------------------------------------- paths
APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def asset(name: str) -> Path:
    return APP_DIR / "assets" / name


FONT_FILES = {
    ("Exo 2", 600): "Exo2-600.ttf",
    ("Exo 2", 700): "Exo2-700.ttf",
    ("Nunito Sans", 400): "NunitoSans-400.ttf",
    ("Nunito Sans", 600): "NunitoSans-600.ttf",
    ("Nunito Sans", 700): "NunitoSans-700.ttf",
}

# --------------------------------------------------------------------------- tokens
BG_TOP, BG_MID, BG_BOTTOM = "#061a2e", "#04101c", "#071528"
GLOWS = (  # colour, alpha, centre (fx, fy), radius as fraction of farthest corner
    ((0, 190, 255), 0.38, (0.12, 0.18), 0.38),
    ((90, 110, 255), 0.34, (0.88, 0.08), 0.36),
    ((0, 255, 210), 0.20, (0.72, 0.92), 0.40),
    ((40, 140, 255), 0.22, (0.30, 0.85), 0.35),
)
TEXT_PRIMARY = "#ffffff"
TEXT_BODY = "#e8f6ff"
TEXT_MUTED = "#a9cde2"
TEXT_LABEL = "#cfeeff"
TEXT_SUB = "#b9dcf0"
PLACEHOLDER = "#8fb0c4"
ACCENT = "#38d6ff"
ACCENT_OK = "#45f0c8"
FIELD_SOLID = "#081f33"
FOCUS = "#6fdcff"           # rgba(110,220,255,.85) flattened on the dark glass
TABLE_HEADING = "#1a3550"
TABLE_HEADING_ACTIVE = "#21466a"
TABLE_ODD = "#0a2439"
TABLE_HOVER = "#103352"
SELECT_BG = "#0f6fb3"
SCROLL_THUMB = "#2a5675"

GLASS_BORDER = (160, 230, 255, 0.28)
GLASS_HIGHLIGHT = (255, 255, 255, 0.35)
PRIMARY_GLOSS = ((0.0, "#4ab2e6"), (0.49, "#0f6fb3"), (0.51, "#075794"), (1.0, "#0a68a8"))
PRIMARY_BORDER = (200, 240, 255, 0.65)
SECONDARY_GLOSS = ((0.0, 0.28), (0.50, 0.10), (0.51, 0.04), (1.0, 0.12))
SECONDARY_BORDER = (190, 240, 255, 0.45)

SS = 3  # supersampling factor for anti-aliased shapes


# --------------------------------------------------------------------------- platform
def enable_dpi_awareness() -> None:
    """Render at real pixel size on 125-150% displays instead of being bitmap-stretched."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def register_fonts() -> bool:
    """Privately register the bundled TTFs for this process (Windows). Returns True if all loaded."""
    if sys.platform != "win32":
        return False
    ok = True
    for name in FONT_FILES.values():
        path = asset("fonts/" + name)
        try:
            ok &= bool(path.exists() and ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0))
        except (AttributeError, OSError):
            ok = False
    return ok


def work_area(root) -> tuple[int, int, int, int]:
    """Usable screen area (x, y, w, h) excluding the taskbar; falls back to the full screen."""
    if sys.platform == "win32":
        rect = (ctypes.c_long * 4)()
        try:
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
                return rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
        except (AttributeError, OSError):
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def system_animations_enabled() -> bool:
    """Honour Windows 'Animation effects' (Settings > Accessibility > Visual effects)."""
    if sys.platform != "win32":
        return True
    value = ctypes.c_int(1)
    try:
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0)  # SPI_GETCLIENTAREAANIMATION
    except (AttributeError, OSError):
        return True
    return bool(value.value)


SETTINGS_PATH = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Track & Cover" / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_setting(key: str, value) -> None:
    data = load_settings()
    data[key] = value
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- fonts
class Fonts:
    """Tk fonts in pixel sizes (scaled), using bundled families with Segoe UI fallback."""

    def __init__(self, root, scale: float) -> None:
        import tkinter.font as tkfont
        self._tkfont, self._root, self.scale = tkfont, root, scale
        families = set(tkfont.families(root))
        self.has_exo = "Exo 2" in families
        self.has_nunito = "Nunito Sans" in families
        self.has_exo_semi = "Exo 2 SemiBold" in families
        self.has_nunito_semi = "Nunito Sans SemiBold" in families
        self._cache: dict = {}

    def _font(self, family: str, px: float, weight: str):
        key = (family, round(px), weight)
        if key not in self._cache:
            self._cache[key] = self._tkfont.Font(root=self._root, family=family,
                                                 size=-max(6, round(px * self.scale)), weight=weight)
        return self._cache[key]

    def heading(self, px: float, weight: int = 600):
        if weight >= 700:
            return self._font("Exo 2" if self.has_exo else "Segoe UI", px, "bold")
        if self.has_exo_semi:
            return self._font("Exo 2 SemiBold", px, "normal")
        return self._font("Segoe UI Semibold", px, "normal")

    def body(self, px: float, weight: int = 400):
        if weight >= 700:
            return self._font("Nunito Sans" if self.has_nunito else "Segoe UI", px, "bold")
        if weight >= 600:
            return self._font("Nunito Sans SemiBold" if self.has_nunito_semi else "Segoe UI Semibold", px, "normal")
        return self._font("Nunito Sans" if self.has_nunito else "Segoe UI", px, "normal")


@lru_cache(maxsize=32)
def pil_font(family: str, weight: int, px: int):
    path = asset("fonts/" + FONT_FILES.get((family, weight), ""))
    try:
        return ImageFont.truetype(str(path), px)
    except OSError:
        try:
            return ImageFont.truetype("segoeuib.ttf" if weight >= 600 else "segoeui.ttf", px)
        except OSError:
            return ImageFont.load_default()


# --------------------------------------------------------------------------- colour helpers
def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgba(color, alpha: float = 1.0) -> tuple[int, int, int, int]:
    if isinstance(color, str):
        color = hex_rgb(color)
    return (*color[:3], round(255 * alpha))


def mix(c1: str, c2: str, t: float) -> str:
    a, b = hex_rgb(c1), hex_rgb(c2)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _stop_color(stops, t):
    """stops: list of (pos, rgba tuple). Linear interpolation."""
    if t <= stops[0][0]:
        return stops[0][1]
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            return _lerp(c0, c1, 0 if p1 == p0 else (t - p0) / (p1 - p0))
    return stops[-1][1]


# --------------------------------------------------------------------------- primitives
def vgradient(w: int, h: int, stops) -> Image.Image:
    """Vertical RGBA gradient. stops: [(pos, (r,g,b,a)), ...]"""
    column = Image.new("RGBA", (1, max(1, h)))
    px = column.load()
    for y in range(h):
        px[0, y] = _stop_color(stops, y / max(1, h - 1))
    return column.resize((max(1, w), max(1, h)), Image.NEAREST)


def round_mask(w: int, h: int, r: float) -> Image.Image:
    """Anti-aliased rounded-rectangle mask."""
    big = Image.new("L", (max(1, w * SS), max(1, h * SS)), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), radius=max(0, r * SS), fill=255)
    return big.resize((max(1, w), max(1, h)), Image.LANCZOS)


def outline_layer(w: int, h: int, r: float, color, width: float = 1.0, inset: float = 0.0) -> Image.Image:
    big = Image.new("RGBA", (max(1, w * SS), max(1, h * SS)), (0, 0, 0, 0))
    i = inset * SS
    ImageDraw.Draw(big).rounded_rectangle((i, i, w * SS - 1 - i, h * SS - 1 - i), radius=max(0, (r - inset) * SS),
                                          outline=color, width=max(1, round(width * SS)))
    return big.resize((max(1, w), max(1, h)), Image.LANCZOS)


def multiply_alpha(img: Image.Image, factor: float) -> Image.Image:
    img = img.copy()
    alpha = img.getchannel("A").point(lambda a: round(a * factor))
    img.putalpha(alpha)
    return img


def brighten(img: Image.Image, factor: float) -> Image.Image:
    alpha = img.getchannel("A")
    out = ImageEnhance.Brightness(img.convert("RGB")).enhance(factor).convert("RGBA")
    out.putalpha(alpha)
    return out


def soft_shadow(mask: Image.Image, color, sigma: float, offset=(0, 0), margin: int = 0) -> Image.Image:
    """Blurred coloured shadow of ``mask`` (L), returned at mask size + 2*margin. Blur runs at 1/4 size."""
    w, h = mask.size
    canvas = Image.new("L", (w + 2 * margin, h + 2 * margin), 0)
    canvas.paste(mask, (margin + round(offset[0]), margin + round(offset[1])))
    k = 4 if sigma >= 6 else 1
    small = canvas.resize((max(1, canvas.width // k), max(1, canvas.height // k)), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(max(0.5, sigma / k)))
    blurred = small.resize(canvas.size, Image.BILINEAR)
    color = rgba(color[:3], color[3]) if len(color) == 4 and isinstance(color[3], float) else color
    layer = Image.new("RGBA", canvas.size, color[:3] + (0,))
    layer.putalpha(blurred.point(lambda a: round(a * color[3] / 255)))
    return layer


def _distance_image(size: int, cx: float, cy: float, radius: float) -> Image.Image:
    """L image where value ~= 180 * distance/radius (Pillow's radial_gradient scale)."""
    side = max(2, round(2 * radius * 1.0))
    grad = Image.radial_gradient("L").resize((side, side), Image.BILINEAR)
    # grad centre is at side/2; distance 'radius' maps to ~180.
    full = Image.new("L", (size, size), 255)
    full.paste(grad, (round(cx - side / 2), round(cy - side / 2)))
    return full


def radial_rgba(size: int, center=(0.5, 0.5), stops=None, radius: float | None = None,
                circle_clip: bool = True) -> Image.Image:
    """Radial gradient sprite. stops: [(pos 0..1 of radius, (r,g,b,a))]."""
    cx, cy = center[0] * size, center[1] * size
    if radius is None:  # CSS 'circle farthest-corner'
        radius = max(math.hypot(cx - x, cy - y) for x in (0, size) for y in (0, size))
    dist = _distance_image(size, cx, cy, radius)
    lut = [_stop_color(stops, min(1.0, v / 180.3)) for v in range(256)]
    channels = [dist.point([c[i] for c in lut]) for i in range(4)]
    img = Image.merge("RGBA", channels)
    if circle_clip:
        mask = Image.new("L", (size * SS, size * SS), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size * SS - 1, size * SS - 1), fill=255)
        mask = mask.resize((size, size), Image.LANCZOS)
        img.putalpha(Image.composite(img.getchannel("A"), Image.new("L", img.size, 0), mask))
    return img


# --------------------------------------------------------------------------- background
def render_background(w: int, h: int) -> Image.Image:
    stops = [(0.0, rgba(BG_TOP)), (0.55, rgba(BG_MID)), (1.0, rgba(BG_BOTTOM))]
    # 160deg CSS gradient ~ mostly vertical with a slight horizontal lean.
    big = vgradient(1, 64, stops).resize((64, 64), Image.NEAREST)
    big = big.rotate(-20, resample=Image.BICUBIC, expand=False, fillcolor=rgba(BG_MID))
    img = vgradient(1, max(1, h), stops).resize((max(1, w), max(1, h)), Image.NEAREST)
    img = Image.blend(img, big.resize(img.size, Image.BILINEAR), 0.35)
    far = math.hypot(w, h)
    for color, alpha, (fx, fy), rad in GLOWS:
        r = rad * far
        cx, cy = fx * w, fy * h
        side = max(2, round(2 * r))
        grad = Image.radial_gradient("L").resize((side, side), Image.BILINEAR)
        mask_full = Image.new("L", (w, h), 255)
        mask_full.paste(grad, (round(cx - side / 2), round(cy - side / 2)))
        a255 = alpha * 255
        mask = mask_full.point(lambda v: round(max(0.0, 1 - v / 180.3) * a255))
        layer = Image.new("RGBA", (w, h), color + (0,))
        layer.putalpha(mask)
        img.alpha_composite(layer)
    return img


# --------------------------------------------------------------------------- glass panels
def render_glass(bg: Image.Image, rect, radius: float, scale: float, gloss: bool = False,
                 shadow: bool = True, pill: bool = False) -> tuple[Image.Image, int]:
    """Frosted glass panel for ``rect`` (x, y, w, h) over ``bg``. Returns (image, margin)."""
    x, y, w, h = (round(v) for v in rect)
    w, h = max(4, w), max(4, h)
    r = h / 2 if pill else radius
    m = round(42 * scale) if shadow else 0
    crop = bg.crop((x, y, x + w, y + h)).convert("RGB")
    k = 3  # blur at 1/3 size for speed (visually identical on smooth gradients)
    small = crop.resize((max(1, w // k), max(1, h // k)), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(18 * scale / k))
    glass = ImageEnhance.Color(small.resize((w, h), Image.BILINEAR)).enhance(1.4).convert("RGBA")
    if gloss:
        ramp = [(0.0, (255, 255, 255, 46)), (0.48, (255, 255, 255, 15)),
                (0.52, (255, 255, 255, 5)), (1.0, (255, 255, 255, 13))]
    else:
        ramp = [(0.0, (255, 255, 255, 31)), (0.30, (255, 255, 255, 10)), (1.0, (255, 255, 255, 8))]
    glass.alpha_composite(vgradient(w, h, ramp))
    glass.alpha_composite(outline_layer(w, h, r, rgba(*_split(GLASS_BORDER)), 1 * scale))
    # 1px highlight just inside the top edge, fading out down the sides.
    hl = outline_layer(w, h, r, rgba(*_split(GLASS_HIGHLIGHT)), 1 * scale, inset=1 * scale)
    fade = vgradient(1, h, [(0.0, (0, 0, 0, 255)), (min(0.5, (r + 4) / h), (0, 0, 0, 0)), (1.0, (0, 0, 0, 0))])
    hl.putalpha(Image.composite(hl.getchannel("A"), Image.new("L", (w, h), 0),
                                fade.resize((w, h)).getchannel("A")))
    glass.alpha_composite(hl)
    mask = round_mask(w, h, r)
    glass.putalpha(mask)
    if not shadow:
        return glass, 0
    out = soft_shadow(mask, (0, 0, 0, 89), 18 * scale, (0, 14 * scale), m)
    out.alpha_composite(glass, (m, m))
    return out, m


def _split(token):
    return token[:3], token[3]


def render_inset(w: int, h: int, radius: float, scale: float, fill=(8, 31, 51, 255),
                 border=(160, 230, 255, 56), dashed: bool = False, inner_shadow: bool = True,
                 radial: bool = False) -> Image.Image:
    w, h = max(4, round(w)), max(4, round(h))
    img = Image.new("RGBA", (w, h), fill)
    if radial:  # cover box: soft cyan light at (50%, 40%)
        glow = radial_rgba(max(w, h), (0.5, 0.4), [(0.0, (80, 200, 255, 46)), (0.7, (0, 14, 30, 0)),
                                                    (1.0, (0, 14, 30, 0))], circle_clip=False)
        img.alpha_composite(glow.crop((0, 0, w, h)))
    if inner_shadow:
        img.alpha_composite(vgradient(w, round(10 * scale), [(0.0, (0, 0, 0, 115)), (1.0, (0, 0, 0, 0))]))
    if dashed:
        img.alpha_composite(_dashed_outline(w, h, radius, (160, 230, 255, 90), scale))
    else:
        img.alpha_composite(outline_layer(w, h, radius, border, 1 * scale))
    img.putalpha(Image.composite(img.getchannel("A"), Image.new("L", (w, h), 0), round_mask(w, h, radius)))
    return img


def _dashed_outline(w, h, r, color, scale):
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    pts = []
    R = r * SS
    W, H = w * SS - 1, h * SS - 1
    for cx, cy, start in ((W - R, R, -90), (W - R, H - R, 0), (R, H - R, 90), (R, R, 180)):
        for i in range(13):
            a = math.radians(start + 90 * i / 12)
            pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))
    pts.append(pts[0])
    dash, gap = 6 * scale * SS, 4 * scale * SS
    on, left = True, dash
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        pos = 0.0
        while pos < seg:
            step = min(left, seg - pos)
            if on:
                t0, t1 = pos / seg, (pos + step) / seg
                d.line((x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0, x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1),
                       fill=color, width=max(1, round(scale * SS)))
            pos += step
            left -= step
            if left <= 0:
                on, left = not on, (gap if on else dash)
    return big.resize((w, h), Image.LANCZOS)


def render_field(w: int, h: int, radius: float, scale: float) -> Image.Image:
    """Opaque inset entry field (solid fill so the real Entry blends in exactly)."""
    return render_inset(w, h, radius, scale, fill=rgba(FIELD_SOLID), border=rgba((160, 230, 255), 0.28),
                        inner_shadow=True)


# --------------------------------------------------------------------------- pills (buttons, toggles)
def _primary_body(w, h):
    return vgradient(w, h, [(p, rgba(c)) for p, c in PRIMARY_GLOSS])


def _secondary_body(w, h):
    return vgradient(w, h, [(p, (255, 255, 255, round(a * 255))) for p, a in SECONDARY_GLOSS])


def render_pill(w: int, h: int, kind: str, state: str, scale: float) -> tuple[Image.Image, int]:
    """Glossy pill button. kind: primary|secondary|badge. state: normal|hover|pressed|disabled."""
    w, h = max(8, round(w)), max(8, round(h))
    r = h / 2
    m = round(30 * scale)
    mask = round_mask(w, h, r)
    if kind == "primary":
        body = _primary_body(w, h)
        border, highlight = PRIMARY_BORDER, (255, 255, 255, 0.75)
        out = soft_shadow(mask, (0, 150, 230, 128), 12 * scale, (0, 8 * scale), m)
    elif kind == "badge":
        body = vgradient(w, h, [(0.0, (255, 255, 255, 51)), (1.0, (255, 255, 255, 10))])
        border, highlight = (160, 230, 255, 0.35), (255, 255, 255, 0.0)
        out = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    else:
        body = _secondary_body(w, h)
        border, highlight = SECONDARY_BORDER, (255, 255, 255, 0.6)
        out = soft_shadow(mask, (0, 0, 0, 77), 9 * scale, (0, 6 * scale), m) if kind == "secondary" \
            else Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    if state == "hover":
        body = brighten(body, 1.08) if kind == "primary" else multiply_alpha(body, 1.45)
    elif state == "pressed":
        body = brighten(body, 0.90) if kind == "primary" else multiply_alpha(body, 0.7)
    body.alpha_composite(outline_layer(w, h, r, rgba(*_split(border)), 1 * scale))
    if highlight[3]:
        hl = outline_layer(w, h, r, rgba(*_split(highlight)), 1 * scale, inset=1 * scale)
        fade = vgradient(w, h, [(0.0, (0, 0, 0, 255)), (0.35, (0, 0, 0, 0)), (1.0, (0, 0, 0, 0))])
        hl.putalpha(Image.composite(hl.getchannel("A"), Image.new("L", (w, h), 0), fade.getchannel("A")))
        body.alpha_composite(hl)
    body.putalpha(Image.composite(body.getchannel("A"), Image.new("L", (w, h), 0), mask))
    out.alpha_composite(body, (m, m))
    if state == "disabled":
        out = multiply_alpha(out, 0.45)
    return out, m


def render_toggle_track(w: int, h: int, on: bool, scale: float) -> tuple[Image.Image, int]:
    w, h = round(w), round(h)
    r = h / 2
    m = round(16 * scale)
    mask = round_mask(w, h, r)
    if on:
        out = soft_shadow(mask, (0, 170, 255, 128), 7 * scale, (0, 0), m)
        body = _primary_body(w, h)
        body.alpha_composite(outline_layer(w, h, r, (200, 240, 255, 153), 1 * scale))
        hl = outline_layer(w, h, r, (255, 255, 255, 153), 1 * scale, inset=1 * scale)
        fade = vgradient(w, h, [(0.0, (0, 0, 0, 255)), (0.4, (0, 0, 0, 0)), (1.0, (0, 0, 0, 0))])
        hl.putalpha(Image.composite(hl.getchannel("A"), Image.new("L", (w, h), 0), fade.getchannel("A")))
        body.alpha_composite(hl)
    else:
        out = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
        body = Image.new("RGBA", (w, h), (255, 255, 255, 26))
        body.alpha_composite(outline_layer(w, h, r, rgba(*_split(GLASS_BORDER)), 1 * scale))
    body.putalpha(Image.composite(body.getchannel("A"), Image.new("L", (w, h), 0), mask))
    out.alpha_composite(body, (m, m))
    return out, m


def render_knob(d: int, scale: float) -> tuple[Image.Image, int]:
    d = round(d)
    m = round(6 * scale)
    sphere = radial_rgba(d, (0.35, 0.30), [(0.0, rgba("#ffffff")), (0.5, rgba("#e3f5ff")), (1.0, rgba("#a9d4ee"))])
    out = soft_shadow(sphere.getchannel("A"), (0, 0, 0, 102), 3 * scale, (0, 2 * scale), m)
    out.alpha_composite(sphere, (m, m))
    return out, m


def render_sphere(d: int, inner: str, outer: str, glow, scale: float) -> tuple[Image.Image, int]:
    """Small glossy section marker sphere with a coloured glow."""
    d = round(d)
    m = round(8 * scale)
    sphere = radial_rgba(d, (0.35, 0.30), [(0.0, rgba("#ffffff")), (0.4, rgba(inner)), (1.0, rgba(outer))])
    out = soft_shadow(sphere.getchannel("A"), glow, 5 * scale, (0, 0), m)
    out.alpha_composite(sphere, (m, m))
    return out, m


def render_ring(d: int, scale: float) -> tuple[Image.Image, int]:
    """Header accent ring: 3px stroke, glowing, with a solid centre dot."""
    d = round(d)
    m = round(14 * scale)
    big = Image.new("RGBA", (d * SS, d * SS), (0, 0, 0, 0))
    dr = ImageDraw.Draw(big)
    sw = round(3 * scale * SS)
    dr.ellipse((sw / 2, sw / 2, d * SS - sw / 2, d * SS - sw / 2), outline=rgba(ACCENT), width=sw)
    dot = 12 * scale * SS
    c = d * SS / 2
    dr.ellipse((c - dot / 2, c - dot / 2, c + dot / 2, c + dot / 2), fill=rgba(ACCENT))
    ring = big.resize((d, d), Image.LANCZOS)
    out = soft_shadow(ring.getchannel("A"), (80, 220, 255, 153), 8 * scale, (0, 0), m)
    out.alpha_composite(ring, (m, m))
    return out, m


def render_dot(d: int, color: str, scale: float, glow: bool = True) -> tuple[Image.Image, int]:
    d = round(d)
    m = round(6 * scale) if glow else 0
    big = Image.new("RGBA", (d * SS, d * SS), (0, 0, 0, 0))
    ImageDraw.Draw(big).ellipse((0, 0, d * SS - 1, d * SS - 1), fill=rgba(color))
    dot = big.resize((d, d), Image.LANCZOS)
    if not glow:
        return dot, 0
    out = soft_shadow(dot.getchannel("A"), rgba(color, 0.9), 4 * scale, (0, 0), m)
    out.alpha_composite(dot, (m, m))
    return out, m


def render_disc(d: int, scale: float) -> tuple[Image.Image, int]:
    """Rainbow CD placeholder: conic gradient, dark hole with a pale ring, soft shadow."""
    d = round(d)
    m = round(20 * scale)
    colors = [hex_rgb(c) for c in ("#c9f2ff", "#8fb6ff", "#e2c8ff", "#9ff5e4", "#c9f2ff")]
    n = d * SS
    big = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    dr = ImageDraw.Draw(big)
    steps = 180
    for i in range(steps):
        t = i / steps
        k = min(3, int(t * 4))
        col = _lerp(colors[k], colors[k + 1], t * 4 - k)
        a0 = -90 + 30 + 360 * t  # conic 'from 30deg'
        dr.pieslice((0, 0, n - 1, n - 1), a0, a0 + 360 / steps + 0.6, fill=col + (255,))
    c = n / 2
    ring_r = n * 19 / 96  # proportions of the 96px reference disc: 26px hole + 6px pale ring
    dr.ellipse((c - ring_r, c - ring_r, c + ring_r, c + ring_r), fill=(255, 255, 255, 140))
    hole = n * 13 / 96
    dr.ellipse((c - hole, c - hole, c + hole, c + hole), fill=rgba("#0a1f35"))
    dr.ellipse((1, 1, n - 2, n - 2), outline=(255, 255, 255, 153), width=max(1, round(scale * SS)))
    disc = big.resize((d, d), Image.LANCZOS)
    out = soft_shadow(disc.getchannel("A"), (0, 0, 0, 102), 10 * scale, (0, 8 * scale), m)
    out.alpha_composite(disc, (m, m))
    return out, m


def _note_icon(size: int, color, stroke: float) -> Image.Image:
    """Feather-style music note (two heads)."""
    n = size * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = n / 24
    w = max(1, round(stroke * SS))
    d.line([(9 * s, 18 * s), (9 * s, 5 * s), (21 * s, 3 * s), (21 * s, 16 * s)], fill=color, width=w, joint="curve")
    for cx, cy in ((6, 18), (18, 16)):
        d.ellipse(((cx - 3) * s, (cy - 3) * s, (cx + 3) * s, (cy + 3) * s), outline=color, width=w)
    return img.resize((size, size), Image.LANCZOS)


def render_empty_bubble(d: int, scale: float) -> tuple[Image.Image, int]:
    d = round(d)
    m = round(24 * scale)
    sphere = radial_rgba(d, (0.35, 0.28), [(0.0, (255, 255, 255, 140)), (0.35, (120, 220, 255, 64)),
                                           (1.0, (10, 80, 140, 64))])
    sphere.alpha_composite(outline_layer(d, d, d / 2, (190, 240, 255, 115), 1 * scale))
    inner = vgradient(d, d, [(0.0, (0, 0, 0, 0)), (0.75, (0, 0, 0, 0)), (1.0, (0, 60, 120, 102))])
    inner.putalpha(Image.composite(inner.getchannel("A"), Image.new("L", (d, d), 0), sphere.getchannel("A")))
    sphere.alpha_composite(inner)
    icon = _note_icon(round(40 * scale), rgba("#e8f8ff"), 1.6 * scale * 40 / 24)
    sphere.alpha_composite(icon, ((d - icon.width) // 2, (d - icon.height) // 2))
    out = soft_shadow(sphere.getchannel("A"), (0, 160, 240, 89), 15 * scale, (0, 10 * scale), m)
    out.alpha_composite(sphere, (m, m))
    return out, m


def render_folder_icon(size: int, scale: float) -> Image.Image:
    n = size * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = n / 24
    w = max(1, round(1.8 * scale * SS * size / 20 / 1.2))
    pts = [(3, 7), (3, 17), (5, 19), (19, 19), (21, 17), (21, 9), (19, 7), (11, 7), (9, 5), (5, 5), (3, 7)]
    d.line([(x * s, y * s) for x, y in pts], fill=rgba("#7fdcff"), width=w, joint="curve")
    return img.resize((size, size), Image.LANCZOS)


def render_shield_icon(size: int, scale: float) -> Image.Image:
    n = size * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = n / 24
    pts = [(12, 3), (20, 6), (20, 12), (18, 17), (12, 21), (6, 17), (4, 12), (4, 6), (12, 3)]
    d.line([(x * s, y * s) for x, y in pts], fill=rgba(ACCENT_OK), width=max(1, round(2 * scale * SS * size / 16 / 1.5)),
           joint="curve")
    return img.resize((size, size), Image.LANCZOS)


def render_logo(w: int, h: int, scale: float) -> tuple[Image.Image, int]:
    """Transparent logo, no frame, with a soft cyan drop shadow."""
    m = round(22 * scale)
    try:
        src = Image.open(asset("trackcover_logo.png")).convert("RGBA")
    except OSError:
        return Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0)), m
    src.thumbnail((round(w), round(h)), Image.LANCZOS)
    logo = Image.new("RGBA", (round(w), round(h)), (0, 0, 0, 0))
    logo.alpha_composite(src, ((logo.width - src.width) // 2, (logo.height - src.height) // 2))
    out = soft_shadow(logo.getchannel("A"), (0, 170, 255, 102), 8 * scale, (0, 6 * scale), m)
    out.alpha_composite(logo, (m, m))
    return out, m


def render_text_glow(text: str, px: int, scale: float) -> tuple[Image.Image, int]:
    """Soft cyan glow behind the app title (the crisp text itself is a Tk text item)."""
    font = pil_font("Exo 2", 700, round(px))
    m = round(20 * scale)
    bbox = font.getbbox(text)
    w, h = bbox[2] + 2 * m, bbox[3] + 2 * m
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((m, m), text, font=font, fill=255)
    small = mask.resize((max(1, w // 3), max(1, h // 3)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3 * scale))
    glow = Image.new("RGBA", (w, h), (80, 210, 255, 0))
    glow.putalpha(small.resize((w, h), Image.BILINEAR).point(lambda a: round(min(255, a * 1.6) * 0.55)))
    return glow, m


# --------------------------------------------------------------------------- animated sprites
def render_bubble_sprite(size: int, tint=(140, 225, 255), deep=(20, 120, 200), hi_alpha=0.75,
                         tint_alpha=0.28, deep_alpha=0.10, rim=True) -> Image.Image:
    size = max(4, round(size))
    img = radial_rgba(size, (0.32, 0.28), [
        (0.0, (255, 255, 255, round(255 * hi_alpha))),
        (0.28, tint + (round(255 * tint_alpha),)),
        (0.70, deep + (round(255 * deep_alpha),)),
        (1.0, deep + (0,)),
    ])
    if rim:
        img.alpha_composite(outline_layer(size, size, size / 2, (190, 240, 255, 64), 1))
    return img


def render_glow_sprite(size: int, color, alpha: float, blur: float) -> tuple[Image.Image, int]:
    size = max(4, round(size))
    m = round(blur * 2)
    img = Image.new("RGBA", (size + 2 * m, size + 2 * m), (0, 0, 0, 0))
    core = radial_rgba(size, (0.5, 0.5), [(0.0, color + (round(255 * alpha),)), (0.7, color + (0,)),
                                          (1.0, color + (0,))], radius=size / 2)
    img.alpha_composite(core, (m, m))
    small = img.resize((max(1, img.width // 2), max(1, img.height // 2)), Image.BILINEAR)
    return small.filter(ImageFilter.GaussianBlur(blur / 2)).resize(img.size, Image.BILINEAR), m
