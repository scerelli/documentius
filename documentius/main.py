import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import fitz

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QIcon, QImage
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QMainWindow, QMessageBox,
    QSplitter, QWidget,
)

from .i18n import _t
from .models import PageEntry
from .pdf_ops import export_pages
from .theme import _CleanDialogStyle, apply_dark_palette, is_dark, preferred_platform_theme
from .widgets.page_panel import PagePanel, _IMG_EXTS
from .widgets.viewer import PDFViewer


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._dirty: bool = False
        self._save_path: Optional[str] = None
        self._current_entry: Optional[PageEntry] = None
        self._can_undo_annotations: bool = False
        self.setWindowTitle("Documentius")
        self.resize(1300, 840)
        self._setup_ui()
        self._setup_menubar()
        self.statusBar().hide()
        self.setAcceptDrops(True)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        self._page_panel = PagePanel()
        self._page_panel.page_selected.connect(self._on_page_selected)

        self._viewer = PDFViewer()
        self._viewer.setFocusPolicy(Qt.StrongFocus)
        self._viewer.save_requested.connect(self._save)

        splitter.addWidget(self._page_panel)
        splitter.addWidget(self._viewer)
        splitter.setSizes([220, 1080])
        lay.addWidget(splitter)

    def _setup_menubar(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu(_t("File", "File"))

        act_open = QAction(_t("Apri…", "Open…"), self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._page_panel.open_file)
        file_menu.addAction(act_open)

        act_append = QAction(_t("Aggiungi…", "Append…"), self)
        act_append.setShortcut("Ctrl+Shift+O")
        act_append.triggered.connect(self._page_panel.append_file)
        file_menu.addAction(act_append)

        file_menu.addSeparator()

        act_save = QAction(_t("Salva", "Save"), self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self._save)
        file_menu.addAction(act_save)

        act_save_as = QAction(_t("Salva come…", "Save As…"), self)
        act_save_as.setShortcut("Ctrl+Shift+S")
        act_save_as.triggered.connect(self._save_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_print = QAction(_t("Stampa…", "Print…"), self)
        act_print.setShortcut("Ctrl+P")
        act_print.triggered.connect(self._print)
        file_menu.addAction(act_print)

        file_menu.addSeparator()

        act_quit = QAction(_t("Esci", "Quit"), self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        edit_menu = mb.addMenu(_t("Modifica", "Edit"))

        self._act_undo = QAction(_t("Annulla", "Undo"), self)
        self._act_undo.setShortcut("Ctrl+Z")
        self._act_undo.setEnabled(False)
        self._act_undo.triggered.connect(self._undo)
        edit_menu.addAction(self._act_undo)

        self._act_redo = QAction(_t("Ripristina", "Redo"), self)
        self._act_redo.setShortcut("Ctrl+Shift+Z")
        self._act_redo.setEnabled(False)
        self._act_redo.triggered.connect(self._viewer.redo)
        edit_menu.addAction(self._act_redo)

        edit_menu.addSeparator()

        act_del_ann = QAction(_t("Elimina annotazione", "Delete annotation"), self)
        act_del_ann.setShortcut("Delete")
        act_del_ann.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        act_del_ann.triggered.connect(
            lambda: self._viewer._page_canvas.ann_layer.delete_selected()
        )
        self._viewer.addAction(act_del_ann)
        edit_menu.addAction(act_del_ann)

        self._viewer.undo_available.connect(self._on_ann_undo_available)
        self._viewer.redo_available.connect(self._act_redo.setEnabled)
        self._page_panel._list.pages_changed.connect(self._on_pages_changed)

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self._update_title()

    def _mark_clean(self) -> None:
        self._dirty = False
        self._update_title()

    def _update_title(self) -> None:
        self.setWindowTitle("Documentius" + (" •" if self._dirty else ""))

    def _on_ann_undo_available(self, v: bool) -> None:
        self._can_undo_annotations = v
        self._update_undo_action()
        if v:
            self._mark_dirty()

    def _on_pages_changed(self) -> None:
        self._update_undo_action()
        self._mark_dirty()

    def _update_undo_action(self) -> None:
        self._act_undo.setEnabled(
            self._can_undo_annotations or self._page_panel._list.can_undo_page_delete()
        )

    def _undo(self) -> None:
        if self._can_undo_annotations:
            self._viewer.undo()
        else:
            self._page_panel._list.undo_last_delete()

    def _on_page_selected(self, entry: PageEntry) -> None:
        self._viewer.flush()
        self._current_entry = entry
        self._viewer.load_entry(entry)

    def _save(self) -> bool:
        if self._save_path:
            return self._do_save(self._save_path)
        return self._first_save()

    def _first_save(self) -> bool:
        pages = self._page_panel.get_pages()
        if not pages:
            QMessageBox.information(
                self, "Documentius",
                _t("Nessuna pagina da salvare.", "No pages to save."),
            )
            return False

        source_paths = {p.source_path for p in pages}

        if len(source_paths) == 1:
            original = list(source_paths)[0]
            box = QMessageBox(self)
            box.setWindowTitle(_t("Salva PDF", "Save PDF"))
            box.setText(
                _t(
                    f"Vuoi sovrascrivere il file originale?\n{original}",
                    f"Overwrite the original file?\n{original}",
                )
            )
            btn_overwrite = box.addButton(
                _t("Sovrascrivi originale", "Overwrite original"), QMessageBox.AcceptRole
            )
            btn_copy = box.addButton(
                _t("Salva come copia…", "Save as copy…"), QMessageBox.ActionRole
            )
            box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(btn_copy)
            box.exec()
            clicked = box.clickedButton()
            if clicked == btn_overwrite:
                if self._do_save(original):
                    self._save_path = original
                    return True
                return False
            elif clicked == btn_copy:
                return self._save_as()
            else:
                return False
        else:
            return self._save_as()

    def _save_as(self) -> bool:
        pages = self._page_panel.get_pages()
        if not pages:
            QMessageBox.information(
                self, "Documentius",
                _t("Nessuna pagina da salvare.", "No pages to save."),
            )
            return False
        stem = Path(pages[0].source_path).stem
        default_name = stem + _t("_firmato.pdf", "_signed.pdf")
        default_path = str(Path(pages[0].source_path).with_name(default_name))
        save_path, _ = QFileDialog.getSaveFileName(
            self, _t("Salva PDF come", "Save PDF As"), default_path, "PDF (*.pdf)"
        )
        if not save_path:
            return False
        if self._do_save(save_path):
            self._save_path = save_path
            return True
        return False

    def _do_save(self, path: str) -> bool:
        self._viewer.flush()
        pages = self._page_panel.get_pages()
        try:
            export_pages(pages, path, self._viewer.scale())
            self._mark_clean()
            return True
        except Exception as exc:
            QMessageBox.critical(
                self,
                _t("Errore", "Error"),
                _t(f"Salvataggio fallito:\n{exc}", f"Save failed:\n{exc}"),
            )
            return False

    def _print(self) -> None:
        try:
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError:
            QMessageBox.warning(
                self, "Documentius",
                _t(
                    "Il modulo di stampa non è disponibile.",
                    "The print module is not available.",
                ),
            )
            return

        from PySide6.QtGui import QPainter

        pages = self._page_panel.get_pages()
        if not pages:
            QMessageBox.information(
                self, "Documentius",
                _t("Nessuna pagina da stampare.", "No pages to print."),
            )
            return

        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QPrintDialog.Accepted:
            return

        self._viewer.flush()

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                tmp_path = f.name

            export_pages(pages, tmp_path, self._viewer.scale())

            doc = fitz.open(tmp_path)
            painter = QPainter(printer)

            page_rect = printer.pageRect(QPrinter.DevicePixel).toRect()
            dpi = printer.resolution()

            for i, page in enumerate(doc):
                if i > 0:
                    printer.newPage()
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = QImage(
                    pix.samples, pix.width, pix.height, pix.stride,
                    QImage.Format_RGB888,
                ).copy()
                painter.drawImage(page_rect, img)

            painter.end()
            doc.close()

        except Exception as exc:
            QMessageBox.critical(
                self,
                _t("Errore", "Error"),
                _t(f"Stampa fallita:\n{exc}", f"Print failed:\n{exc}"),
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def closeEvent(self, event) -> None:
        if self._dirty:
            ret = QMessageBox.question(
                self,
                "Documentius",
                _t(
                    "Ci sono modifiche non salvate.\nSalvare prima di uscire?",
                    "There are unsaved changes.\nSave before quitting?",
                ),
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if ret == QMessageBox.Save:
                if not self._save():
                    event.ignore()
                    return
            elif ret == QMessageBox.Cancel:
                event.ignore()
                return
        event.accept()

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            ext = Path(p).suffix.lower()
            if ext == ".pdf":
                self._page_panel._list.add_pdf(p)
            elif ext in _IMG_EXTS:
                self._page_panel._list.add_image(p)


_APP_ID = "io.github.scerelli.Documentius"


def _app_icon() -> QIcon:
    icon = QIcon.fromTheme(_APP_ID)
    if not icon.isNull():
        return icon
    svg = Path(__file__).resolve().parent.parent / "data" / "icons" / "documentius.svg"
    if svg.exists():
        return QIcon(str(svg))
    return QIcon()


def main() -> None:
    theme = preferred_platform_theme()
    if theme:
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", theme)

    app = QApplication(sys.argv)
    app.setApplicationName("Documentius")
    app.setDesktopFileName(_APP_ID)
    app.setWindowIcon(_app_icon())
    if is_dark(app):
        apply_dark_palette(app)
    app.setStyle(_CleanDialogStyle())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
