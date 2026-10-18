from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFormLayout,
    QLineEdit, QTabWidget, QWidget, QLabel, QDialogButtonBox, QComboBox,
    QStackedWidget, QCheckBox, QSlider, QListWidget, QListWidgetItem,
    QGroupBox, QScrollArea, QFrame, QToolButton, QColorDialog, QFileDialog,
    QApplication, QMessageBox
)
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QColor

_HELP = {
    "webdav": (
        "Enter your WebDAV server details. The URL should be in the format:\n"
        "http(s)://example.com/remote.php/dav/files/username/\n\n"
        "For Nextcloud/OwnCloud, you can find this in the WebDAV section of your settings."
    ),
    "ampache": (
        "Ampache-compatible API (Nextcloud Music, Ampache server). Use the URL from\n"
        "Nextcloud \u2192 Music \u2192 Settings → 'Ampache address', e.g.\n"
        "https://cloud.example.com/apps/music/ampache\n"
        "The player appends /server/xml.server.php automatically. Use the same\n"
        "username/password as shown on that settings page (the app password)."
    ),
    "subsonic": (
        "Subsonic-compatible API (Nextcloud Music, Subsonic server). Use the URL from\n"
        "Nextcloud \u2192 Music \u2192 Settings → 'Subsonic address', e.g.\n"
        "https://cloud.example.com/apps/music/subsonic\n"
        "Use the username/password shown next to it (the app password)."
    ),
}


class AddCloudDialog(QDialog):
    """Dialog for adding cloud storage accounts (WebDAV / Ampache / Subsonic)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Cloud Storage")
        self.resize(520, 340)

        layout = QVBoxLayout()

        self.type_combo = QComboBox()
        self.type_combo.addItems(["WebDAV", "Ampache", "Subsonic"])
        layout.addWidget(QLabel("Provider type:"))
        layout.addWidget(self.type_combo)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # --- WebDAV page ---
        webdav_page = QWidget()
        wd_form = QFormLayout()
        self.webdav_name = QLineEdit()
        self.webdav_url = QLineEdit()
        self.webdav_username = QLineEdit()
        self.webdav_password = QLineEdit()

        self.webdav_password.setEchoMode(QLineEdit.Password)
        wd_form.addRow("Name:", self.webdav_name)
        wd_form.addRow("Server URL:", self.webdav_url)
        wd_form.addRow("Username:", self.webdav_username)
        wd_form.addRow("Password:", self.webdav_password)
        self._finish_page(webdav_page, wd_form, "webdav")

        # --- Ampache page ---
        amp_page = QWidget()
        amp_form = QFormLayout()
        self.ampache_name = QLineEdit()
        self.ampache_url = QLineEdit()
        self.ampache_username = QLineEdit()
        self.ampache_password = QLineEdit()

        self.ampache_password.setEchoMode(QLineEdit.Password)
        amp_form.addRow("Name:", self.ampache_name)
        amp_form.addRow("Ampache URL:", self.ampache_url)
        amp_form.addRow("Username:", self.ampache_username)
        amp_form.addRow("Password:", self.ampache_password)
        self._finish_page(amp_page, amp_form, "ampache")

        # --- Subsonic page ---
        sub_page = QWidget()
        sub_form = QFormLayout()
        self.subsonic_name = QLineEdit()
        self.subsonic_url = QLineEdit()
        self.subsonic_username = QLineEdit()
        self.subsonic_password = QLineEdit()

        self.subsonic_password.setEchoMode(QLineEdit.Password)
        sub_form.addRow("Name:", self.subsonic_name)
        sub_form.addRow("Subsonic URL:", self.subsonic_url)
        sub_form.addRow("Username:", self.subsonic_username)
        sub_form.addRow("Password:", self.subsonic_password)
        self._finish_page(sub_page, sub_form, "subsonic")

        self.type_combo.currentIndexChanged.connect(
            lambda i: self.stack.setCurrentIndex(i))

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

    def _finish_page(self, page, form, ptype):
        form_holder = QWidget()
        inner = QVBoxLayout()
        inner.addLayout(form)
        help_label = QLabel(_HELP[ptype])
        help_label.setWordWrap(True)
        inner.addWidget(help_label)
        inner.addStretch()
        form_holder.setLayout(inner)
        page.setLayout(QVBoxLayout(page))
        page.layout().addWidget(form_holder)
        self.stack.addWidget(page)

    def get_data(self):
        itype = self.type_combo.currentIndex()
        if itype == 0:
            return {
                "type": "webdav",
                "name": self.webdav_name.text().strip() or "WebDAV",
                "config": {
                    "webdav_hostname": self.webdav_url.text().strip(),
                    "webdav_login": self.webdav_username.text().strip(),
                    "webdav_password": self.webdav_password.text().strip(),
                },
            }
        if itype == 1:
            return {
                "type": "ampache",
                "name": self.ampache_name.text().strip() or "Ampache",
                "config": {
                    "ampache_url": self.ampache_url.text().strip(),
                    "ampache_user": self.ampache_username.text().strip(),
                    "ampache_password": self.ampache_password.text().strip(),
                },
            }
        return {
            "type": "subsonic",
            "name": self.subsonic_name.text().strip() or "Subsonic",
            "config": {
                "subsonic_url": self.subsonic_url.text().strip(),
                "subsonic_user": self.subsonic_username.text().strip(),
                "subsonic_password": self.subsonic_password.text().strip(),
            },
        }


class EditCloudDialog(QDialog):
    """Dialog for editing an existing cloud account, by provider."""

    def __init__(self, cloud_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Cloud Account")
        self.resize(520, 340)
        self.cloud_data = cloud_data

        itype = cloud_data.get("type", "webdav")
        cfg = cloud_data.get("config", {})

        layout = QVBoxLayout()
        form = QFormLayout()

        self.name_edit = QLineEdit(cloud_data.get("name", ""))

        self.url_edit = QLineEdit()
        self.user_edit = QLineEdit()
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)

        if itype == "ampache":
            self.url_edit.setText(cfg.get("ampache_url", ""))
            self.user_edit.setText(cfg.get("ampache_user", ""))
            self.pass_edit.setText(cfg.get("ampache_password", ""))
            url_label = "Ampache URL:"
        elif itype == "subsonic":
            self.url_edit.setText(cfg.get("subsonic_url", ""))
            self.user_edit.setText(cfg.get("subsonic_user", ""))
            self.pass_edit.setText(cfg.get("subsonic_password", ""))
            url_label = "Subsonic URL:"
        else:  # webdav
            self.url_edit.setText(cfg.get("webdav_hostname", ""))
            self.user_edit.setText(cfg.get("webdav_login", ""))
            self.pass_edit.setText(cfg.get("webdav_password", ""))
            url_label = "WebDAV URL:"

        form.addRow("Account name:", self.name_edit)
        form.addRow(url_label, self.url_edit)
        form.addRow("Username:", self.user_edit)
        form.addRow("Password:", self.pass_edit)

        self._itype = itype

        help_label = QLabel(f"Editing an existing {self._itype} account.")
        help_label.setWordWrap(True)

        btns = QHBoxLayout()
        self.ok_btn = QPushButton("Save Changes")
        self.cancel_btn = QPushButton("Cancel")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)

        layout.addLayout(form)
        layout.addWidget(help_label)
        layout.addLayout(btns)
        self.setLayout(layout)

    def get_data(self):
        base = {"name": self.name_edit.text().strip()}
        if self._itype == "ampache":
            return {"type": "ampache", "config": {
                "ampache_url": self.url_edit.text().strip(),
                "ampache_user": self.user_edit.text().strip(),
                "ampache_password": self.pass_edit.text().strip(),
            }, **base}
        if self._itype == "subsonic":
            return {"type": "subsonic", "config": {
                "subsonic_url": self.url_edit.text().strip(),
                "subsonic_user": self.user_edit.text().strip(),
                "subsonic_password": self.pass_edit.text().strip(),
            }, **base}
        return {"type": "webdav", "config": {
            "webdav_hostname": self.url_edit.text().strip(),
            "webdav_login": self.user_edit.text().strip(),
            "webdav_password": self.pass_edit.text().strip(),
        }, **base}


class EqualizerDialog(QDialog):
    """Simple 10-band equalizer UI.

    Slider changes are applied LIVE via ``apply_cb(gains_db, enabled)``
    (so auditioning is immediate); pressing OK persists; Cancel restores
    the state captured at open time.
    """

    BAND_LABELS = ("31", "62", "125", "250", "500", "1k", "2k", "4k", "8k", "16k")
    MIN_DB, MAX_DB = -12, 12

    def __init__(self, parent, gains_db, enabled, preset, apply_cb):
        super().__init__(parent)
        self.setWindowTitle("Equalizer")
        self.resize(420, 320)
        self._apply_cb = apply_cb
        self._initial = (tuple(gains_db), bool(enabled), str(preset))

        import dsp
        self._presets = dict(dsp.PRESETS)

        self.enabled_check = QCheckBox("Equalizer on")
        self.enabled_check.setChecked(bool(enabled))
        self.enabled_check.toggled.connect(self._emit)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Custom")
        for name in self._presets:
            self.preset_combo.addItem(name)
        if preset in self._presets:
            self.preset_combo.setCurrentText(preset)
        self.preset_combo.currentTextChanged.connect(self._on_preset)

        top = QHBoxLayout()
        top.addWidget(self.enabled_check)
        top.addStretch(1)
        top.addWidget(QLabel("Preset:"))
        top.addWidget(self.preset_combo)

        band_row = QHBoxLayout()
        self._sliders = []
        for label, value in zip(self.BAND_LABELS, gains_db):
            col = QVBoxLayout()
            slider = QSlider(Qt.Vertical)
            slider.setRange(self.MIN_DB, self.MAX_DB)
            slider.setValue(int(value))
            slider.setMinimumWidth(18)
            slider.valueChanged.connect(self._on_slider)
            lab = QLabel(label)
            lab.setAlignment(Qt.AlignHCenter)
            col.addWidget(lab)
            col.addWidget(slider, 1)
            band_row.addLayout(col)
            self._sliders.append(slider)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(band_row, 1)
        layout.addWidget(buttons)

    # ------------------------------------------------------------ behavior
    def _current_gains(self):
        return tuple(float(s.value()) for s in self._sliders)

    def _emit(self, *_):
        if self._apply_cb is not None:
            self._apply_cb(self._current_gains(), self.enabled_check.isChecked())

    def _on_slider(self, _):
        self.preset_combo.blockSignals(True)
        gains = self._current_gains()
        matched = "Custom"
        for name, values in self._presets.items():
            if tuple(gains) == tuple(values):
                matched = name
                break
        if self.preset_combo.currentText() != matched:
            self.preset_combo.setCurrentText(matched)
        self.preset_combo.blockSignals(False)
        self._emit()

    def _on_preset(self, name):
        values = self._presets.get(name)
        if values is None:
            return
        for slider, value in zip(self._sliders, values):
            slider.blockSignals(True)
            slider.setValue(int(value))
            slider.blockSignals(False)
        self._emit()

    def reject(self):
        gains, enabled, _ = self._initial
        if self._apply_cb is not None:
            self._apply_cb(tuple(float(g) for g in gains), bool(enabled))
        super().reject()


class CloudAccountsDialog(QDialog):
    def __init__(self, parent, clouds):
        super().__init__(parent)
        self.setWindowTitle("Cloud Accounts")
        self.resize(500, 350)
        self.clouds = clouds
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.refresh_list()
        layout.addWidget(self.list_widget)
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
        edit_btn = QPushButton("Edit")
        remove_btn = QPushButton("Remove")
        add_btn.clicked.connect(self.add_cloud)
        edit_btn.clicked.connect(self.edit_cloud)
        remove_btn.clicked.connect(self.remove_cloud)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(remove_btn)
        layout.addLayout(btn_layout)
        # Close with QDialog.Accepted so the caller persists changes; without
        # this the dialog can only ever reject, making edits hard to save.
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        self.button_box.button(QDialogButtonBox.Ok).setText("Done")
        self.button_box.accepted.connect(self.accept)
        layout.addWidget(self.button_box)
    def refresh_list(self):
        self.list_widget.clear()
        for cloud in self.clouds:
            status = "Connected" if cloud.get("files") else "Not Synced"
            last_sync = cloud.get("last_sync", "Never")
            self.list_widget.addItem(f"{cloud['name']} ({cloud['type']}) - {status} | Last Sync: {last_sync}")
    def add_cloud(self):
        dlg = AddCloudDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            if data["type"] != "unknown":
                self.clouds.append({
                    "type": data["type"],
                    "name": data["name"],
                    "config": data["config"],
                    "files": [],
                    "last_sync": "Never"
                })
                self.refresh_list()
    def edit_cloud(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.clouds):
            return
        cloud = self.clouds[row]
        dlg = EditCloudDialog(cloud, self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            cloud["name"] = data["name"]
            cloud["config"] = data["config"]
            self.refresh_list()
    def remove_cloud(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.clouds):
            return
        del self.clouds[row]
        self.refresh_list()

class SettingsDialog(QDialog):
    """Settings with sidebar navigation: Playback / Appearance / Library /
    Web Remote. All historical widget attribute names are preserved."""

    WEB_HINT = ("Control this app from your phone or any other computer — "
                "like a remote control for your music. Both devices only "
                "need to be on the same Wi-Fi network.")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(640, 470)
        # Use the parent app's QSettings (tests isolate via the fixture);
        # standalone fallback keeps the dialog usable on its own.
        self.settings = getattr(parent, "settings", None) \
            if parent is not None else None
        if self.settings is None:
            self.settings = QSettings("HiCloudMP", "HiCloudMP")
        self.parent = parent
        self.custom_accent_hex = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        body = QHBoxLayout()
        body.setSpacing(12)
        outer.addLayout(body, 1)

        # ---------------- Navigation rail ----------------
        self.nav_list = QListWidget(self)
        self.nav_list.setObjectName("settingsNav")
        self.nav_list.setFixedWidth(148)
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body.addWidget(self.nav_list)

        # ---------------- Pages ----------------
        self.pages = QStackedWidget(self)
        body.addWidget(self.pages, 1)
        self.pages.addWidget(self._build_playback_page())
        self.pages.addWidget(self._build_appearance_page())
        self.pages.addWidget(self._build_library_page())
        self.pages.addWidget(self._build_web_page())

        self.nav_list.currentRowChanged.connect(self.pages.setCurrentIndex)
        for label in ("Playback", "Appearance", "Library", "Web Remote"):
            self.nav_list.addItem(QListWidgetItem(label))
        self.nav_list.setCurrentRow(0)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        outer.addWidget(btn_box)

    # ------------------------------------------------------------ pages
    def _build_playback_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)
        box = QGroupBox("Playback")
        v.addWidget(box)
        v.addStretch(1)
        form = QFormLayout(box)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.settings.value("volume", 70, int))
        form.addRow("Default volume", self.volume_slider)
        hint = QLabel("Used every time the app starts.")
        hint.setObjectName("hintLabel")
        form.addRow("", hint)
        self.visualizer_checkbox = QCheckBox("Show spectrum visualizer while playing")
        self.visualizer_checkbox.setChecked(
            self.settings.value("ui/visualizer_enabled", False, type=bool))
        form.addRow("", self.visualizer_checkbox)
        viz_hint = QLabel("Routes audio through the equalizer engine "
                          "(bit-identical with a flat EQ) so the spectrum "
                          "shows real data even with the EQ disabled.")
        viz_hint.setObjectName("hintLabel")
        viz_hint.setWordWrap(True)
        form.addRow("", viz_hint)
        self.output_combo = QComboBox()
        import audio_devices
        for did, desc in audio_devices.list_output_devices():
            self.output_combo.addItem(desc, did)
        stored = str(self.settings.value("audio/output_device", "", type=str)
                     or "")
        idx = self.output_combo.findData(stored) if stored else 0
        self.output_combo.setCurrentIndex(max(0, idx))
        form.addRow("Output device", self.output_combo)
        out_hint = QLabel("The equalizer engine switches at the next track.")
        out_hint.setObjectName("hintLabel")
        form.addRow("", out_hint)
        return page

    def _build_appearance_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        page.setWidget(inner)
        v = QVBoxLayout(inner)
        v.setContentsMargins(4, 4, 4, 4)

        # --- Colors ---
        colors_box = QGroupBox("Colors")
        v.addWidget(colors_box)
        form = QFormLayout(colors_box)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.setCurrentText(self.settings.value("theme", "Dark"))
        form.addRow("Theme", self.theme_combo)

        import theme as _theme
        self.accent_combo = QComboBox()
        self.accent_combo.addItems(list(_theme.ACCENTS.keys()))
        stored_accent = self.settings.value("ui/accent", _theme.ACCENTS["Emerald"])
        default_accent_name = next(
            (n for n, h in _theme.ACCENTS.items()
             if h.lower() == str(stored_accent).lower()), None)
        if default_accent_name is None:
            # A previously chosen custom color: surface it as "Custom"
            self.custom_accent_hex = str(stored_accent)
            self.accent_combo.addItem("Custom")
            self.accent_combo.setCurrentText("Custom")
        else:
            self.accent_combo.setCurrentText(default_accent_name)

        pick_row = QHBoxLayout()
        self.custom_accent_btn = QPushButton("Pick any color…")
        self.custom_accent_btn.setToolTip("Choose any color as the accent")
        self.custom_accent_btn.clicked.connect(self.pick_custom_accent)
        pick_row.addWidget(self.accent_combo)
        pick_row.addWidget(self.custom_accent_btn)
        form.addRow("Accent color", pick_row)

        self.density_combo = QComboBox()
        self.density_combo.addItems(["Comfortable", "Compact"])
        self.density_combo.setCurrentText(
            str(self.settings.value("ui/density", "comfortable")).capitalize())
        form.addRow("UI density", self.density_combo)

        # --- Background image ---
        bg_box = QGroupBox("Background image")
        v.addWidget(bg_box)
        bgl = QVBoxLayout(bg_box)
        self.bg_image_edit = QLineEdit(str(self.settings.value("ui/bg_image", "")))
        self.bg_image_edit.setReadOnly(True)
        self.bg_image_edit.setPlaceholderText("No background image selected")
        bgl.addWidget(self.bg_image_edit)
        brows = QHBoxLayout()
        self.bg_browse_btn = QPushButton("Choose image…")
        self.bg_browse_btn.clicked.connect(self.browse_bg_image)
        self.bg_clear_btn = QPushButton("Remove")
        self.bg_clear_btn.setEnabled(bool(self.bg_image_edit.text()))
        self.bg_clear_btn.clicked.connect(self.clear_bg_image)
        brows.addWidget(self.bg_browse_btn)
        brows.addWidget(self.bg_clear_btn)
        brows.addStretch(1)
        bgl.addLayout(brows)
        dim_row = QHBoxLayout()
        dim_row.addWidget(QLabel("Darkness"))
        self.bg_dim_slider = QSlider(Qt.Horizontal)
        self.bg_dim_slider.setRange(0, 80)
        self.bg_dim_slider.setValue(
            int(self._safe_int(self.settings.value("ui/bg_dim", 35))))
        self.bg_dim_label = QLabel(f"{self.bg_dim_slider.value()}%")
        self.bg_dim_slider.valueChanged.connect(
            lambda v_: self.bg_dim_label.setText(f"{v_}%"))
        self.bg_dim_slider.setFixedWidth(220)
        dim_row.addWidget(self.bg_dim_slider)
        dim_row.addWidget(self.bg_dim_label)
        dim_row.addStretch(1)
        bgl.addLayout(dim_row)
        bg_hint = QLabel("The image goes behind the player panels. "
                         "Darkness makes it subtle. Applies instantly.")
        bg_hint.setObjectName("hintLabel")
        bg_hint.setWordWrap(True)
        bgl.addWidget(bg_hint)
        v.addStretch(1)
        return page

    def _build_library_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)
        box = QGroupBox("Library & cloud accounts")
        v.addWidget(box)
        v.addStretch(1)
        form = QFormLayout(box)
        self.download_folder_edit = QLineEdit(
            str(self.settings.value("download_folder", "")))
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self.browse_folder)
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.download_folder_edit, 1)
        folder_layout.addWidget(browse_btn)
        form.addRow("Download folder", folder_layout)
        self.cloud_btn = QPushButton("Manage cloud accounts…")
        self.cloud_btn.clicked.connect(self.open_cloud_accounts)
        form.addRow("", self.cloud_btn)
        hint = QLabel("Streams and downloads from Nextcloud, "
                      "Ampache or Subsonic servers.")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        form.addRow("", hint)

        updates_box = QGroupBox("Updates")
        v.addWidget(updates_box)
        uf = QFormLayout(updates_box)
        self.update_btn = QPushButton("Check for updates…")
        self.update_btn.clicked.connect(self.check_for_updates)
        uf.addRow("", self.update_btn)
        self.update_result_label = QLabel("")
        self.update_result_label.setObjectName("hintLabel")
        self.update_result_label.setWordWrap(True)
        uf.addRow("", self.update_result_label)
        return page

    def _build_web_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)

        self.web_hint_label = QLabel(self.WEB_HINT)
        self.web_hint_label.setWordWrap(True)
        v.addWidget(self.web_hint_label)

        link_box = QGroupBox("Your remote link")
        v.addWidget(link_box)
        v.addStretch(1)
        ll = QVBoxLayout(link_box)
        token = ""
        port = 5000
        if self.parent is not None and hasattr(self.parent, "ensure_web_token"):
            token = self.parent.ensure_web_token()
            port = getattr(self.parent, "web_port", port)
        else:
            token = str(self.settings.value("web/token", ""))
        base = f"http://localhost:{port}" if token == "" else \
            f"http://localhost:{port}/?token={token}"
        self.web_link_edit = QLineEdit(base)
        self.web_link_edit.setReadOnly(True)
        ll.addWidget(self.web_link_edit)
        link_row = QHBoxLayout()
        self.web_copy_btn = QPushButton("Copy link")
        self.web_copy_btn.clicked.connect(self.copy_web_link)
        self.web_open_btn = QPushButton("Open in browser")
        self.web_open_btn.clicked.connect(self.open_web_link)
        link_row.addWidget(self.web_copy_btn)
        link_row.addWidget(self.web_open_btn)
        link_row.addStretch(1)
        ll.addLayout(link_row)

        self.web_status_label = QLabel(self._web_status_text())
        self.web_status_label.setObjectName("hintLabel")
        ll.addWidget(self.web_status_label)

        opts = QGroupBox("Options")
        v.addWidget(opts)
        ol = QVBoxLayout(opts)
        self.web_checkbox = QCheckBox("Enable web remote")
        self.web_checkbox.setChecked(self.settings.value("web_interface", False, bool))
        self.web_checkbox.toggled.connect(
            lambda _on: self.web_status_label.setText(self._web_status_text()))
        ol.addWidget(self.web_checkbox)
        self.lan_checkbox = QCheckBox("Allow other devices on this network "
                                      "(needed for phones)")
        self.lan_checkbox.setChecked(self.settings.value("web/host", "127.0.0.1") == "0.0.0.0")
        ol.addWidget(self.lan_checkbox)
        lan_hint = QLabel("Music stays private: only people who open the "
                          "link above can connect. Leave this off if you "
                          "only use the remote on this computer.")
        lan_hint.setObjectName("hintLabel")
        lan_hint.setWordWrap(True)
        ol.addWidget(lan_hint)

        # Advanced: raw access code stays reachable, mostly invisible
        self.web_token_toggle = QToolButton()
        self.web_token_toggle.setText("show access code…")
        self.web_token_toggle.setCheckable(True)
        self.web_token_toggle.setAutoRaise(True)
        self.web_token_edit = QLineEdit(token)
        self.web_token_edit.setReadOnly(True)
        self.web_token_edit.setVisible(False)
        self.web_token_toggle.toggled.connect(self.web_token_edit.setVisible)
        adv_row = QHBoxLayout()
        adv_row.addStretch(1)
        adv_row.addWidget(self.web_token_toggle)
        adv_row.addWidget(self.web_token_edit, 1)
        v.addLayout(adv_row)
        return page

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _safe_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 35

    def _web_status_text(self):
        running = bool(getattr(self.parent, "web_server", None)
                       if self.parent else False)
        enabled = self.settings.value("web_interface", False, bool)
        if running:
            return "Web remote is running. Open the link on any device."
        return ("Web remote is off. Turn it on, then open the link "
                "on your phone.") if enabled else \
            "Web remote is off."

    def pick_custom_accent(self):
        initial = QColor(self.custom_accent_hex or "#10b981")
        color = QColorDialog.getColor(initial, self, "Custom accent color")
        if color is None or not color.isValid():
            return  # dialog cancelled — no change
        self.custom_accent_hex = color.name()
        if self.accent_combo.findText("Custom") < 0:
            self.accent_combo.addItem("Custom")
        self.accent_combo.setCurrentText("Custom")

    def browse_bg_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a background image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.bg_image_edit.setText(path)
            self.bg_clear_btn.setEnabled(True)
            self.bg_preview_path = path

    def clear_bg_image(self):
        self.bg_image_edit.setText("")

    def copy_web_link(self):
        QApplication.clipboard().setText(self.web_link_edit.text())

    def open_web_link(self):
        import webbrowser
        webbrowser.open(self.web_link_edit.text())

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.download_folder_edit.setText(folder)

    def save_settings(self):
        self.settings.setValue("volume", self.volume_slider.value())
        old_viz = bool(self.settings.value("ui/visualizer_enabled",
                                           False, type=bool))
        new_viz = self.visualizer_checkbox.isChecked()
        self.settings.setValue("ui/visualizer_enabled", new_viz)
        if new_viz != old_viz and self.parent is not None:
            try:
                self.parent.apply_visualizer_toggle(new_viz)
            except Exception:
                pass
        self.settings.setValue(
            "audio/output_device",
            str(self.output_combo.currentData() or ""))
        self.settings.setValue("theme", self.theme_combo.currentText())
        # Appearance persistence (accent stored as hex; density lowercased)
        import theme as _theme
        self.settings.setValue("ui/accent", _theme.accent_hex(
            self.accent_combo.currentText(), custom=self.custom_accent_hex))
        self.settings.setValue("ui/density", self.density_combo.currentText().lower())
        self.settings.setValue("ui/bg_image", self.bg_image_edit.text())
        self.settings.setValue("ui/bg_dim", self.bg_dim_slider.value())
        self.settings.setValue("download_folder", self.download_folder_edit.text())
        self.settings.setValue("web_interface", self.web_checkbox.isChecked())
        self.settings.setValue("web/host", "0.0.0.0" if self.lan_checkbox.isChecked() else "127.0.0.1")

    def open_cloud_accounts(self):
        if self.parent:
            dlg = CloudAccountsDialog(self, self.parent.clouds)
            dlg.exec()

    # ------------------------------------------------------------ updates
    def check_for_updates(self):
        """Manual check against GitHub releases, off the UI thread."""
        import threading

        import updates_check
        self.update_btn.setEnabled(False)
        self.update_result_label.setText("Checking…")
        parent = self.parent
        dispatch = (parent.run_on_ui.emit
                    if parent is not None and hasattr(parent, "run_on_ui")
                    else (lambda fn: fn()))

        def work():
            data = error = None
            try:
                data = updates_check.latest_release()
            except Exception as e:
                error = str(e)
            dispatch(lambda: self._on_update_result(data, error))

        threading.Thread(target=work, daemon=True,
                         name="update-check").start()

    def _on_update_result(self, data, error):
        import updates_check
        self.update_btn.setEnabled(True)
        latest = (data or {}).get("tag", "")
        url = (data or {}).get("url", "") or updates_check.RELEASES_PAGE
        if error is not None:
            self.update_result_label.setText(f"Update check failed: {error}")
            return
        from updates_check import APP_VERSION, compare_versions
        verdict = None
        if latest:
            verdict = compare_versions(APP_VERSION, latest)
        if verdict == -1:
            self.update_result_label.setText(
                f"A new version is available: {latest} (you have {APP_VERSION}).")
            QMessageBox.information(
                self, "Update available",
                f"HiCloudMP {latest} is available (you have {APP_VERSION}).\n"
                f"Download it from:\n{url}",
                QMessageBox.StandardButton.Ok)
        elif verdict == 0:
            self.update_result_label.setText(
                f"HiCloudMP {APP_VERSION} — you're up to date.")
        elif verdict == 1:
            self.update_result_label.setText(
                f"Running {APP_VERSION} (newer than the latest release {latest}).")
        else:
            self.update_result_label.setText(
                f"Latest release: {latest or RELEASES_PAGE}")

