from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.ffmpeg import ensure_ffmpeg


if __name__ == "__main__":
    ensure_ffmpeg()
    print("ffmpeg bootstrap completed")
