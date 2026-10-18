"""Central theming for HiCloud MP.

One module owns every visual decision so the QSS scattered across main.py /
player.py can't drift apart again. Everything is tokenized and interpolated:

- theme:   "Dark" | "Light"
- accent:  hex color used for progress, sliders, selection and active toggles
- density: "comfortable" | "compact"

apply_theme() resolves values from QSettings and applies them to any widget
(the whole app or a single dialog). The QApplication palette for native
widgets QSS cannot reach lives in apply_app_palette().
"""

from datetime import datetime
import hashlib
import os

from platformdirs import user_cache_dir
from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import Qt

# Accent presets shown in Settings; values are the single source of truth.
ACCENTS = {
    "Emerald": "#10b981",
    "Blue": "#3b82f6",
    "Violet": "#8b5cf6",
    "Amber": "#f59e0b",
    "Rose": "#f43f5e",
    "Sky": "#38bdf8",
    "Cyan": "#06b6d4",
    "Orange": "#f97316",
    "Pink": "#ec4899",
    "Lime": "#84cc16",
    "Indigo": "#6366f1",
    "Slate": "#64748b",
}

_DEFAULTS = {
    "theme": "Dark",
    "accent": "#10b981",
    "density": "comfortable",
}

_DENSITY = {
    "comfortable": {"ctrl_pad": "6px 12px", "input_pad": "5px 8px",
                    "item_pad": "5px", "menu_pad": "5px 18px",
                    "bar_h": "38px", "sb_w": "10px"},
    "compact": {"ctrl_pad": "3px 6px", "input_pad": "2px 6px",
                "item_pad": "2px", "menu_pad": "3px 12px",
                "bar_h": "30px", "sb_w": "8px"},
}

_DARK = {
    "window": "#0f1218", "surface": "#161b24", "raised": "#1d2430",
    "text": "#e6e9ef", "text_dim": "#9aa3b2", "border": "#2a3342",
    "hover": "#242d3d", "scroll": "#424d61", "tooltip_bg": "#1d2430",
    "tooltip_fg": "#e6e9ef", "input_bg": "#12161e", "shadow": "#000000",
}

_LIGHT = {
    "window": "#f4f6fa", "surface": "#ffffff", "raised": "#e9edf4",
    "text": "#1a2233", "text_dim": "#5b6577", "border": "#d4dbe6",
    "hover": "#e2e8f2", "scroll": "#c3ccd9", "tooltip_bg": "#253044",
    "tooltip_fg": "#ffffff", "input_bg": "#fbfcfe", "shadow": "#94a3b8",
}


def _resolve(theme, accent, density):
    theme = theme if theme is not None else _DEFAULTS["theme"]
    density = (density or _DEFAULTS["density"]).lower()
    if density not in _DENSITY:
        density = "comfortable"
    if accent is None or not str(accent).startswith("#"):
        accent = _DEFAULTS["accent"]
    return theme, str(accent), density


def accent_hex(name_or_hex, custom=None):
    """Map a preset name (or pass through a hex) to its hex color.
    'Custom' resolves to the dialog-provided hex, if any."""
    if name_or_hex == "Custom":
        if custom and str(custom).startswith("#"):
            return str(custom)
        return _DEFAULTS["accent"]
    if name_or_hex in ACCENTS:
        return ACCENTS[name_or_hex]
    if isinstance(name_or_hex, str) and name_or_hex.startswith("#"):
        return name_or_hex
    return _DEFAULTS["accent"]


def prepare_background(src, dim_pct, cache_dir=None):
    """Process a user photo for use as app wallpaper.

    Returns the path of a cached, dimmed PNG (max side 1600px), or None when
    the source is missing/unreadable. Deterministic per (file, dim) via a
    content + dim hash, so repeated theme applications never re-process."""
    if not src:
        return None
    try:
        from PySide6.QtGui import QColor, QImage, QPainter

        img = QImage(str(src))
        if img.isNull():
            return None

        # downscale giant photos before hashing (perf)
        max_side = 1600
        if max(img.width(), img.height()) > max_side:
            img = img.scaled(
                max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)

        h = hashlib.sha1(open(str(src), "rb").read()).hexdigest() \
            if os.path.exists(src) else "x"
        # scale-date guard: re-encode when dimensions changed on disk
        composite = f"{h}_{img.width()}x{img.height()}_{int(dim_pct) & 0xff}"
        name = hashlib.sha1(composite.encode("utf-8")).hexdigest()[:24]
        if cache_dir is None:
            cache_dir = user_cache_dir("HiCloudMP", "HiCloudMP",
                                       ensure_exists=True)
        os.makedirs(str(cache_dir), exist_ok=True)
        out = os.path.join(str(cache_dir), f"bg_{name}.png")
        if os.path.exists(out):
            return out

        if img.format() != QImage.Format.Format_ARGB32:
            img = img.convertToFormat(QImage.Format.Format_ARGB32)
        dim_alpha = max(0, min(255, int(int(dim_pct) * 2.55)))
        if dim_alpha:
            painter = QPainter(img)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.fillRect(img.rect(), QColor(8, 10, 14, dim_alpha))
            painter.end()
        img.save(out, "PNG")
        return out
    except Exception:
        return None


def build_qss(theme="Dark", accent=None, density="comfortable", bg=None):
    """Generate the full application stylesheet.

    `bg` (str path of a pre-dimmed photo) switches big surfaces to
    translucent glass and paints the photo behind the main content area."""
    theme, accent, density = _resolve(theme, accent, density)
    tk = _DARK if theme == "Dark" else _LIGHT
    d = _DENSITY[density]

    def _qa(hex_color, alpha):
        """hex color -> rgba() string at given opacity 0..255."""
        q = QColor(hex_color)
        return f"rgba({q.red()}, {q.green()}, {q.blue()}, {alpha})"

    acc_trans = _qa(accent, 28)
    acc_hover = _qa(accent, 60)

    qss = f"""
    QMainWindow, QDialog {{
        background-color: {tk['window']};
        color: {tk['text']};
    }}
    QWidget {{ color: {tk['text']}; }}
    QToolTip {{
        background-color: {tk['tooltip_bg']};
        color: {tk['tooltip_fg']};
        border: 1px solid {accent};
        padding: 4px 8px;
        border-radius: 4px;
    }}

    /* --- Menus --- */
    QMenuBar {{ background-color: {tk['window']}; color: {tk['text_dim']}; }}
    QMenuBar::item {{ padding: {d['item_pad']} 10px; border-radius: 4px; }}
    QMenuBar::item:selected {{ background: {tk['hover']}; color: {tk['text']}; }}
    QMenu {{
        background-color: {tk['surface']};
        color: {tk['text']};
        border: 1px solid {tk['border']};
        border-radius: 6px;
        padding: 4px;
    }}
    QMenu::item {{ padding: {d['menu_pad']}; border-radius: 4px; }}
    QMenu::item:selected {{ background-color: {acc_trans}; color: {tk['text']}; }}
    QMenu::separator {{ height: 1px; background: {tk['border']}; margin: 4px 6px; }}

    /* --- Controls --- */
    QPushButton {{
        background-color: {tk['raised']};
        color: {tk['text']};
        border: 1px solid {tk['border']};
        border-radius: 6px;
        padding: {d['ctrl_pad']};
    }}
    QPushButton:hover {{ background-color: {tk['hover']}; border-color: {accent}; }}
    QPushButton:pressed {{ background-color: {acc_hover}; }}
    QPushButton:disabled {{ color: {tk['text_dim']}; border-color: {tk['border']}; }}
    QPushButton[accentActive="true"] {{
        background-color: {acc_trans};
        color: {accent};
        border: 1px solid {accent};
        font-weight: 600;
    }}

    QLineEdit, QSpinBox {{
        background-color: {tk['input_bg']};
        color: {tk['text']};
        border: 1px solid {tk['border']};
        border-radius: 6px;
        padding: {d['input_pad']};
        selection-background-color: {accent};
    }}
    QLineEdit:focus, QSpinBox:focus {{ border-color: {accent}; }}

    QComboBox {{
        background-color: {tk['input_bg']};
        color: {tk['text']};
        border: 1px solid {tk['border']};
        border-radius: 6px;
        padding: {d['input_pad']};
        padding-right: 22px;
    }}
    QComboBox:hover {{ border-color: {accent}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background-color: {tk['surface']};
        color: {tk['text']};
        border: 1px solid {tk['border']};
        border-radius: 6px;
        selection-background-color: {acc_trans};
        outline: none;
    }}

    QCheckBox, QRadioButton {{ color: {tk['text']}; spacing: 8px; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
    QCheckBox::indicator:checked,
    QRadioButton::indicator:checked {{
        background: {accent};
        border: 1px solid {accent};
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        border: 1px solid {tk['border']};
        border-radius: 4px;
        background: {tk['input_bg']};
    }}
    QRadioButton::indicator {{ border-radius: 8px; }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {accent}; }}

    QGroupBox {{
        background-color: {tk['surface']};
        border: 1px solid {tk['border']};
        border-radius: 8px;
        margin-top: 12px;
        padding: 14px 10px 8px 10px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: {tk['text_dim']};
    }}

    /* --- Views / lists --- */
    QListWidget, QTreeWidget, QTableWidget, QListView, QTreeView {{
        background-color: {tk['surface']};
        color: {tk['text']};
        border: 1px solid {tk['border']};
        border-radius: 6px;
        outline: none;
    }}
    QListWidget::item, QTreeWidget::item, QListView::item {{
        padding: {d['item_pad']};
        border-radius: 4px;
        color: {tk['text']};
    }}
    QListWidget::item:hover, QTreeWidget::item:hover, QListView::item:hover {{ background: {tk['hover']}; }}
    QListWidget::item:selected, QTreeWidget::item:selected,
    QTableWidget::item:selected, QListView::item:selected {{
        background-color: {acc_trans};
        color: {tk['text']};
    }}

    QHeaderView::section {{
        background-color: {tk['raised']};
        color: {tk['text_dim']};
        padding: 4px 8px;
        border: none;
        border-bottom: 1px solid {tk['border']};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {tk['text_dim']};
        padding: 7px 14px;
        border: none;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{ color: {tk['text']}; border-bottom: 2px solid {accent}; }}
    QTabBar::tab:hover {{ color: {tk['text']}; }}
    QTabWidget::pane {{ border: 1px solid {tk['border']}; border-radius: 6px; }}

    /* --- Sliders / progress --- */
    QSlider {{ min-height: {d['bar_h']}; }}
    QSlider::groove:horizontal {{
        height: 6px;
        border-radius: 3px;
        background: {tk['border']};
    }}
    QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 3px; }}
    QSlider::handle:horizontal {{
        width: 14px;
        margin: -5px 0;
        border-radius: 7px;
        background: {tk['surface']};
        border: 2px solid {accent};
    }}
    QSlider::handle:horizontal:hover {{ background: {accent}; }}
    QProgressBar {{
        background: {tk['input_bg']};
        border: 1px solid {tk['border']};
        border-radius: 6px;
        text-align: center;
        color: {tk['text']};
    }}
    QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}

    /* --- Scrollbars (slim, overlay feel) --- */
    QScrollBar:vertical {{
        background: transparent; width: {d['sb_w']}; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {tk['scroll']}; min-height: 30px; border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {accent}; }}
    QScrollBar:horizontal {{
        background: transparent; height: {d['sb_w']}; margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {tk['scroll']}; min-width: 30px; border-radius: 4px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {accent}; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: none; border: none; width: 0px; height: 0px;
    }}

    QStatusBar {{
        background: {tk['window']};
        color: {tk['text_dim']};
        border-top: 1px solid {tk['border']};
    }}
    QDialogButtonBox QPushButton {{ min-width: 76px; }}

    /* ================ Structural layout (UI overhaul) ================ */
    QWidget#sidebar {{
        background-color: {tk['surface']};
        border-right: 1px solid {tk['border']};
    }}
    QLabel#brandTitle {{
        font-size: 20px;
        font-weight: 800;
        color: {tk['text']};
        letter-spacing: 0.5px;
    }}
    QLabel#brandSub {{
        font-size: 11px;
        color: {tk['text_dim']};
        margin-top: -6px;
        margin-left: 2px;
    }}
    QWidget#sidebar QPushButton {{
        background: transparent;
        border: none;
        text-align: left;
        color: {tk['text_dim']};
        padding: {d['ctrl_pad']};
        border-radius: 6px;
    }}
    QWidget#sidebar QPushButton:hover {{
        background: {tk['hover']};
        color: {tk['text']};
        border: none;
    }}
    QWidget#sidebar QLineEdit {{ margin: 0px; }}

    QFrame#nowCard {{
        background-color: {tk['surface']};
        border: 1px solid {tk['border']};
        border-radius: 12px;
    }}
    QLabel#coverCard {{
        background-color: {tk['input_bg']};
        border: 1px solid {tk['border']};
        border-radius: 12px;
    }}
    QLabel#trackTitle {{
        font-size: 18px;
        font-weight: 700;
        color: {tk['text']};
        font-family: "Segoe UI";
    }}
    QLabel#trackDim {{
        font-size: 12px;
        color: {tk['text_dim']};
    }}
    QFrame#transportBar {{
        background-color: {tk['surface']};
        border: 1px solid {tk['border']};
        border-radius: 12px;
    }}
    QFrame#transportBar QLabel {{ color: {tk['text_dim']}; font-size: 11px; }}
    QFrame#transportBar QSlider {{ min-height: 28px; }}
    QToolButton#playBtn {{
        background-color: {accent};
        border: none;
        border-radius: 28px;
        padding: 0px;
    }}
    QToolButton#playBtn:hover {{
        background-color: {accent};
        border: none;
    }}
    QToolButton#playBtn:pressed {{ background-color: {acc_hover}; border: none; }}
    QFrame#transportBar QToolButton {{
        background: transparent;
        border: none;
        border-radius: 8px;
        padding: {d['ctrl_pad']};
        color: {tk['text']};
    }}
    QFrame#transportBar QToolButton:hover {{ background: {tk['hover']}; border: none; }}
    QFrame#transportBar QToolButton[accentActive="true"] {{
        background: {acc_trans};
        color: {accent};
        border: none;
    }}
    """

    if bg:
        url = str(bg).replace("\\", "/")
        qss += f"""

    /* ================ Custom background (wallpaper mode) ================ */
    QWidget#central {{
        border-image: url('{url}') 0;
    }}
    QWidget#sidebar {{
        background-color: {_qa(tk['surface'], 232)};
    }}
    QFrame#nowCard, QFrame#transportBar {{
        background-color: {_qa(tk['surface'], 224)};
    }}
    QFrame#nowCard QLabel#trackTitle, QFrame#nowCard QLabel#trackDim,
    QFrame#transportBar QLabel {{
        color: {tk['text']};
    }}
    QGroupBox {{
        background-color: {_qa(tk['surface'], 236)};
    }}
    QListWidget, QTreeWidget, QTableWidget, QListView, QTreeView {{
        background-color: {_qa(tk['surface'], 244)};
    }}
    """
    return qss


def icon_colors(settings=None, theme=None, accent=None):
    """(accent_hex, text_hex, dim_hex) for icon tinting, theme-consistent."""
    if theme is None or accent is None:
        from PySide6.QtCore import QSettings as _QSettings
        q = settings
        if q is None:
            q = _QSettings("HiCloudMP", "HiCloudMP")
        theme = theme if theme is not None else q.value("theme", _DEFAULTS["theme"])
        accent = accent if accent is not None else q.value("ui/accent", _DEFAULTS["accent"])
    _, accent, _ = _resolve(theme, accent, None)
    tk = _DARK if theme == "Dark" else _LIGHT
    return accent, tk["text"], tk["text_dim"]


def apply_theme(widget, settings=None, theme=None, accent=None, density=None):
    """Resolve appearance values (explicit args win) and setStyleSheet on widget."""
    bg = None
    if theme is None or accent is None or density is None:
        from PySide6.QtCore import QSettings as _QSettings
        q = settings
        if q is None:
            q = _QSettings("HiCloudMP", "HiCloudMP")
        theme = theme if theme is not None else q.value("theme", _DEFAULTS["theme"])
        accent = accent if accent is not None else q.value("ui/accent", _DEFAULTS["accent"])
        density = density if density is not None else q.value("ui/density", _DEFAULTS["density"])
    if settings is not None:
        # Wallpaper mode: pre-dimmed photo behind translucent glass surfaces.
        bg_path = settings.value("ui/bg_image", "")
        if bg_path:
            try:
                dim = int(settings.value("ui/bg_dim", 35))
            except (TypeError, ValueError):
                dim = 35
            prepared = prepare_background(bg_path, dim)
            if prepared and os.path.exists(prepared):
                bg = prepared
    widget.setStyleSheet(build_qss(theme=theme, accent=accent,
                                   density=density, bg=bg))
    return widget


def apply_app_palette(app, theme="Dark"):
    """QPalette fallback for the QSS-unreachable native bits (menus on some
    styles, disabled text). Windows palette colors match the theme tokens."""
    tk = _DARK if theme == "Dark" else _LIGHT
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(tk["window"]))
    palette.setColor(QPalette.WindowText, QColor(tk["text"]))
    palette.setColor(QPalette.Base, QColor(tk["input_bg"]))
    palette.setColor(QPalette.AlternateBase, QColor(tk["surface"]))
    palette.setColor(QPalette.Text, QColor(tk["text"]))
    palette.setColor(QPalette.Button, QColor(tk["raised"]))
    palette.setColor(QPalette.ButtonText, QColor(tk["text"]))
    palette.setColor(QPalette.Highlight, QColor("#3d6a8a" if theme == "Dark" else "#b3d4fc"))
    palette.setColor(QPalette.HighlightedText, QColor(tk["text"]))
    palette.setColor(QPalette.ToolTipBase, QColor(tk["tooltip_bg"]))
    palette.setColor(QPalette.ToolTipText, QColor(tk["tooltip_fg"]))
    palette.setColor(QPalette.PlaceholderText, QColor(tk["text_dim"]))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(_DARK["text_dim"] if theme == "Dark" else _LIGHT["text_dim"]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(_DARK["text_dim"] if theme == "Dark" else _LIGHT["text_dim"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(_DARK["text_dim"] if theme == "Dark" else _LIGHT["text_dim"]))
    app.setPalette(palette)


def apply_app_theme(app, settings=None, theme=None, accent=None, density=None):
    """Full-application theme: QPalette + QSS on the QApplication itself."""
    if theme is None:
        from PySide6.QtCore import QSettings as _QSettings
        q = settings
        if q is None:
            q = _QSettings("HiCloudMP", "HiCloudMP")
        theme = q.value("theme", _DEFAULTS["theme"])
        accent = accent if accent is not None else q.value("ui/accent", _DEFAULTS["accent"])
        density = density if density is not None else q.value("ui/density", _DEFAULTS["density"])
    apply_app_palette(app, theme=theme)
    apply_theme(app, settings=settings, theme=theme, accent=accent, density=density)
