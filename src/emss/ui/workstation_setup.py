from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QDialogButtonBox, QMessageBox


class WorkstationSetupDialog(QDialog):
    """One explicit, passwordless selection; persistence belongs to the service."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Pengaturan pertama Mode Farmasi')
        layout = QVBoxLayout(self)
        text = QLabel('Pilih lokasi instalasi E-MAS pada komputer ini. Pilihan disimpan tetap; '
            'resep, popup, dan suara hanya untuk layanan yang dipilih. Tidak memerlukan kata sandi. '
            'Pastikan pilihan benar sebelum melanjutkan.')
        text.setWordWrap(True)
        layout.addWidget(text)
        self.choice = QComboBox()
        self.choice.addItem('Pilih lokasi farmasi…', '')
        self.choice.addItem('Farmasi Rawat Jalan', 'RALAN')
        self.choice.addItem('Farmasi Rawat Inap', 'RANAP')
        layout.addWidget(self.choice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Simpan lokasi dan masuk')
        buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        self.choice.currentIndexChanged.connect(lambda _: buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(self.choice.currentData())))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(480, 210)

    @property
    def care_setting(self):
        return self.choice.currentData()
