import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

SIZES = [16, 24, 32, 48, 64, 96, 128, 256, 512]
APP_ID = "io.github.scerelli.Documentius"
SVG = Path(__file__).parent / "documentius.svg"
OUT = Path(__file__).parent


def render(renderer: QSvgRenderer, size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    renderer.render(p)
    p.end()
    return img


def main() -> None:
    app = QApplication(sys.argv)

    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        print(f"ERROR: could not load {SVG}", file=sys.stderr)
        sys.exit(1)

    for size in SIZES:
        img = render(renderer, size)
        out_path = OUT / f"{APP_ID}.{size}.png"
        img.save(str(out_path))
        print(f"  {size:>4}x{size}  →  {out_path.name}")

    img512 = render(renderer, 512)
    primary = OUT / f"{APP_ID}.png"
    img512.save(str(primary))
    print(f"   512x512  →  {primary.name}  (primary)")


if __name__ == "__main__":
    main()
