from pathlib import Path
from PySide6.QtCore import QObject, QUrl, Signal, QTimer
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaDevices
from emss.alerts.audio import validate_audio_file


class AlertAudioPlayer(QObject):
    failed = Signal(str)
    completed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.output)
        self.player.errorOccurred.connect(lambda *_: self._fail('Audio gagal diputar; periksa file/perangkat.'))
        self.player.mediaStatusChanged.connect(self._media_status_changed)
        self._sequence: list[Path] = []
        self.limit = QTimer(self)
        self.limit.setSingleShot(True)
        self.limit.timeout.connect(lambda: self._fail('Audio dihentikan setelah batas 30 detik.'))

    def play(self, path, volume):
        return self.play_sequence([path], volume)

    def play_sequence(self, paths, volume):
        self.player.stop()  # A single player: never mix overlapping prescription sounds.
        try:
            local_paths = [validate_audio_file(path) for path in paths if path]
            if not local_paths:
                raise ValueError('Audio belum dipilih; periksa pengaturan suara.')
            if not QMediaDevices.audioOutputs():
                raise ValueError('Perangkat audio tidak tersedia.')
            if volume == 0:
                raise ValueError('Volume aplikasi 0 (mute).')
        except (ValueError, OSError) as exc:
            self.failed.emit(str(exc))
            return False
        self.output.setVolume(max(0, min(100, volume)) / 100)
        self._sequence = list(local_paths)
        self._play_next()
        self.limit.start(30000)
        return True

    def _play_next(self):
        if not self._sequence:
            self.limit.stop()
            self.completed.emit()
            return
        self.player.setSource(QUrl.fromLocalFile(str(self._sequence.pop(0))))
        self.player.play()

    def _media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._play_next()

    def _fail(self, message):
        self.limit.stop()
        self._sequence.clear()
        self.player.stop()
        self.failed.emit(message)
