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


def build_qss(theme="Dark", accent=None, density="comfortable"):
    """Generate the full application stylesheet."""
    theme, accent, density = _resolve(theme, accent, density)
    tk = _DARK if theme == "Dark" else _LIGHT
    d = _DENSITY[density]

    def _qa(hex_color, alpha):
        """hex color -> rgba() string at given opacity 0..255."""
        q = QColor(hex_color)
        return f"rgba({q.red()}, {q.green()}, {q.blue()}, {alpha})"

    acc_trans = _qa(accent, 28)
    acc_hover = _qa(accent, 60)

    return f"""
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
    """


def apply_theme(widget, settings=None, theme=None, accent=None, density=None):
    """Resolve appearance values (explicit args win) and setStyleSheet on widget."""
    if theme is None or accent is None or density is None:
        from PySide6.QtCore import QSettings as _QSettings
        q = settings
        if q is None:
            q = _QSettings("HiCloudMP", "HiCloudMP")
        theme = theme if theme is not None else q.value("theme", _DEFAULTS["theme"])
        accent = accent if accent is not None else q.value("ui/accent", _DEFAULTS["accent"])
        density = density if density is not None else q.value("ui/density", _DEFAULTS["density"])
    widget.setStyleSheet(build_qss(theme=theme, accent=accent, density=density))
    return widget


def accent_hex(name_or_hex):
    """Map a preset name (or pass through a hex) to its hex color."""
    if name_or_hex in ACCENTS:
        return ACCENTS[name_or_hex]
    if isinstance(name_or_hex, str) and name_or_hex.startswith("#"):
        return name_or_hex
    return _DEFAULTS["accent"]


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
