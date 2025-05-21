from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFormLayout,
    QLineEdit, QTabWidget, QWidget, QLabel
)
from PySide6.QtCore import Qt

class AddCloudDialog(QDialog):
    """Dialog for adding cloud storage accounts"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Cloud Account")
        self.resize(450, 300)
        
        # Create tab widget for different cloud types
        self.tab_widget = QTabWidget()
        
        # Create tabs for each cloud type
        self.setup_webdav_tab()
        self.setup_dropbox_tab()
        self.setup_gdrive_tab()
        self.setup_onedrive_tab()
        
        # Buttons
        btns = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tab_widget)
        main_layout.addLayout(btns)
        self.setLayout(main_layout)
        
    def setup_webdav_tab(self):
        tab = QWidget()
        form = QFormLayout()
        
        self.webdav_name = QLineEdit()
        self.webdav_url = QLineEdit()
        self.webdav_user = QLineEdit()
        self.webdav_pass = QLineEdit()
        self.webdav_pass.setEchoMode(QLineEdit.Password)
        
        form.addRow("Account Name:", self.webdav_name)
        form.addRow("WebDAV URL:", self.webdav_url)
        form.addRow("Username:", self.webdav_user)
        form.addRow("Password:", self.webdav_pass)
        
        help_label = QLabel("Enter your WebDAV server information. The URL should include "
                           "the protocol (http:// or https://) and end with a slash.")
        help_label.setWordWrap(True)
        
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(help_label)
        layout.addStretch()
        
        tab.setLayout(layout)
        self.tab_widget.addTab(tab, "WebDAV")
        
    def setup_dropbox_tab(self):
        tab = QWidget()
        form = QFormLayout()
        
        self.dropbox_name = QLineEdit()
        self.dropbox_token = QLineEdit()
        
        form.addRow("Account Name:", self.dropbox_name)
        form.addRow("API Token:", self.dropbox_token)
        
        help_label = QLabel("To connect to Dropbox, you need an API token. Visit "
                           "https://www.dropbox.com/developers/apps to create an app and generate a token.")
        help_label.setWordWrap(True)
        
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(help_label)
        layout.addStretch()
        
        tab.setLayout(layout)
        self.tab_widget.addTab(tab, "Dropbox")
        
    def setup_gdrive_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        
        label = QLabel("Google Drive integration is coming soon!")
        label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(label)
        tab.setLayout(layout)
        self.tab_widget.addTab(tab, "Google Drive")
        
    def setup_onedrive_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        
        label = QLabel("OneDrive integration is coming soon!")
        label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(label)
        tab.setLayout(layout)
        self.tab_widget.addTab(tab, "OneDrive")
        
    def get_data(self):
        current_tab = self.tab_widget.currentIndex()
        
        if current_tab == 0:  # WebDAV
            return {
                "type": "webdav",
                "name": self.webdav_name.text().strip(),
                "config": {
                    "webdav_hostname": self.webdav_url.text().strip(),
                    "webdav_login": self.webdav_user.text().strip(),
                    "webdav_password": self.webdav_pass.text().strip()
                }
            }
        elif current_tab == 1:  # Dropbox
            return {
                "type": "dropbox",
                "name": self.dropbox_name.text().strip(),
                "config": {
                    "token": self.dropbox_token.text().strip()
                }
            }
        else:
            # Placeholder for future implementations
            return {"type": "unknown", "name": "Not Implemented", "config": {}}


class EditCloudDialog(QDialog):
    """Dialog for editing cloud storage accounts"""
    def __init__(self, cloud_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Cloud Account")
        self.resize(450, 300)
        self.cloud_data = cloud_data
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Set up the appropriate tab based on cloud type
        cloud_type = cloud_data["type"].lower()
        if cloud_type == "webdav":
            self.setup_webdav_tab()
            self.tab_widget.setCurrentIndex(0)
        elif cloud_type == "dropbox":
            self.setup_dropbox_tab()
            self.tab_widget.setCurrentIndex(1)
        else:
            # Add placeholder tabs for completeness
            self.setup_webdav_tab()
            self.setup_dropbox_tab()
            
        # Buttons
        btns = QHBoxLayout()
        self.ok_btn = QPushButton("Save Changes")
        self.cancel_btn = QPushButton("Cancel")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tab_widget)
        main_layout.addLayout(btns)
        self.setLayout(main_layout)
        
    def setup_webdav_tab(self):
        tab = QWidget()
        form = QFormLayout()
        
        self.webdav_name = QLineEdit()
        self.webdav_url = QLineEdit()
        self.webdav_user = QLineEdit()
        self.webdav_pass = QLineEdit()
        self.webdav_pass.setEchoMode(QLineEdit.Password)
        
        # Pre-fill fields with existing data
        if self.cloud_data["type"] == "webdav":
            self.webdav_name.setText(self.cloud_data["name"])
            self.webdav_url.setText(self.cloud_data["config"].get("webdav_hostname", ""))
            self.webdav_user.setText(self.cloud_data["config"].get("webdav_login", ""))
            self.webdav_pass.setText(self.cloud_data["config"].get("webdav_password", ""))
        
        form.addRow("Account Name:", self.webdav_name)
        form.addRow("WebDAV URL:", self.webdav_url)
        form.addRow("Username:", self.webdav_user)
        form.addRow("Password:", self.webdav_pass)
        
        help_label = QLabel("Enter your WebDAV server information. The URL should include "
                           "the protocol (http:// or https://) and end with a slash.")
        help_label.setWordWrap(True)
        
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(help_label)
        layout.addStretch()
        
        tab.setLayout(layout)
        self.tab_widget.addTab(tab, "WebDAV")
        
    def setup_dropbox_tab(self):
        tab = QWidget()
        form = QFormLayout()
        
        self.dropbox_name = QLineEdit()
        self.dropbox_token = QLineEdit()
        
        # Pre-fill fields with existing data
        if self.cloud_data["type"] == "dropbox":
            self.dropbox_name.setText(self.cloud_data["name"])
            self.dropbox_token.setText(self.cloud_data["config"].get("token", ""))
        
        form.addRow("Account Name:", self.dropbox_name)
        form.addRow("API Token:", self.dropbox_token)
        
        help_label = QLabel("To connect to Dropbox, you need an API token. Visit "
                           "https://www.dropbox.com/developers/apps to create an app and generate a token.")
        help_label.setWordWrap(True)
        
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(help_label)
        layout.addStretch()
        
        tab.setLayout(layout)
        self.tab_widget.addTab(tab, "Dropbox")
        
    def get_data(self):
        # Keep the original cloud type
        cloud_type = self.cloud_data["type"]
        
        if cloud_type == "webdav":
            return {
                "type": cloud_type,
                "name": self.webdav_name.text().strip(),
                "config": {
                    "webdav_hostname": self.webdav_url.text().strip(),
                    "webdav_login": self.webdav_user.text().strip(),
                    "webdav_password": self.webdav_pass.text().strip()
                }
            }
        elif cloud_type == "dropbox":
            return {
                "type": cloud_type,
                "name": self.dropbox_name.text().strip(),
                "config": {
                    "token": self.dropbox_token.text().strip()
                }
            }
        else:
            # Return original data if type not supported for editing
            return self.cloud_data 