from typing import Optional

import fitz

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QKeyEvent, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QScrollArea, QVBoxLayout, QWidget

from ..i18n import _t
from ..models import PageEntry, _TOOL_SHORTCUTS
from ..signatures import SignatureStore
from .ann_layer import AnnotationLayer
from .page_canvas import PageCanvas
from .sig_dialog import SignatureDialog
from .sig_picker import SignaturePicker
from .toolbar import AnnotationToolbar


BASE_DPI = 150
RENDER_DPI_CAP = 300


def _hsep() -> QFrame:
    s = QFrame()
    s.setFrameShape(QFrame.HLine)
    s.setFrameShadow(QFrame.Sunken)
    return s


class PDFViewer(QWidget):
    save_requested = Signal()
    undo_available = Signal(bool)
    redo_available = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._entry: Optional[PageEntry] = None
        self._zoom: float = 1.0
        self._dpr: float = 1.0
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._toolbar = AnnotationToolbar()
        self._toolbar.tool_changed.connect(self._on_tool)
        self._toolbar.stroke_changed.connect(
            lambda c: self._page_canvas.ann_layer.set_stroke(c)
        )
        self._toolbar.fill_changed.connect(
            lambda c: self._page_canvas.ann_layer.set_fill(c)
        )
        self._toolbar.text_color_changed.connect(
            lambda c: self._page_canvas.ann_layer.set_text_color(c)
        )
        self._toolbar.width_changed.connect(
            lambda v: self._page_canvas.ann_layer.set_line_width(v)
        )
        self._toolbar.font_size_changed.connect(
            lambda v: self._page_canvas.ann_layer.set_font_size(v)
        )
        self._toolbar.font_family_changed.connect(
            lambda f: self._page_canvas.ann_layer.set_font_family(f)
        )
        self._toolbar.zoom_in.connect(lambda: self._set_zoom(self._zoom * 1.2))
        self._toolbar.zoom_out.connect(lambda: self._set_zoom(self._zoom / 1.2))
        self._toolbar.zoom_reset.connect(lambda: self._set_zoom(1.0))
        root.addWidget(self._toolbar)
        root.addWidget(_hsep())

        self._scroll = QScrollArea()
        self._scroll.setAlignment(Qt.AlignCenter)
        self._scroll.setWidgetResizable(False)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: palette(window); }"
            "QScrollArea > QWidget { background: palette(window); }"
        )

        self._page_canvas = PageCanvas()
        self._page_canvas.ann_layer.sign_requested.connect(self._on_sign)
        self._page_canvas.ann_layer.undo_available.connect(self.undo_available)
        self._page_canvas.ann_layer.redo_available.connect(self.redo_available)
        self._scroll.setWidget(self._page_canvas)
        root.addWidget(self._scroll)

        self._toolbar.setEnabled(False)

    def load_entry(self, entry: PageEntry) -> None:
        self._flush()
        self._entry = entry
        self._page_canvas.ann_layer.reset_history()
        self._render()
        self._toolbar.setEnabled(True)

    def flush(self) -> None:
        self._flush()

    def undo(self) -> None:
        self._page_canvas.ann_layer.undo()

    def redo(self) -> None:
        self._page_canvas.ann_layer.redo()

    def scale(self) -> float:
        return (BASE_DPI * self._zoom) / 72.0

    def _flush(self) -> None:
        if self._entry is not None:
            self._entry.annotations = self._page_canvas.ann_layer.get_annotations()

    def _dpi(self) -> float:
        if self._dpr == 1.0:
            s = QApplication.primaryScreen()
            if s:
                self._dpr = s.devicePixelRatio()
        return BASE_DPI * self._zoom * self._dpr

    def _render(self) -> None:
        if not self._entry:
            return
        full_dpi = self._dpi()
        render_dpi = min(full_dpi, RENDER_DPI_CAP * self._dpr)
        mat = fitz.Matrix(render_dpi / 72, render_dpi / 72)
        pix = self._entry.doc[self._entry.page_num].get_pixmap(matrix=mat, alpha=False)
        img = QImage(
            pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888
        ).copy()
        if full_dpi > render_dpi:
            sf = full_dpi / render_dpi
            img = img.scaled(
                round(img.width() * sf), round(img.height() * sf),
                Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
            )
        pixmap = QPixmap.fromImage(img)
        pixmap.setDevicePixelRatio(self._dpr)
        self._page_canvas.load(pixmap, self.scale())
        self._page_canvas.ann_layer.set_annotations(self._entry.annotations)

    def _set_zoom(self, zoom: float) -> None:
        self._flush()
        old_scale = self.scale()
        self._zoom = max(0.25, min(4.0, zoom))
        ratio = self.scale() / old_scale
        if self._entry and ratio != 1.0:
            for ann in self._entry.annotations:
                ann.rescale(ratio)
        self._toolbar.set_zoom_label(int(self._zoom * 100))
        self._render()

    def _on_tool(self, tool) -> None:
        self._page_canvas.ann_layer.set_tool(tool)
        self._page_canvas.ann_layer.setFocus()

    def _on_sign(self) -> None:
        store = SignatureStore()
        sigs = store.load_all()
        if not sigs:
            self._create_signature(store)
        else:
            picker = SignaturePicker(store, self)
            picker.signature_selected.connect(self._page_canvas.ann_layer.add_signature)
            picker.exec()

    def _create_signature(self, store: SignatureStore) -> None:
        dlg = SignatureDialog(self)
        if dlg.exec() == QDialog.Accepted:
            px = dlg.get_pixmap()
            if px:
                store.save(px)
                self._page_canvas.ann_layer.add_signature(px)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        tool = _TOOL_SHORTCUTS.get(e.key())
        if tool and not e.modifiers():
            self._toolbar.select_tool(tool)
            self._on_tool(tool)
            return
        if e.modifiers() == Qt.ControlModifier:
            if e.key() in (Qt.Key_Equal, Qt.Key_Plus):
                self._set_zoom(self._zoom * 1.2)
            elif e.key() == Qt.Key_Minus:
                self._set_zoom(self._zoom / 1.2)
            elif e.key() == Qt.Key_0:
                self._set_zoom(1.0)
            elif e.key() == Qt.Key_S:
                self.save_requested.emit()
            elif e.key() == Qt.Key_Z:
                self.undo()
        elif e.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
            if e.key() == Qt.Key_Z:
                self.redo()
        super().keyPressEvent(e)
