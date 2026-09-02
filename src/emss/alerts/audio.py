"""Local alert audio with original bundled tones and optional user overrides."""
from dataclasses import dataclass, field, asdict
import json
from pathlib import Path
import wave

CATEGORIES = (
    'contraindicated', 'major', 'significant-review', 'duplicate',
    'high-alert', 'screening-clear',
)


def bundled_audio_paths() -> dict[str, str]:
    import sys
    root = getattr(sys, '_MEIPASS', None)
    folder = (Path(root) / 'emss' / 'assets' / 'audio' if root else
              Path(__file__).resolve().parents[1] / 'assets' / 'audio')
    return {category: str((folder / f'{category}.wav').resolve()) for category in CATEGORIES}


@dataclass
class AudioPreferences:
    volume: int = 75
    paths: dict[str, str] = field(default_factory=bundled_audio_paths)

    @classmethod
    def load(cls, path):
        try:
            raw = json.loads(Path(path).read_text(encoding='utf-8'))
            paths = bundled_audio_paths()
            supplied = raw['paths']
            if not isinstance(supplied, dict) or any(
                key not in CATEGORIES or not isinstance(value, str)
                for key, value in supplied.items()
            ):
                raise ValueError('Path audio tidak valid')
            paths.update(supplied)  # Upgrade old 3-sound preferences without losing choices.
            value = cls(volume=int(raw['volume']), paths=paths)
            if not 1 <= value.volume <= 100 or set(value.paths) != set(CATEGORIES):
                raise ValueError('Konfigurasi audio tidak valid')
            return value
        except (OSError, ValueError, KeyError, TypeError):
            return cls()

    def save(self, path):
        if not 1 <= self.volume <= 100 or set(self.paths) != set(CATEGORIES):
            raise ValueError('Konfigurasi audio tidak valid')
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(asdict(self), indent=2), encoding='utf-8')
        temp.replace(target)


def validate_audio_file(filename):
    if not filename:
        raise ValueError('Audio belum dipilih; periksa pengaturan suara.')
    path = Path(filename)
    if not path.is_absolute() or str(path).startswith(('\\\\', '//')):
        raise ValueError('Pilih file audio lokal dengan path absolut.')
    if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('File audio hilang atau melebihi 20 MB.')
    if path.suffix.lower() == '.wav':
        try:
            with wave.open(str(path), 'rb') as wav:
                duration = wav.getnframes() / wav.getframerate()
                if not 0 < duration <= 30 or wav.getcomptype() != 'NONE':
                    raise ValueError('Gunakan PCM WAV berdurasi maksimal 30 detik.')
                if len(wav.readframes(wav.getnframes())) != wav.getnframes() * wav.getnchannels() * wav.getsampwidth():
                    raise ValueError('Isi WAV terpotong.')
        except (wave.Error, EOFError) as exc:
            raise ValueError('File WAV rusak atau tidak didukung.') from exc
    elif path.suffix.lower() != '.mp3':
        raise ValueError('Format audio harus WAV atau MP3.')
    return path


def resolve_audio_path(category: str, configured: str) -> tuple[Path | None, bool]:
    """Return a valid configured path, or the bundled category fallback.

    The fallback is intentionally per category and is not written back to the
    user's preferences.  A broken custom path therefore cannot silence an
    alert permanently, while the user still receives a diagnostic and can
    replace the custom file from the settings panel.
    """
    try:
        return validate_audio_file(configured), False
    except (OSError, ValueError):
        fallback = bundled_audio_paths().get(category, "")
        try:
            return validate_audio_file(fallback), True
        except (OSError, ValueError):
            return None, True
