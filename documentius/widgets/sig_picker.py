from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from ..i18n import _t
from ..signatures import SignatureStore

_THUMB_W = 210
_THUMB_H = 75


def _sig_thumb(pixmap: QPixmap) -> QPixmap:
    bg = QPixmap(_THUMB_W, _THUMB_H)
    bg.fill(Qt.white)
    scaled = pixmap.scaled(
        _THUMB_W - 8, _THUMB_H - 8,
        Qt.KeepAspectRatio, Qt.SmoothTransformation,
    )
    painter = QPainter(bg)
    x = (_THUMB_W - scaled.width()) // 2
    y = (_THUMB_H - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return bg


class SignaturePicker(QDialog):

    signature_selected = Signal(QPixmap)

    def __init__(
        self, store: SignatureStore, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._sigs: list[tuple[Path, QPixmap]] = []
        self.setWindowTitle(_t("Seleziona firma", "Select signature"))
        self.setModal(True)
        self.resize(520, 320)
        self._setup_ui()
        self._reload()

    def _setup_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        self._list = QListWidget()
        self._list.setViewMode(QListView.IconMode)
        self._list.setFlow(QListView.LeftToRight)
        self._list.setWrapping(True)
        self._list.setResizeMode(QListView.Adjust)
        self._list.setIconSize(QSize(_THUMB_W, _THUMB_H))
        self._list.setGridSize(QSize(_THUMB_W + 12, _THUMB_H + 20))
        self._list.setSpacing(4)
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.setStyleSheet(
            "QListWidget{border:1px solid #888;border-radius:4px;background:#f5f5f5;}"
            "QListWidget::item{border:2px solid transparent;border-radius:4px;}"
            "QListWidget::item:selected{border-color:#0078d4;background:#e0f0ff;}"
        )
        self._list.itemDoubleClicked.connect(self._use_selected)
        lay.addWidget(self._list)

        row = QHBoxLayout()

        btn_new = QPushButton(_t("＋ Nuova firma", "+ New signature"))
        btn_new.setToolTip(_t("Disegna o importa una nuova firma", "Draw or import a new signature"))
        btn_new.clicked.connect(self._add_new)
        row.addWidget(btn_new)

        btn_del = QPushButton(_t("✕ Elimina", "✕ Delete"))
        btn_del.setToolTip(_t("Elimina firma selezionata", "Delete selected signature"))
        btn_del.clicked.connect(self._delete_selected)
        row.addWidget(btn_del)

        row.addStretch()

        btn_cancel = QPushButton(_t("Annulla", "Cancel"))
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_cancel)

        btn_use = QPushButton(_t("Usa →", "Use →"))
        btn_use.setDefault(True)
        btn_use.setStyleSheet(
            "QPushButton{background:#0078d4;color:white;border:none;"
            "padding:4px 16px;border-radius:5px;}"
            "QPushButton:hover{background:#106ebe;}"
        )
        btn_use.clicked.connect(self._use_selected)
        row.addWidget(btn_use)

        lay.addLayout(row)

    def _reload(self) -> None:
        self._list.clear()
        self._sigs = self._store.load_all()
        for path, pixmap in self._sigs:
            item = QListWidgetItem()
            item.setIcon(QIcon(_sig_thumb(pixmap)))
            item.setData(Qt.UserRole, (path, pixmap))
            item.setTextAlignment(Qt.AlignCenter)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _use_selected(self) -> None:
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(
                self,
                _t("Nessuna firma", "No signature"),
                _t("Seleziona una firma prima.", "Select a signature first."),
            )
            return
        _, pixmap = item.data(Qt.UserRole)
        self.signature_selected.emit(pixmap)
        self.accept()

    def _delete_selected(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        path, _ = item.data(Qt.UserRole)
        self._store.delete(path)
        self._reload()

    def _add_new(self) -> None:
        from .sig_dialog import SignatureDialog
        dlg = SignatureDialog(self)
        if dlg.exec() == QDialog.Accepted:
            px = dlg.get_pixmap()
            if px:
                self._store.save(px)
                self._reload()
                self._list.setCurrentRow(self._list.count() - 1)
