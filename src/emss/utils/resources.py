from __future__ import annotations

import sys
from pathlib import Path


def bundled_resource(*parts: str) -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).joinpath(*parts)
    return Path(__file__).resolve().parents[3].joinpath(*parts)
