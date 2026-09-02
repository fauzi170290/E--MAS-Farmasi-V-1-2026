"""Identify a named actor for one action without granting a new application session."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout
from emss.services.authentication import AuthenticationError


class ActionIdentityDialog(QDialog):
    def __init__(self, container, roles, parent=None):
        super().__init__(parent)
        self.container, self.roles, self.actor = container, roles, None
        self.setWindowTitle('Verifikasi Petugas')
        self.setMinimumWidth(380)
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.message = QLabel('Masukkan akun petugas untuk mencatat tindakan atas nama Anda. Mode Farmasi tetap aktif.')
        self.message.setWordWrap(True)
        form = QFormLayout()
        form.addRow('Nama pengguna', self.username)
        form.addRow('Kata sandi', self.password)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.message)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _submit(self):
        try:
            actor = self.container.authentication.authenticate(self.username.text(), self.password.text())
        except AuthenticationError as exc:
            self.message.setText(str(exc))
            self.password.clear()
            return
        self.password.clear()
        if actor.username == 'mode.farmasi' or not actor.roles.intersection(self.roles):
            self.message.setText('Akun tidak berwenang melakukan tindakan ini.')
            return
        if actor.must_change_password:
            self.message.setText('Ubah kata sandi melalui halaman masuk sebelum mencatat tindakan.')
            return
        self.actor = actor
        self.accept()
