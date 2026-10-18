"""Accent-colored icon set for HiCloud MP.

Feather icon geometry (https://feathericons.com, MIT) rendered through
QSvgRenderer and tinted to any color — no external asset files, no stock
QStyle icons. Colors follow the theme: transport glyphs on the accent-filled
play button render white; toggle glyphs use the accent; utility glyphs use
theme text. Calculated to be crisp by rendering at 2x device pixel ratio.
"""
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Feather geometry: (kind, inner-markup) where kind is 'stroke' or 'fill'.
_GLYPHS = {
    "play": ("fill", '<polygon points="5 3 19 12 5 21 5 3"/>'),
    "pause": ("fill", '<rect x="6" y="4" width="4" height="16" rx="1"/>'
                      '<rect x="14" y="4" width="4" height="16" rx="1"/>'),
    "stop": ("fill", '<rect x="6" y="6" width="12" height="12" rx="2"/>'),
    "skip-back": ("fill", '<polygon points="19 20 9 12 19 4 19 20"/>'
                          '<line x1="5" y1="19" x2="5" y2="5"/>'),
    "skip-forward": ("fill", '<polygon points="5 4 15 12 5 20 5 4"/>'
                             '<line x1="19" y1="5" x2="19" y2="19"/>'),
    "shuffle": ("stroke",
                '<polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/>'
                '<polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/>'
                '<line x1="4" y1="4" x2="9" y2="9"/>'),
    "repeat": ("stroke",
               '<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/>'
               '<polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>'),
    "volume": ("stroke",
               '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>'
               '<path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>'),
    "folder": ("stroke",
               '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'),
    "music": ("stroke",
              '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/>'
              '<circle cx="18" cy="16" r="3"/>'),
    "plus": ("stroke",
             '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>'),
    "save": ("stroke",
             '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>'
             '<polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>'),
    "trash": ("stroke",
              '<polyline points="3 6 5 6 21 6"/>'
              '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'),
    "refresh": ("stroke",
                '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>'
                '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>'),
    "globe": ("stroke",
              '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>'
              '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>'),
    "sliders": ("stroke",
                '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>'
                '<line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>'
                '<line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>'
                '<line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/>'
                '<line x1="17" y1="16" x2="23" y2="16"/>'),
    "info": ("stroke",
             '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/>'
             '<line x1="12" y1="8" x2="12.01" y2="8"/>'),
    "cloud": ("stroke", '<path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>'),
}

_STROKE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">{inner}</svg>'
)
_FILL_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="{color}" stroke="{color}" stroke-width="1.5" '
    'stroke-linecap="round" stroke-linejoin="round">{inner}</svg>'
)

_RENDER_SCALE = 2  # device pixels per logical pixel for crisp hidpi glyphs
_cache = {}
_tray_cache = {}


def _svg_markup(name, color):
    entry = _GLYPHS.get(name)
    if entry is None:
        return None
    kind, inner = entry
    if kind == "fill":
        return _FILL_SVG.format(color=color, inner=inner)
    return _STROKE_SVG.format(color=color, inner=inner)


def pixmap(name, size=20, color="#e6e9ef"):
    """Render `name` as a transparent QPixmap tinted to `color`, or a null
    pixmap for unknown glyph names (honest fallback, no crash)."""
    key = (name, str(color), int(size))
    hit = _cache.get(key)
    if hit is not None:
        return hit

    markup = _svg_markup(name, color)
    if markup is None:
        return QPixmap()

    renderer = QSvgRenderer(QByteArray(markup.encode("utf-8")))
    if not renderer.isValid():
        return QPixmap()

    device_px = int(size) * _RENDER_SCALE
    img = QImage(device_px, device_px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # Small inset so 2px strokes never clip against the bitmap edge.
    renderer.render(painter, QRectF(0.5, 0.5, device_px - 1, device_px - 1))
    painter.end()

    out = QPixmap.fromImage(img)
    out.setDevicePixelRatio(_RENDER_SCALE)
    _cache[key] = out
    return out


def icon(name, size=20, color="#e6e9ef"):
    pix = pixmap(name, size=size, color=color)
    return QIcon(pix)


def _contrast_glyph_color(fill_hex):
    """'#ffffff' or '#111111' - whichever contrasts with the fill color."""
    c = QColor(fill_hex)
    if not c.isValid():
        c = QColor("#10b981")
    luminance = 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
    return "#111111" if luminance > 0.6 else "#ffffff"


def _badge_pixmap(name, accent_color, size):
    """Accent-filled round badge with a contrast-safe glyph, rendered at
    _RENDER_SCALE device pixels. Null pixmap for unknown glyph names."""
    markup_color = _contrast_glyph_color(accent_color)
    markup = _svg_markup(name, markup_color)
    if markup is None:
        return QPixmap()
    renderer = QSvgRenderer(QByteArray(markup.encode("utf-8")))
    if not renderer.isValid():
        return QPixmap()

    device_px = max(int(size), 1) * _RENDER_SCALE
    img = QImage(device_px, device_px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    accent = QColor(accent_color)
    if not accent.isValid():
        accent = QColor("#10b981")
    # Hairline rim keeps the badge defined on light AND dark taskbars.
    rim = QColor(0, 0, 0, 46) if markup_color == "#111111" \
        else QColor(255, 255, 255, 60)
    stroke = max(1.0, device_px * 0.045)
    margin = stroke / 2.0
    painter.setBrush(accent)
    painter.setPen(QPen(rim, stroke))
    painter.drawEllipse(QRectF(margin, margin,
                               device_px - 2 * margin, device_px - 2 * margin))

    # Glyph centred at ~52% of the badge.
    side = device_px * 0.52
    renderer.render(painter, QRectF((device_px - side) / 2.0,
                                    (device_px - side) / 2.0, side, side))
    painter.end()

    out = QPixmap.fromImage(img)
    out.setDevicePixelRatio(_RENDER_SCALE)
    return out


def tray_icon(name, accent_color, sizes=(16, 24, 32, 48)):
    """QSystemTrayIcon-ready icon: accent-filled round badge with a
    contrast-safe play/pause/stop glyph (white on dark fills, near-black on
    light fills). Null QIcon for unknown glyph names (honest fallback)."""
    if name not in _GLYPHS:
        return QIcon()
    key = (name, str(accent_color), tuple(int(s) for s in sizes))
    hit = _tray_cache.get(key)
    if hit is not None:
        return hit
    accent = accent_color if QColor(accent_color).isValid() else "#10b981"
    out = QIcon()
    for size in sizes:
        out.addPixmap(_badge_pixmap(name, accent, size))
    _tray_cache[key] = out
    return out


def invalidate():
    """Drop the cache — call whenever the theme/accent colors change."""
    _cache.clear()
    _tray_cache.clear()


class IconFactory:
    """Per-app icon provider bound to the live theme colors.

    roles: 'text'    — theme text color (default)
           'dim'     — dimmed text
           'accent'  — active accent color
           'onaccent'— white glyph that sits on an accent-filled surface
    """

    def __init__(self, accent_color="#10b981", text_color="#e6e9ef",
                 dim_color="#9aa3b2"):
        self._colors = {
            "text": text_color,
            "dim": dim_color,
            "accent": accent_color,
            "onaccent": "#ffffff",
        }
        self._size = 20

    # ------------------------------------------------------------ colors
    @property
    def accent_color(self):
        return self._colors["accent"]

    @property
    def dim_color(self):
        return self._colors["dim"]

    def set_colors(self, accent_color, text_color, dim_color=None):
        self._colors["accent"] = accent_color
        self._colors["text"] = text_color
        if dim_color:
            self._colors["dim"] = dim_color
        invalidate()

    # ------------------------------------------------------------ access
    def pixmap(self, name, size=None, role="text"):
        color = self._colors.get(role, self._colors["text"])
        return pixmap(name, size=size or self._size, color=color)

    def icon(self, name, size=None, role="text"):
        pix = self.pixmap(name, size=size, role=role)
        return QIcon(pix)
