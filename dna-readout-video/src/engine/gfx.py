"""cairo + Pango drawing surface, driven through ctypes.

No pygobject, no pycairo: this environment has neither wired up in a way that
lets Pango see a real cairo_t, so both libraries are called through their C ABI.
Cairo's ARGB32 surface is BGRA in memory on little-endian, which is exactly the
pixel format handed to ffmpeg.
"""
import ctypes as C
from ctypes import (c_int, c_uint, c_double, c_char_p, c_void_p, c_ubyte,
                    POINTER, byref, Structure)

# ---------------------------------------------------------------- libraries
_cairo = C.CDLL("libcairo.so.2")
_pango = C.CDLL("libpango-1.0.so.0")
_pangocairo = C.CDLL("libpangocairo-1.0.so.0")
_gobj = C.CDLL("libgobject-2.0.so.0")

_vp, _i, _d, _cp = c_void_p, c_int, c_double, c_char_p


def _fn(lib, name, restype, argtypes):
    f = getattr(lib, name)
    f.restype = restype
    f.argtypes = argtypes
    return f


# --- cairo -----------------------------------------------------------------
cairo_image_surface_create = _fn(_cairo, "cairo_image_surface_create", _vp, [_i, _i, _i])
cairo_surface_destroy = _fn(_cairo, "cairo_surface_destroy", None, [_vp])
cairo_image_surface_get_data = _fn(_cairo, "cairo_image_surface_get_data", c_void_p, [_vp])
cairo_image_surface_get_stride = _fn(_cairo, "cairo_image_surface_get_stride", _i, [_vp])
cairo_surface_flush = _fn(_cairo, "cairo_surface_flush", None, [_vp])
cairo_surface_mark_dirty = _fn(_cairo, "cairo_surface_mark_dirty", None, [_vp])
cairo_surface_write_to_png = _fn(_cairo, "cairo_surface_write_to_png", _i, [_vp, _cp])

cairo_create = _fn(_cairo, "cairo_create", _vp, [_vp])
cairo_destroy = _fn(_cairo, "cairo_destroy", None, [_vp])
cairo_save = _fn(_cairo, "cairo_save", None, [_vp])
cairo_restore = _fn(_cairo, "cairo_restore", None, [_vp])
cairo_new_path = _fn(_cairo, "cairo_new_path", None, [_vp])
cairo_close_path = _fn(_cairo, "cairo_close_path", None, [_vp])
cairo_move_to = _fn(_cairo, "cairo_move_to", None, [_vp, _d, _d])
cairo_line_to = _fn(_cairo, "cairo_line_to", None, [_vp, _d, _d])
cairo_curve_to = _fn(_cairo, "cairo_curve_to", None, [_vp, _d, _d, _d, _d, _d, _d])
cairo_rectangle = _fn(_cairo, "cairo_rectangle", None, [_vp, _d, _d, _d, _d])
cairo_arc = _fn(_cairo, "cairo_arc", None, [_vp, _d, _d, _d, _d, _d])
cairo_arc_negative = _fn(_cairo, "cairo_arc_negative", None, [_vp, _d, _d, _d, _d, _d])
cairo_fill = _fn(_cairo, "cairo_fill", None, [_vp])
cairo_fill_preserve = _fn(_cairo, "cairo_fill_preserve", None, [_vp])
cairo_stroke = _fn(_cairo, "cairo_stroke", None, [_vp])
cairo_stroke_preserve = _fn(_cairo, "cairo_stroke_preserve", None, [_vp])
cairo_paint = _fn(_cairo, "cairo_paint", None, [_vp])
cairo_paint_with_alpha = _fn(_cairo, "cairo_paint_with_alpha", None, [_vp, _d])
cairo_clip = _fn(_cairo, "cairo_clip", None, [_vp])
cairo_clip_preserve = _fn(_cairo, "cairo_clip_preserve", None, [_vp])
cairo_reset_clip = _fn(_cairo, "cairo_reset_clip", None, [_vp])
cairo_set_source_rgba = _fn(_cairo, "cairo_set_source_rgba", None,
                            [_vp, _d, _d, _d, _d])
cairo_set_source_rgb = _fn(_cairo, "cairo_set_source_rgb", None, [_vp, _d, _d, _d])
cairo_set_source = _fn(_cairo, "cairo_set_source", None, [_vp, _vp])
cairo_set_line_width = _fn(_cairo, "cairo_set_line_width", None, [_vp, _d])
cairo_set_line_cap = _fn(_cairo, "cairo_set_line_cap", None, [_vp, _i])
cairo_set_line_join = _fn(_cairo, "cairo_set_line_join", None, [_vp, _i])
cairo_set_dash = _fn(_cairo, "cairo_set_dash", None,
                     [_vp, POINTER(c_double), _i, _d])
cairo_set_operator = _fn(_cairo, "cairo_set_operator", None, [_vp, _i])
cairo_translate = _fn(_cairo, "cairo_translate", None, [_vp, _d, _d])
cairo_scale = _fn(_cairo, "cairo_scale", None, [_vp, _d, _d])
cairo_rotate = _fn(_cairo, "cairo_rotate", None, [_vp, _d])
cairo_push_group = _fn(_cairo, "cairo_push_group", None, [_vp])
cairo_pop_group_to_source = _fn(_cairo, "cairo_pop_group_to_source", None, [_vp])

cairo_pattern_create_linear = _fn(_cairo, "cairo_pattern_create_linear", _vp,
                                  [_d, _d, _d, _d])
cairo_pattern_create_for_surface = _fn(_cairo, "cairo_pattern_create_for_surface",
                                       _vp, [_vp])
cairo_pattern_set_extend = _fn(_cairo, "cairo_pattern_set_extend", None, [_vp, _i])
cairo_image_surface_create_from_png = _fn(_cairo, "cairo_image_surface_create_from_png",
                                          _vp, [_cp])
cairo_pattern_create_radial = _fn(_cairo, "cairo_pattern_create_radial", _vp,
                                  [_d, _d, _d, _d, _d, _d])
cairo_pattern_add_color_stop_rgba = _fn(_cairo, "cairo_pattern_add_color_stop_rgba",
                                        None, [_vp, _d, _d, _d, _d, _d])
cairo_pattern_destroy = _fn(_cairo, "cairo_pattern_destroy", None, [_vp])

# --- pango -----------------------------------------------------------------
class PangoRect(Structure):
    _fields_ = [("x", c_int), ("y", c_int), ("width", c_int), ("height", c_int)]


pango_font_description_new = _fn(_pango, "pango_font_description_new", _vp, [])
pango_font_description_set_family = _fn(_pango, "pango_font_description_set_family",
                                        None, [_vp, _cp])
pango_font_description_set_absolute_size = _fn(
    _pango, "pango_font_description_set_absolute_size", None, [_vp, _d])
pango_font_description_set_weight = _fn(_pango, "pango_font_description_set_weight",
                                        None, [_vp, _i])
pango_font_description_free = _fn(_pango, "pango_font_description_free", None, [_vp])

pango_layout_set_font_description = _fn(_pango,
                                        "pango_layout_set_font_description",
                                        None, [_vp, _vp])
pango_layout_set_text = _fn(_pango, "pango_layout_set_text", None, [_vp, _cp, _i])
pango_layout_set_markup = _fn(_pango, "pango_layout_set_markup", None, [_vp, _cp, _i])
pango_layout_set_width = _fn(_pango, "pango_layout_set_width", None, [_vp, _i])
pango_layout_set_wrap = _fn(_pango, "pango_layout_set_wrap", None, [_vp, _i])
pango_layout_set_alignment = _fn(_pango, "pango_layout_set_alignment", None, [_vp, _i])
pango_layout_set_spacing = _fn(_pango, "pango_layout_set_spacing", None, [_vp, _i])
pango_layout_get_pixel_extents = _fn(_pango, "pango_layout_get_pixel_extents",
                                     None, [_vp, POINTER(PangoRect), POINTER(PangoRect)])

pango_cairo_create_layout = _fn(_pangocairo, "pango_cairo_create_layout", _vp, [_vp])
pango_cairo_show_layout = _fn(_pangocairo, "pango_cairo_show_layout", None, [_vp, _vp])
pango_cairo_update_layout = _fn(_pangocairo, "pango_cairo_update_layout", None,
                                [_vp, _vp])
g_object_unref = _fn(_gobj, "g_object_unref", None, [_vp])

PANGO_SCALE = 1024
WRAP_WORD_CHAR = 2
ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT = 0, 1, 2
WEIGHT_NORMAL, WEIGHT_MEDIUM, WEIGHT_BOLD = 400, 500, 700

OP_OVER, OP_ADD, OP_SCREEN, OP_MULTIPLY = 2, 12, 15, 14


# ---------------------------------------------------------------- helpers
def hex_rgb(s):
    """'#1A2B3C' -> (r, g, b) floats in 0..1."""
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgba(s, a=1.0):
    r, g, b = hex_rgb(s)
    return (r, g, b, a)


def mix(c1, c2, t):
    """Blend two ('#rrggbb', alpha) colours."""
    a = hex_rgb(c1)
    b = hex_rgb(c2)
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else (hi if x > hi else x)


def ramp(t, t0, t1):
    """0 before t0, 1 after t1, smooth in between."""
    if t1 <= t0:
        return 1.0 if t >= t1 else 0.0
    x = clamp((t - t0) / (t1 - t0))
    return x * x * (3 - 2 * x)


def ramp_lin(t, t0, t1):
    if t1 <= t0:
        return 1.0 if t >= t1 else 0.0
    return clamp((t - t0) / (t1 - t0))


def ease_out(t):
    return 1 - (1 - clamp(t)) ** 3


def ease_in_out(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def pulse(t, t0, dur=0.45):
    """A quick 0->1->0 bump starting at t0 (used for highlight flashes)."""
    if t < t0 or t > t0 + dur:
        return 0.0
    x = (t - t0) / dur
    return (1 - abs(2 * x - 1)) ** 0.7


# ---------------------------------------------------------------- Frame
def _esc(s):
    """Pango markup is on (it gives us CJK shaping we want), so literal
    & < > in copy must be escaped or the run silently disappears."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Frame:
    """A render surface plus the cairo_t that draws on it."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self._surf = cairo_image_surface_create(0, w, h)  # ARGB32
        if not self._surf:
            raise RuntimeError("cairo_image_surface_create failed")
        self._cr = cairo_create(self._surf)
        if not self._cr:
            raise RuntimeError("cairo_create failed")
        self.stride = cairo_image_surface_get_stride(self._surf)

    def close(self):
        if self._cr:
            cairo_destroy(self._cr)
            self._cr = None
        if self._surf:
            cairo_surface_destroy(self._surf)
            self._surf = None

    # ---- colour / paint
    def color(self, c, a=None):
        if isinstance(c, str):
            r, g, b = hex_rgb(c)
            alpha = 1.0 if a is None else a
        else:
            r, g, b = c[0], c[1], c[2]
            alpha = (c[3] if len(c) > 3 else 1.0) if a is None else a
        cairo_set_source_rgba(self._cr, r, g, b, alpha)

    def clear(self, c="#0B1116"):
        self.color(c)
        cairo_paint(self._cr)

    def fill(self, c):
        self.color(c)
        cairo_paint(self._cr)

    def paint_alpha(self, a):
        cairo_paint_with_alpha(self._cr, a)

    # ---- state
    def save(self):
        cairo_save(self._cr)

    def restore(self):
        cairo_restore(self._cr)

    def translate(self, x, y):
        cairo_translate(self._cr, x, y)

    def scale(self, sx, sy=None):
        cairo_scale(self._cr, sx, sx if sy is None else sy)

    def rotate(self, r):
        cairo_rotate(self._cr, r)

    def push_group(self):
        cairo_push_group(self._cr)

    def pop_group(self, alpha=1.0):
        cairo_pop_group_to_source(self._cr)
        cairo_paint_with_alpha(self._cr, alpha)

    def operator(self, op):
        cairo_set_operator(self._cr, op)

    def clip_rect(self, x, y, w, h):
        cairo_rectangle(self._cr, x, y, w, h)
        cairo_clip(self._cr)

    def reset_clip(self):
        cairo_reset_clip(self._cr)

    # ---- primitives
    def rect(self, x, y, w, h, c=None, alpha=None, r=0.0):
        if w <= 0 or h <= 0:
            return
        cairo_new_path(self._cr)
        if r <= 0:
            cairo_rectangle(self._cr, x, y, w, h)
        else:
            r = min(r, w / 2, h / 2)
            cairo_arc(self._cr, x + w - r, y + r, r, -1.5707963, 0)
            cairo_arc(self._cr, x + w - r, y + h - r, r, 0, 1.5707963)
            cairo_arc(self._cr, x + r, y + h - r, r, 1.5707963, 3.1415927)
            cairo_arc(self._cr, x + r, y + r, r, 3.1415927, 4.712389)
            cairo_close_path(self._cr)
        if c is not None:
            self.color(c, alpha)
        cairo_fill(self._cr)

    def rect_stroke(self, x, y, w, h, c, lw=2.0, r=0.0, alpha=None, dash=None):
        if w <= 0 or h <= 0:
            return
        cairo_new_path(self._cr)
        if r <= 0:
            cairo_rectangle(self._cr, x, y, w, h)
        else:
            r = min(r, w / 2, h / 2)
            cairo_arc(self._cr, x + w - r, y + r, r, -1.5707963, 0)
            cairo_arc(self._cr, x + w - r, y + h - r, r, 0, 1.5707963)
            cairo_arc(self._cr, x + r, y + h - r, r, 1.5707963, 3.1415927)
            cairo_arc(self._cr, x + r, y + r, r, 3.1415927, 4.712389)
            cairo_close_path(self._cr)
        self.color(c, alpha)
        cairo_set_line_width(self._cr, lw)
        self.dash(dash)
        cairo_stroke(self._cr)
        self.dash(None)

    def circle(self, x, y, rad, c=None, alpha=None, stroke=None, lw=2.0):
        cairo_new_path(self._cr)
        cairo_arc(self._cr, x, y, rad, 0, 6.2831853)
        if c is not None:
            self.color(c, alpha)
            cairo_fill_preserve(self._cr)
        if stroke is not None:
            self.color(stroke)
            cairo_set_line_width(self._cr, lw)
            cairo_stroke(self._cr)
        else:
            cairo_new_path(self._cr)

    def line(self, x0, y0, x1, y1, c, lw=2.0, alpha=None, dash=None):
        cairo_new_path(self._cr)
        cairo_move_to(self._cr, x0, y0)
        cairo_line_to(self._cr, x1, y1)
        self.color(c, alpha)
        cairo_set_line_width(self._cr, lw)
        self.dash(dash)
        cairo_stroke(self._cr)
        self.dash(None)

    def polyline(self, pts, c, lw=2.0, alpha=None, dash=None, close=False):
        if len(pts) < 2:
            return
        cairo_new_path(self._cr)
        cairo_move_to(self._cr, pts[0][0], pts[0][1])
        for p in pts[1:]:
            cairo_line_to(self._cr, p[0], p[1])
        if close:
            cairo_close_path(self._cr)
        self.color(c, alpha)
        cairo_set_line_width(self._cr, lw)
        self.dash(dash)
        cairo_stroke(self._cr)
        self.dash(None)

    def fill_poly(self, pts, c, alpha=None):
        if len(pts) < 3:
            return
        cairo_new_path(self._cr)
        cairo_move_to(self._cr, pts[0][0], pts[0][1])
        for p in pts[1:]:
            cairo_line_to(self._cr, p[0], p[1])
        cairo_close_path(self._cr)
        self.color(c, alpha)
        cairo_fill(self._cr)

    def arc_stroke(self, x, y, rad, a0, a1, c, lw=2.0, alpha=None):
        cairo_new_path(self._cr)
        cairo_arc(self._cr, x, y, rad, a0, a1)
        self.color(c, alpha)
        cairo_set_line_width(self._cr, lw)
        cairo_stroke(self._cr)

    def dash(self, dashes):
        if not dashes:
            cairo_set_dash(self._cr, None, 0, 0.0)
        else:
            n = len(dashes)
            arr = (c_double * n)(*dashes)
            cairo_set_dash(self._cr, arr, n, 0.0)

    def line_cap(self, cap):
        cairo_set_line_cap(self._cr, cap)  # 0 butt 1 round 2 square

    def line_join(self, j):
        cairo_set_line_join(self._cr, j)  # 0 miter 1 round 2 bevel

    # ---- gradients
    def grad_v(self, x, y, h, stops):
        """Vertical linear gradient. stops = [(offset, '#rrggbb', alpha), ...]"""
        pat = cairo_pattern_create_linear(x, y, x, y + h)
        for off, col, a in stops:
            r, g, b = hex_rgb(col)
            cairo_pattern_add_color_stop_rgba(pat, off, r, g, b, a)
        cairo_set_source(self._cr, pat)
        cairo_pattern_destroy(pat)
        return True

    def grad_h(self, x, y, w, stops):
        pat = cairo_pattern_create_linear(x, y, x + w, y)
        for off, col, a in stops:
            r, g, b = hex_rgb(col)
            cairo_pattern_add_color_stop_rgba(pat, off, r, g, b, a)
        cairo_set_source(self._cr, pat)
        cairo_pattern_destroy(pat)
        return True

    def grain(self, path, alpha=0.5):
        """Tile a film-grain PNG over the whole surface (multiply-ish overlay).

        Keeps large flat dark areas from banding in H.264 and adds the fine
        texture that reads as 'graded' rather than 'flat fill'.
        """
        import os
        if not os.path.exists(path):
            return
        surf = cairo_image_surface_create_from_png(str(path).encode())
        if not surf:
            return
        pat = cairo_pattern_create_for_surface(surf)
        cairo_pattern_set_extend(pat, 1)          # CAIRO_EXTEND_REPEAT
        cairo_set_source(self._cr, pat)
        cairo_paint_with_alpha(self._cr, alpha)
        cairo_pattern_destroy(pat)
        cairo_surface_destroy(surf)

    def glow(self, cx, cy, rx, ry, col, alpha=0.18, inner=0.0, soft=0.55):
        """Soft elliptical glow. Real cairo radial gradient, scaled to an
        ellipse — the cheap way to give a flat dark frame depth."""
        rx, ry = max(float(rx), 1.0), max(float(ry), 1.0)
        self.save()
        self.translate(cx, cy)
        self.scale(rx, ry)
        pat = cairo_pattern_create_radial(0.0, 0.0, max(float(inner), 0.0),
                                          0.0, 0.0, 1.0)
        r, g, b = hex_rgb(col)
        cairo_pattern_add_color_stop_rgba(pat, 0.0, r, g, b, alpha)
        cairo_pattern_add_color_stop_rgba(pat, soft, r, g, b, alpha * 0.30)
        cairo_pattern_add_color_stop_rgba(pat, 1.0, r, g, b, 0.0)
        cairo_set_source(self._cr, pat)
        cairo_pattern_destroy(pat)
        cairo_rectangle(self._cr, -1.0, -1.0, 2.0, 2.0)
        cairo_fill(self._cr)
        self.restore()

    # ---- text
    def text(self, s, x, y, size=32, c="#E8EEF2", family="Noto Sans CJK SC",
             weight=WEIGHT_NORMAL, align="left", alpha=1.0, width=None,
             spacing=1.0, anchor_mid=False):
        """Draw text. y is the top of the layout box (or vertical centre when
        anchor_mid). align: 'left' | 'center' | 'right' relative to x."""
        if not s:
            return (0, 0)
        lay = pango_cairo_create_layout(self._cr)
        fd = pango_font_description_new()
        pango_font_description_set_family(fd, family.encode())
        pango_font_description_set_absolute_size(fd, size * PANGO_SCALE)
        pango_font_description_set_weight(fd, weight)
        pango_layout_set_font_description(lay, fd)
        pango_font_description_free(fd)
        pango_layout_set_markup(lay, _esc(s).encode("utf-8"), -1)
        if width is not None:
            pango_layout_set_width(lay, int(width * PANGO_SCALE))
            pango_layout_set_wrap(lay, WRAP_WORD_CHAR)
        if spacing != 1.0:
            pango_layout_set_spacing(lay, int((spacing - 1.0) * size * PANGO_SCALE))
        ink, log = PangoRect(), PangoRect()
        pango_layout_get_pixel_extents(lay, byref(ink), byref(log))
        bw = width if width is not None else log.width
        dx = x - ink.x
        if align == "center":
            dx = x - ink.x - ink.width / 2.0
        elif align == "right":
            dx = x - ink.x - ink.width
        dy = y
        if anchor_mid:
            dy = y - log.height / 2.0
        cairo_move_to(self._cr, dx, dy)
        self.color(c, alpha)
        pango_cairo_show_layout(self._cr, lay)
        g_object_unref(lay)
        return (ink.width, ink.height)

    def measure(self, s, size=32, family="Noto Sans CJK SC", weight=WEIGHT_NORMAL,
                width=None):
        lay = pango_cairo_create_layout(self._cr)
        fd = pango_font_description_new()
        pango_font_description_set_family(fd, family.encode())
        pango_font_description_set_absolute_size(fd, size * PANGO_SCALE)
        pango_font_description_set_weight(fd, weight)
        pango_layout_set_font_description(lay, fd)
        pango_font_description_free(fd)
        pango_layout_set_markup(lay, _esc(s).encode("utf-8"), -1)
        if width is not None:
            pango_layout_set_width(lay, int(width * PANGO_SCALE))
            pango_layout_set_wrap(lay, WRAP_WORD_CHAR)
        ink, log = PangoRect(), PangoRect()
        pango_layout_get_pixel_extents(lay, byref(ink), byref(log))
        g_object_unref(lay)
        return (ink.width, ink.height, log.width, log.height)

    # ---- output
    def rgb_bytes(self):
        cairo_surface_flush(self._surf)
        n = self.stride * self.h
        return C.string_at(cairo_image_surface_get_data(self._surf), n)

    def write_png(self, path):
        cairo_surface_flush(self._surf)
        if cairo_surface_write_to_png(self._surf, str(path).encode()) != 0:
            raise RuntimeError("cairo_surface_write_to_png failed: %s" % path)
