from pathlib import Path
from typing import Optional

import fitz

from PySide6.QtCore import QRect, QSettings, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QPainter, QPalette,
    QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFileDialog,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QPushButton, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QVBoxLayout, QWidget,
)

import qtawesome as qta

from ..i18n import _t
from ..models import PageEntry
from ..pdf_ops import render_thumbnail


_IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}

_PIXMAP_ROLE = Qt.UserRole + 1

_PAD   = 8
_NUM_H = 20
_X_R   = 20


def _x_rect(item_rect: QRect) -> QRect:
    return QRect(item_rect.right() - _X_R - 4, item_rect.top() + 4, _X_R, _X_R)


class _PageDelegate(QStyledItemDelegate):
    def __init__(self, list_widget: QListWidget) -> None:
        super().__init__(list_widget)
        self._lw = list_widget

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()

        selected = bool(option.state & QStyle.State_Selected)

        painter.fillRect(
            option.rect,
            option.palette.highlight() if selected else option.palette.base(),
        )

        px: Optional[QPixmap] = index.data(_PIXMAP_ROLE)
        if px and not px.isNull():
            img_rect = option.rect.adjusted(_PAD, _PAD, -_PAD, -(_PAD + _NUM_H))
            scaled = px.scaled(img_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = img_rect.x() + (img_rect.width()  - scaled.width())  // 2
            y = img_rect.y() + (img_rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        text_color = (
            option.palette.highlightedText().color()
            if selected else option.palette.text().color()
        )
        painter.setPen(text_color)
        num_rect = QRect(
            option.rect.left(),
            option.rect.bottom() - _NUM_H,
            option.rect.width(),
            _NUM_H,
        )
        painter.drawText(num_rect, Qt.AlignCenter, index.data(Qt.DisplayRole) or "")

        if not selected:
            painter.setPen(option.palette.mid().color())
            painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())

        if index.row() == self._lw.hover_row():
            xr = _x_rect(option.rect)
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(200, 30, 30))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(xr)
            painter.setPen(QPen(QColor(255, 255, 255), 1.8))
            m = 5
            cx, cy = xr.center().x(), xr.center().y()
            painter.drawLine(cx - m, cy - m, cx + m, cy + m)
            painter.drawLine(cx + m, cy - m, cx - m, cy + m)
            painter.restore()

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        cached = index.data(Qt.SizeHintRole)
        if cached and cached.isValid():
            return cached
        w = max(80, self._lw.viewport().width())
        h = int(w * 1.414) + _NUM_H + _PAD * 2
        return QSize(w, h)


class PageListWidget(QListWidget):

    pages_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setSpacing(0)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setItemDelegate(_PageDelegate(self))
        self.model().rowsMoved.connect(self.pages_changed)
        self._last_vp_w: int = 0
        self._hover_row: int = -1
        self._deleted_pages: list[list[tuple[int, PageEntry]]] = []

    def hover_row(self) -> int:
        return self._hover_row

    def can_undo_page_delete(self) -> bool:
        return bool(self._deleted_pages)

    def undo_last_delete(self) -> None:
        if not self._deleted_pages:
            return
        batch = self._deleted_pages.pop()
        for row, entry in sorted(batch, key=lambda x: x[0]):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, entry)
            self._refresh_item(item, entry)
            self.insertItem(min(row, self.count()), item)
        self.pages_changed.emit()

    def _confirm_delete(self, count: int) -> bool:
        settings = QSettings("io.github.scerelli", "Documentius")
        if settings.value("page_panel/skip_delete_confirm", False, type=bool):
            return True
        label = (
            _t(f"Eliminare {count} pagine?", f"Delete {count} pages?")
            if count > 1
            else _t("Eliminare la pagina selezionata?", "Delete the selected page?")
        )
        box = QMessageBox(self)
        box.setWindowTitle(_t("Elimina pagina", "Delete page"))
        box.setText(label)
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Ok)
        cb = QCheckBox(_t("Non chiedere più", "Don't ask again"))
        box.setCheckBox(cb)
        result = box.exec()
        if cb.isChecked():
            settings.setValue("page_panel/skip_delete_confirm", True)
        return result == QMessageBox.Ok

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        vw = self.viewport().width()
        if abs(vw - self._last_vp_w) > 4:
            self._last_vp_w = vw
            self._refresh_all_items()

    def add_pdf(self, path: str) -> None:
        try:
            doc = fitz.open(path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                _t("Errore", "Error"),
                _t(f"Impossibile aprire:\n{exc}", f"Cannot open:\n{exc}"),
            )
            return
        for i in range(len(doc)):
            self._add_entry(PageEntry(doc=doc, page_num=i, source_path=path))
        self.pages_changed.emit()

    def add_image(self, path: str) -> None:
        try:
            doc = fitz.open(path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                _t("Errore", "Error"),
                _t(f"Impossibile aprire:\n{exc}", f"Cannot open:\n{exc}"),
            )
            return
        self._add_entry(PageEntry(doc=doc, page_num=0, source_path=path))
        self.pages_changed.emit()

    def get_pages(self) -> list[PageEntry]:
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def rotate_selected(self, degrees: int) -> None:
        item = self.currentItem()
        if not item:
            return
        entry: PageEntry = item.data(Qt.UserRole)
        entry.doc[entry.page_num].set_rotation(
            (entry.doc[entry.page_num].rotation + degrees) % 360
        )
        self._refresh_item(item, entry)
        self.pages_changed.emit()

    def mouseMoveEvent(self, e) -> None:
        idx = self.indexAt(e.pos())
        new_row = idx.row() if idx.isValid() else -1
        if new_row != self._hover_row:
            self._hover_row = new_row
            self.viewport().update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e) -> None:
        if self._hover_row != -1:
            self._hover_row = -1
            self.viewport().update()
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            idx = self.indexAt(e.pos())
            if idx.isValid():
                xr = _x_rect(self.visualRect(idx))
                if xr.contains(e.pos()):
                    row = idx.row()
                    if not self._confirm_delete(1):
                        return
                    entry: PageEntry = self.item(row).data(Qt.UserRole)
                    self._deleted_pages.append([(row, entry)])
                    self.takeItem(row)
                    self._hover_row = -1
                    self.pages_changed.emit()
                    return
        super().mousePressEvent(e)

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e: QDragMoveEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e: QDropEvent) -> None:
        if e.mimeData().hasUrls():
            had_selection = self.currentRow() >= 0
            for url in e.mimeData().urls():
                path = url.toLocalFile()
                ext = Path(path).suffix.lower()
                if ext == ".pdf":
                    self.add_pdf(path)
                elif ext in _IMG_EXTS:
                    self.add_image(path)
            e.acceptProposedAction()
            if not had_selection and self.count() > 0:
                self.setCurrentRow(0)
        else:
            super().dropEvent(e)
            self.pages_changed.emit()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Delete:
            items = self.selectedItems()
            if items and self._confirm_delete(len(items)):
                batch = []
                for item in items:
                    row = self.row(item)
                    entry: PageEntry = item.data(Qt.UserRole)
                    batch.append((row, entry))
                self._deleted_pages.append(batch)
                for item in items:
                    self.takeItem(self.row(item))
                self._hover_row = -1
                self.pages_changed.emit()
            return
        super().keyPressEvent(e)

    def contextMenuEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if not item:
            return
        if not item.isSelected():
            self.setCurrentItem(item)
        selected = self.selectedItems()
        count = len(selected)
        menu = QMenu(self)
        del_label = (
            _t(f"Elimina {count} pagine", f"Delete {count} pages")
            if count > 1
            else _t("Elimina pagina", "Delete page")
        )
        act_del   = menu.addAction(del_label)
        menu.addSeparator()
        act_rot_l = menu.addAction(_t("Ruota 90° sinistra",  "Rotate 90° left"))
        act_rot_r = menu.addAction(_t("Ruota 90° destra",    "Rotate 90° right"))
        act_rot_l.setEnabled(count == 1)
        act_rot_r.setEnabled(count == 1)
        action = menu.exec(event.globalPos())
        if action == act_del:
            if self._confirm_delete(count):
                batch = [(self.row(i), i.data(Qt.UserRole)) for i in selected]
                self._deleted_pages.append(batch)
                for i in selected:
                    self.takeItem(self.row(i))
                self.pages_changed.emit()
        elif action == act_rot_l:
            self.setCurrentItem(item); self.rotate_selected(-90)
        elif action == act_rot_r:
            self.setCurrentItem(item); self.rotate_selected(90)

    def _add_entry(self, entry: PageEntry) -> None:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, entry)
        self._refresh_item(item, entry)
        self.addItem(item)

    def _refresh_item(self, item: QListWidgetItem, entry: PageEntry) -> None:
        vw = self._last_vp_w or self.viewport().width()
        w  = max(80, vw)
        h  = int(w * 1.414)
        thumb = render_thumbnail(entry.doc[entry.page_num], w)
        item.setData(_PIXMAP_ROLE, thumb)
        item.setText(str(entry.page_num + 1))
        item.setSizeHint(QSize(w, h + _NUM_H + _PAD * 2))

    def _refresh_all_items(self) -> None:
        for i in range(self.count()):
            item = self.item(i)
            entry: PageEntry = item.data(Qt.UserRole)
            self._refresh_item(item, entry)


class PagePanel(QWidget):
    page_selected  = Signal(object)
    save_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
        self.setAcceptDrops(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 6)
        lay.setSpacing(4)

        _ic = QApplication.palette().color(QPalette.ButtonText).name()

        row = QHBoxLayout(); row.setSpacing(4)
        btn_open = QPushButton(_t("Apri", "Open"))
        btn_open.setIcon(qta.icon('fa5s.folder-open', color=_ic))
        btn_open.setToolTip(_t(
            "Apri file — sostituisce le pagine correnti",
            "Open file — replaces current pages",
        ))
        btn_open.clicked.connect(self.open_file)
        btn_append = QPushButton(_t("Aggiungi", "Add"))
        btn_append.setIcon(qta.icon('fa5s.file-import', color=_ic))
        btn_append.setToolTip(_t(
            "Aggiungi file in coda alle pagine esistenti",
            "Append file to existing pages",
        ))
        btn_append.clicked.connect(self.append_file)
        row.addWidget(btn_open); row.addWidget(btn_append)
        lay.addLayout(row)

        lbl = QLabel(_t("Pagine", "Pages"))
        lbl.setStyleSheet("font-size:10px;color:gray;")
        lay.addWidget(lbl)

        self._list = PageListWidget()
        self._list.currentItemChanged.connect(self._on_item_changed)
        lay.addWidget(self._list)

        hint = QLabel(_t("Trascina PDF/immagini", "Drag PDF/images here"))
        hint.setStyleSheet("color:gray;font-size:9px;")
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)

    _FILE_FILTER = "PDF e Immagini (*.pdf *.png *.jpg *.jpeg *.bmp *.tiff *.webp)"

    def open_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, _t("Apri file", "Open file"), "", self._FILE_FILTER
        )
        if paths:
            self._list.clear()
            for p in paths:
                self._load_path(p)
            if self._list.count() > 0:
                self._list.setCurrentRow(0)

    def append_file(self) -> None:
        had_selection = self._list.currentRow() >= 0
        paths, _ = QFileDialog.getOpenFileNames(
            self, _t("Aggiungi file", "Append file"), "", self._FILE_FILTER
        )
        for p in paths:
            self._load_path(p)
        if not had_selection and self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _load_path(self, path: str) -> None:
        ext = Path(path).suffix.lower()
        if ext == ".pdf":
            self._list.add_pdf(path)
        elif ext in _IMG_EXTS:
            self._list.add_image(path)

    def _on_item_changed(self, current, _previous) -> None:
        if current:
            entry: PageEntry = current.data(Qt.UserRole)
            self.page_selected.emit(entry)

    def get_pages(self) -> list[PageEntry]:
        return self._list.get_pages()

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        had_selection = self._list.currentRow() >= 0
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            ext = Path(p).suffix.lower()
            if ext == ".pdf":
                self._list.add_pdf(p)
            elif ext in _IMG_EXTS:
                self._list.add_image(p)
        e.acceptProposedAction()
        if not had_selection and self._list.count() > 0:
            self._list.setCurrentRow(0)
