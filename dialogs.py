from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFormLayout,
    QLineEdit, QTabWidget, QWidget, QLabel, QDialogButtonBox, QComboBox,
    QStackedWidget
)
from PySide6.QtCore import Qt

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
