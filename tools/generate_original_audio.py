"""Generate the original E-MAS alert tones using Python's standard library."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

RATE = 44_100
OUT = Path(__file__).resolve().parents[1] / "src" / "emss" / "assets" / "audio"
PATTERNS = {
    "minor": ((660, .15), (0, .12), (550, .25)),
    "screening-incomplete": ((440, .22), (0, .18), (440, .22), (0, .18), (330, .35)),
    # Descending urgent phrases are deliberately unlike the rising clear phrase.
    "contraindicated": ((880, .22), (0, .08), (660, .22), (0, .08), (440, .42)),
    "major": ((740, .20), (0, .10), (740, .20), (0, .10), (554, .32)),
    "significant-review": ((622, .18), (0, .08), (622, .18), (0, .08), (494, .28)),
    "duplicate": ((587, .15), (494, .15), (587, .15), (0, .08), (392, .30)),
    "high-alert": ((523, .16), (659, .16), (523, .16), (659, .28)),
    "screening-clear": ((523, .18), (659, .18), (784, .32)),
}


def render(name: str, notes: tuple[tuple[int, float], ...]) -> None:
    frames: list[bytes] = []
    for frequency, duration in notes:
        count = round(RATE * duration)
        for index in range(count):
            if frequency == 0:
                sample = 0
            else:
                # Short fades prevent clicks; low amplitude leaves safe headroom.
                fade = min(1.0, index / 220, (count - index - 1) / 220)
                sample = round(10_500 * fade * math.sin(2 * math.pi * frequency * index / RATE))
            frames.append(struct.pack('<h', sample))
    with wave.open(str(OUT / f'{name}.wav'), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(b''.join(frames))


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    for tone_name, tone_notes in PATTERNS.items():
        render(tone_name, tone_notes)
