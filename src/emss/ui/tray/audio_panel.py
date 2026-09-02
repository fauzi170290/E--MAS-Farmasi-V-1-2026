from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QLineEdit, QPushButton, QFileDialog
from PySide6.QtCore import Qt
from emss.alerts.audio import AudioPreferences, CATEGORIES, validate_audio_file
from emss.audit.service import AuditEvent
from emss.config.settings import AppEnvironment
from emss.ui.tray.audio import AlertAudioPlayer


class AudioSettingsPanel(QWidget):
    def __init__(self, container, user):
        super().__init__()
        self.container, self.user = container, user
        self.path = container.settings.data_dir / 'audio-preferences.json'
        self.preferences = AudioPreferences.load(self.path)
        self.player = AlertAudioPlayer(self)
        self.fields = {}
        layout = QVBoxLayout(self)
        note = QLabel('Enam nada orisinal sudah dibundel: kontraindikasi, mayor, interaksi signifikan, '
            'potensi duplikasi, obat high-alert, dan pemeriksaan lengkap tanpa interaksi. '
            'Volume aplikasi minimal 1% sehingga tidak dapat dibuat senyap. File tidak dikirim ke internet dan tidak '
            'memerlukan akun atau kredensial. Anda tetap dapat mengganti tiap nada dengan WAV/MP3 lokal.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(1, 100)
        self.volume.setValue(self.preferences.volume)
        self.volume_label = QLabel()
        self.volume.valueChanged.connect(lambda value: self.volume_label.setText(f'Volume: {value}%'))
        self.volume_label.setText(f'Volume: {self.volume.value()}%')
        layout.addWidget(self.volume_label)
        layout.addWidget(self.volume)
        self.status = QLabel('Belum diuji pada perangkat ini.')
        self.status.setWordWrap(True)
        self.player.failed.connect(self.status.setText)
        for category in CATEGORIES:
            row = QHBoxLayout()
            row.addWidget(QLabel({'contraindicated':'Kontraindikasi', 'major':'Mayor',
                'significant-review':'Interaksi signifikan', 'duplicate':'Potensi duplikasi',
                'high-alert':'Obat high-alert', 'screening-clear':'Pemeriksaan lengkap'}[category]))
            field = QLineEdit(self.preferences.paths[category])
            field.setReadOnly(True)
            self.fields[category] = field
            row.addWidget(field, 1)
            choose = QPushButton('Pilih WAV/MP3')
            choose.clicked.connect(lambda _=False, c=category: self.choose(c))
            test = QPushButton('Uji Suara')
            test.clicked.connect(lambda _=False, c=category: self.test(c))
            test.setEnabled(container.settings.environment in {AppEnvironment.DEVELOPMENT, AppEnvironment.TEST})
            row.addWidget(choose)
            row.addWidget(test)
            layout.addLayout(row)
        save = QPushButton('Simpan Suara Peringatan')
        save.setProperty('primaryAction', True)
        save.clicked.connect(self.save)
        layout.addWidget(save)
        layout.addWidget(self.status)
        layout.addStretch()

    def choose(self, category):
        filename, _ = QFileDialog.getOpenFileName(self, 'Pilih audio lokal', '', 'Audio (*.wav *.mp3)')
        if filename:
            try:
                validate_audio_file(filename)
            except (OSError, ValueError) as exc:
                self.status.setText(str(exc))
                return
            self.fields[category].setText(filename)

    def test(self, category):
        if self.container.settings.environment not in {AppEnvironment.DEVELOPMENT, AppEnvironment.TEST}:
            self.status.setText('Demo hanya tersedia di development/test; silent pilot tetap tanpa suara.')
            return
        self.status.setText('UJI audio perangkat; tidak membuat resep/hasil skrining.')
        self.player.play(self.fields[category].text(), self.volume.value())

    def save(self):
        try:
            AudioPreferences(self.volume.value(), {c: f.text() for c, f in self.fields.items()}).save(self.path)
            with self.container.database.session() as session:
                self.container.audit.append(session, AuditEvent(category='USER_ACTIVITY', action='AUDIO_PREFERENCES_SAVED',
                    outcome='SUCCESS', actor_user_id=self.user.id, details={'volume': self.volume.value(),
                    'categories_configured': [c for c, f in self.fields.items() if f.text()]}))
                session.commit()
            self.status.setText('Pilihan tersimpan. Pastikan volume Windows/perangkat tidak mute; popup tetap aktif jika audio gagal.')
        except (OSError, ValueError):
            self.status.setText('Pengaturan gagal disimpan. Periksa izin folder lokal.')
