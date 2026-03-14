from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPaintEvent, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from ..i18n import _t
from .ann_layer import AnnotationLayer


class PageCanvas(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self._pixmap: Optional[QPixmap] = None
        self.ann_layer = AnnotationLayer(self)

    def load(self, pixmap: QPixmap, scale: float) -> None:
        self._pixmap = pixmap
        dpr = pixmap.devicePixelRatio()
        lw = int(pixmap.width() / dpr)
        lh = int(pixmap.height() / dpr)
        self.setFixedSize(lw, lh)
        self.ann_layer.setFixedSize(lw, lh)
        self.ann_layer.set_scale(scale)
        self.update()

    def paintEvent(self, _: QPaintEvent) -> None:
        p = QPainter(self)
        bg = self.palette().color(self.backgroundRole())
        if self._pixmap:
            p.fillRect(self.rect(), bg)
            p.drawPixmap(self.rect(), self._pixmap)
        else:
            p.fillRect(self.rect(), QColor(200, 200, 200))
            p.drawText(
                self.rect(), Qt.AlignCenter,
                _t("Nessuna pagina selezionata", "No page selected"),
            )
