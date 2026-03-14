import os
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QPixmap


def _store_dir() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = config_home / "documentius" / "signatures"
    d.mkdir(parents=True, exist_ok=True)
    return d


class SignatureStore:

    def save(self, pixmap: QPixmap) -> Path:
        name = f"sig_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        path = _store_dir() / name
        pixmap.save(str(path), "PNG")
        return path

    def load_all(self) -> list[tuple[Path, QPixmap]]:
        results = []
        for f in sorted(_store_dir().glob("sig_*.png")):
            px = QPixmap(str(f))
            if not px.isNull():
                results.append((f, px))
        return results

    def delete(self, path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass
