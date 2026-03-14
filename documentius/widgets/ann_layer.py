import copy
from typing import Optional

from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QKeyEvent, QMouseEvent, QPaintEvent,
    QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from ..models import (
    Annotation, PenAnn, ShapeAnn, SignatureAnn, TextAnn, Tool,
)


class AnnotationLayer(QWidget):
    sign_requested = Signal()
    undo_available = Signal(bool)
    redo_available = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._tool: Tool = Tool.SELECT
        self._anns: list[Annotation] = []
        self._scale: float = 1.0
        self._selected: Optional[Annotation] = None
        self._drag_last: Optional[QPointF] = None
        self._drag_undo_pushed: bool = False
        self._resizing: bool = False
        self._drawing: bool = False
        self._draw_start: Optional[QPointF] = None
        self._pen_pts: list[QPointF] = []
        self._preview: Optional[Annotation] = None

        self._history: list[list] = []
        self._redo_stack: list[list] = []

        self._inline_editor: Optional[QLineEdit] = None
        self._inline_pt: Optional[QPointF] = None

        self.stroke: QColor = QColor(220, 50, 50)
        self.fill: QColor = QColor(0, 0, 0, 0)
        self.text_color: QColor = QColor(0, 0, 0)
        self.line_width: float = 2.0
        self.font_size: int = 14
        self.font_family: str = ""

    def _snapshot(self) -> list:
        result = []
        for ann in self._anns:
            c = copy.copy(ann)
            if isinstance(c, PenAnn):
                c.points = list(ann.points)
            result.append(c)
        return result

    def _push_undo(self) -> None:
        self._history.append(self._snapshot())
        self._redo_stack.clear()
        self.undo_available.emit(True)
        self.redo_available.emit(False)

    def reset_history(self) -> None:
        self._history.clear()
        self._redo_stack.clear()
        self.undo_available.emit(False)
        self.redo_available.emit(False)

    def undo(self) -> None:
        if not self._history:
            return
        self._redo_stack.append(self._snapshot())
        self._anns = self._history.pop()
        self._selected = None
        self.update()
        self.undo_available.emit(bool(self._history))
        self.redo_available.emit(True)

    def redo(self) -> None:
        if not self._redo_stack:
            return
        self._history.append(self._snapshot())
        self._anns = self._redo_stack.pop()
        self._selected = None
        self.update()
        self.undo_available.emit(True)
        self.redo_available.emit(bool(self._redo_stack))

    def set_stroke(self, c: QColor) -> None:
        self.stroke = QColor(c)
        if isinstance(self._selected, ShapeAnn):
            self._selected.stroke = QColor(c)
            self.update()
        elif isinstance(self._selected, PenAnn):
            self._selected.color = QColor(c)
            self.update()

    def set_fill(self, c: QColor) -> None:
        self.fill = QColor(c)
        if isinstance(self._selected, ShapeAnn):
            self._selected.fill = QColor(c)
            self.update()

    def set_text_color(self, c: QColor) -> None:
        self.text_color = QColor(c)
        if isinstance(self._selected, TextAnn):
            self._selected.color = QColor(c)
            self.update()

    def set_font_size(self, v: int) -> None:
        self.font_size = v
        if isinstance(self._selected, TextAnn):
            self._selected.font_size = v
            self.update()
        self._update_inline_style()

    def set_font_family(self, f: str) -> None:
        self.font_family = f
        if isinstance(self._selected, TextAnn):
            self._selected.font_family = f
            self.update()
        self._update_inline_style()

    def set_line_width(self, v: float) -> None:
        self.line_width = v
        if isinstance(self._selected, (ShapeAnn, PenAnn)):
            self._selected.width = v
            self.update()

    def _start_inline_text(self, pt: QPointF) -> None:
        self._finish_inline_text()

        f = QFont(self.font_family) if self.font_family else QFont()
        f.setPointSize(self.font_size)
        fm = QFontMetrics(f)

        ed = QLineEdit(self)
        ed.setFont(f)
        c = self.text_color
        ed.setStyleSheet(
            f"QLineEdit {{ background: rgba(255,255,255,40); "
            f"border: 2px solid rgba(0,120,215,200); "
            f"color: rgb({c.red()},{c.green()},{c.blue()}); "
            f"padding: 1px 4px; border-radius: 3px; }}"
        )
        ed.setMinimumWidth(120)

        ex = int(pt.x())
        ey = int(pt.y()) - fm.ascent() - 2
        ed.move(ex, ey)
        ed.resize(200, fm.height() + 4)
        ed.show()
        ed.setFocus()

        def _resize_to_content() -> None:
            if not self._inline_editor:
                return
            w = max(120, QFontMetrics(ed.font()).horizontalAdvance(ed.text()) + 24)
            ed.setFixedWidth(w)

        ed.textChanged.connect(_resize_to_content)
        ed.returnPressed.connect(self._finish_inline_text)
        ed.installEventFilter(self)

        self._inline_editor = ed
        self._inline_pt = pt

    def _finish_inline_text(self) -> None:
        ed = self._inline_editor
        if not ed:
            return
        self._inline_editor = None
        text = ed.text().strip()
        pt = self._inline_pt
        ed.hide()
        ed.deleteLater()
        if text and pt is not None:
            f = QFont(self.font_family) if self.font_family else QFont()
            f.setPointSize(self.font_size)
            fm = QFontMetrics(f)
            self._push_undo()
            self._commit(TextAnn(
                text=text,
                x=pt.x(),
                y=pt.y() - fm.ascent(),
                color=QColor(self.text_color),
                font_size=self.font_size,
                font_family=self.font_family,
            ))

    def _cancel_inline_text(self) -> None:
        ed = self._inline_editor
        if not ed:
            return
        self._inline_editor = None
        ed.hide()
        ed.deleteLater()

    def _update_inline_style(self) -> None:
        if not self._inline_editor:
            return
        f = QFont(self.font_family) if self.font_family else QFont()
        f.setPointSize(self.font_size)
        self._inline_editor.setFont(f)
        c = self.text_color
        self._inline_editor.setStyleSheet(
            f"QLineEdit {{ background: rgba(255,255,255,40); "
            f"border: 2px solid rgba(0,120,215,200); "
            f"color: rgb({c.red()},{c.green()},{c.blue()}); "
            f"padding: 1px 4px; border-radius: 3px; }}"
        )

    def eventFilter(self, obj, event) -> bool:
        if obj is self._inline_editor:
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key_Escape:
                    self._cancel_inline_text()
                    return True
            elif event.type() == QEvent.Type.FocusOut:
                self._finish_inline_text()
        return super().eventFilter(obj, event)

    def set_tool(self, tool: Tool) -> None:
        self._finish_inline_text()
        self._tool = tool
        self._cancel_drawing()
        self.setCursor(
            Qt.IBeamCursor if tool == Tool.TEXT
            else Qt.ArrowCursor if tool == Tool.SELECT
            else Qt.CrossCursor
        )

    def set_scale(self, scale: float) -> None:
        self._scale = scale

    def clear(self) -> None:
        self._cancel_inline_text()
        self._anns.clear()
        self._selected = None
        self._cancel_drawing()
        self.update()

    def get_annotations(self) -> list[Annotation]:
        self._finish_inline_text()
        return list(self._anns)

    def set_annotations(self, anns: list[Annotation]) -> None:
        self._cancel_inline_text()
        self._anns = list(anns)
        self._selected = None
        self.update()

    def add_signature(self, pixmap: QPixmap) -> None:
        w = min(200, max(60, self.width() // 4))
        h = int(w * pixmap.height() / max(pixmap.width(), 1))
        self._push_undo()
        self._commit(SignatureAnn(pixmap=pixmap, x=40.0, y=40.0, w=float(w), h=float(h)))

    def delete_selected(self) -> None:
        if self._selected and self._selected in self._anns:
            self._push_undo()
            self._anns.remove(self._selected)
            self._selected = None
            self.update()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        pt = e.position()
        if e.button() == Qt.RightButton:
            ann = self._find(pt)
            if ann:
                self._push_undo()
                self._anns.remove(ann)
                if self._selected is ann:
                    self._selected = None
                self.update()
            return
        if e.button() != Qt.LeftButton:
            return

        if self._inline_editor and not self._inline_editor.geometry().contains(pt.toPoint()):
            self._finish_inline_text()
            return

        self._drag_undo_pushed = False

        if self._tool == Tool.SELECT:
            if self._selected and self._selected._resize_handle().contains(pt):
                self._resizing = True
                self._drag_last = pt
                return
            self._resizing = False
            self._select(self._find(pt))
            self._drag_last = pt if self._selected else None

        elif self._tool == Tool.SIGN:
            self.sign_requested.emit()

        elif self._tool == Tool.TEXT:
            self._start_inline_text(pt)

        elif self._tool == Tool.PEN:
            self._drawing = True
            self._pen_pts = [pt]

        elif self._tool in (Tool.RECT, Tool.ELLIPSE, Tool.LINE, Tool.ARROW):
            self._drawing = True
            self._draw_start = pt

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        pt = e.position()
        if self._tool == Tool.SELECT and e.buttons() & Qt.LeftButton and self._drag_last:
            dx = pt.x() - self._drag_last.x()
            dy = pt.y() - self._drag_last.y()
            if self._selected:
                if not self._drag_undo_pushed:
                    self._push_undo()
                    self._drag_undo_pushed = True
                if self._resizing:
                    self._do_resize(self._selected, dx, dy)
                else:
                    self._selected.translate(dx, dy)
                self._drag_last = pt
                self.update()
        elif self._tool == Tool.PEN and self._drawing:
            self._pen_pts.append(pt)
            self.update()
        elif self._drawing and self._draw_start:
            self._preview = self._make_shape(self._draw_start, pt)
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() != Qt.LeftButton:
            return
        if self._tool == Tool.SELECT:
            self._drag_last = None
            self._drag_undo_pushed = False
        elif self._tool == Tool.PEN and self._drawing:
            if len(self._pen_pts) > 1:
                self._push_undo()
                self._commit(PenAnn(
                    points=list(self._pen_pts),
                    color=QColor(self.stroke),
                    width=self.line_width,
                ))
            self._pen_pts.clear()
            self._drawing = False
        elif self._drawing and self._draw_start:
            ann = self._make_shape(self._draw_start, e.position())
            if ann:
                self._push_undo()
                self._commit(ann)
            self._cancel_drawing()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
        elif e.key() == Qt.Key_Escape:
            self._cancel_inline_text()
            self._cancel_drawing()
            self._select(None)
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for ann in self._anns:
            ann.draw(p)
        if self._preview:
            p.setOpacity(0.6)
            self._preview.draw(p)
            p.setOpacity(1.0)
        if len(self._pen_pts) > 1:
            p.setPen(QPen(self.stroke, self.line_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for i in range(1, len(self._pen_pts)):
                p.drawLine(self._pen_pts[i - 1], self._pen_pts[i])

    def _select(self, ann: Optional[Annotation]) -> None:
        if self._selected:
            self._selected.selected = False
        self._selected = ann
        if ann:
            ann.selected = True
        self.update()

    def _find(self, pt: QPointF) -> Optional[Annotation]:
        for ann in reversed(self._anns):
            if ann.hit_test(pt):
                return ann
        return None

    def _commit(self, ann: Annotation) -> None:
        self._select(None)
        self._anns.append(ann)
        self._select(ann)
        self._drawing = False
        self._preview = None
        self.update()

    def _cancel_drawing(self) -> None:
        self._drawing = False
        self._draw_start = None
        self._pen_pts.clear()
        self._preview = None
        self.update()

    def _make_shape(self, p1: QPointF, p2: QPointF) -> Optional[ShapeAnn]:
        name = {
            Tool.RECT: "rect", Tool.ELLIPSE: "ellipse",
            Tool.LINE: "line", Tool.ARROW: "arrow",
        }.get(self._tool)
        if not name:
            return None
        return ShapeAnn(
            shape=name,
            x1=p1.x(), y1=p1.y(), x2=p2.x(), y2=p2.y(),
            stroke=QColor(self.stroke),
            fill=QColor(self.fill),
            width=self.line_width,
        )

    def _do_resize(self, ann: Annotation, dx: float, dy: float) -> None:
        shift = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
        if isinstance(ann, SignatureAnn):
            if shift:
                ratio = ann.h / max(ann.w, 1.0)
                new_w = max(20.0, ann.w + dx)
                ann.w = new_w
                ann.h = max(10.0, new_w * ratio)
            else:
                ann.w = max(20.0, ann.w + dx)
                ann.h = max(10.0, ann.h + dy)
        elif isinstance(ann, ShapeAnn):
            if shift:
                cur_w = ann.x2 - ann.x1
                cur_h = ann.y2 - ann.y1
                ratio = abs(cur_h) / max(abs(cur_w), 1.0)
                if abs(dx) >= abs(dy):
                    ann.x2 += dx
                    new_w = ann.x2 - ann.x1
                    ann.y2 = ann.y1 + abs(new_w) * ratio * (1 if cur_h >= 0 else -1)
                else:
                    ann.y2 += dy
                    new_h = ann.y2 - ann.y1
                    ann.x2 = ann.x1 + abs(new_h) / ratio * (1 if cur_w >= 0 else -1)
            else:
                ann.x2 += dx
                ann.y2 += dy
