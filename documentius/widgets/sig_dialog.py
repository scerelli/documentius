from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import (
    QColor, QImage, QMouseEvent, QPaintEvent, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QColorDialog, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSlider, QTabWidget, QVBoxLayout, QWidget,
)

from ..i18n import _t


class SignatureCanvas(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(520, 180)
        self._img = QImage(520, 180, QImage.Format_ARGB32)
        self._img.fill(Qt.transparent)
        self._drawing = False
        self._last = QPoint()
        self._color = QColor(0, 0, 0)
        self._width = 3
        self.setCursor(Qt.CrossCursor)
        self.setStyleSheet("background:white;border:1px solid #c0c0c0;border-radius:4px;")

    def set_color(self, c: QColor) -> None:
        self._color = c

    def set_width(self, w: int) -> None:
        self._width = w

    def clear(self) -> None:
        self._img.fill(Qt.transparent)
        self.update()

    def is_empty(self) -> bool:
        for y in range(0, self._img.height(), 4):
            for x in range(0, self._img.width(), 4):
                if QColor(self._img.pixel(x, y)).alpha() > 10:
                    return False
        return True

    def cropped_pixmap(self) -> QPixmap:
        mx, my = self._img.width(), self._img.height()
        nx, ny = 0, 0
        found = False
        for y in range(self._img.height()):
            for x in range(self._img.width()):
                if QColor(self._img.pixel(x, y)).alpha() > 10:
                    mx, my = min(mx, x), min(my, y)
                    nx, ny = max(nx, x), max(ny, y)
                    found = True
        if not found:
            return QPixmap.fromImage(self._img)
        pad = 8
        x0 = max(0, mx - pad)
        y0 = max(0, my - pad)
        x1 = min(self._img.width(),  nx + pad + 1)
        y1 = min(self._img.height(), ny + pad + 1)
        rect = QRect(x0, y0, x1 - x0, y1 - y0)
        return QPixmap.fromImage(self._img.copy(rect))

    def paintEvent(self, _: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.white)
        p.drawImage(0, 0, self._img)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            self._drawing = True
            self._last = e.position().toPoint()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drawing and e.buttons() & Qt.LeftButton:
            p = QPainter(self._img)
            p.setPen(QPen(self._color, self._width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawLine(self._last, e.position().toPoint())
            self._last = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            self._drawing = False


class SignatureDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t("Crea / Importa Firma", "Create / Import Signature"))
        self.setModal(True)
        self.resize(570, 370)
        self._result: Optional[QPixmap] = None
        self._uploaded: Optional[QPixmap] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        lay = QVBoxLayout(self)
        self._tabs = QTabWidget()

        dw = QWidget(); dl = QVBoxLayout(dw)
        dl.addWidget(QLabel(_t(
            "Disegna la firma con il mouse:",
            "Draw your signature with the mouse:",
        )))
        self._canvas = SignatureCanvas()
        dl.addWidget(self._canvas)
        row = QHBoxLayout()
        bc = QPushButton(_t("Cancella", "Clear"))
        bc.clicked.connect(self._canvas.clear)
        bk = QPushButton(_t("Colore…", "Color…"))
        bk.clicked.connect(self._pick_color)
        sld = QSlider(Qt.Horizontal)
        sld.setRange(1, 12); sld.setValue(3); sld.setMaximumWidth(110)
        sld.valueChanged.connect(self._canvas.set_width)
        row.addWidget(bc); row.addWidget(bk)
        row.addWidget(QLabel(_t("Sp.:", "Sz:"))); row.addWidget(sld); row.addStretch()
        dl.addLayout(row)
        self._tabs.addTab(dw, _t("✎  Disegna", "✎  Draw"))

        uw = QWidget(); ul = QVBoxLayout(uw)
        ul.addWidget(QLabel(_t("Carica immagine (PNG, JPG, …):", "Load image (PNG, JPG, …):")))
        self._preview = QLabel(_t("Nessuna immagine caricata", "No image loaded"))
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumHeight(130)
        self._preview.setStyleSheet("border:1px dashed #aaa;border-radius:4px;")
        ul.addWidget(self._preview)
        bu = QPushButton(_t("📂  Scegli immagine…", "📂  Choose image…"))
        bu.clicked.connect(self._upload)
        ul.addWidget(bu); ul.addStretch()
        self._tabs.addTab(uw, _t("🖼️  Carica", "🖼️  Load"))

        lay.addWidget(self._tabs)

        btns = QHBoxLayout(); btns.addStretch()
        bc2 = QPushButton(_t("Annulla", "Cancel"))
        bc2.clicked.connect(self.reject)
        ok = QPushButton(_t("Aggiungi →", "Add →"))
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        btns.addWidget(bc2); btns.addWidget(ok)
        lay.addLayout(btns)

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(0, 0, 0), self)
        if c.isValid():
            self._canvas.set_color(c)

    def _upload(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            _t("Scegli immagine", "Choose image"),
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.webp)",
        )
        if path:
            px = QPixmap(path)
            if not px.isNull():
                self._uploaded = px
                self._preview.setPixmap(
                    px.scaled(480, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

    def _accept(self) -> None:
        if self._tabs.currentIndex() == 0:
            if self._canvas.is_empty():
                QMessageBox.warning(
                    self,
                    _t("Attenzione", "Warning"),
                    _t("Disegna prima una firma!", "Please draw a signature first!"),
                )
                return
            self._result = self._canvas.cropped_pixmap()
        else:
            if self._uploaded is None:
                QMessageBox.warning(
                    self,
                    _t("Attenzione", "Warning"),
                    _t("Carica prima un'immagine!", "Please load an image first!"),
                )
                return
            self._result = self._uploaded
        self.accept()

    def get_pixmap(self) -> Optional[QPixmap]:
        return self._result
