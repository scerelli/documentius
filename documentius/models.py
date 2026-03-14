import math
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QIcon, QPainter, QPen, QPixmap,
)


class Tool(Enum):
    SELECT  = auto()
    SIGN    = auto()
    TEXT    = auto()
    PEN     = auto()
    RECT    = auto()
    ELLIPSE = auto()
    LINE    = auto()
    ARROW   = auto()


_TOOL_SHORTCUTS: dict[int, Tool] = {
    Qt.Key_V: Tool.SELECT,  Qt.Key_F: Tool.SIGN,
    Qt.Key_T: Tool.TEXT,    Qt.Key_P: Tool.PEN,
    Qt.Key_R: Tool.RECT,    Qt.Key_E: Tool.ELLIPSE,
    Qt.Key_L: Tool.LINE,    Qt.Key_A: Tool.ARROW,
}


HANDLE_PX = 9


class Annotation:
    selected: bool = False

    def draw(self, p: QPainter) -> None: ...
    def hit_test(self, pt: QPointF, margin: float = 6.0) -> bool: ...
    def translate(self, dx: float, dy: float) -> None: ...
    def bounding_rect(self) -> QRectF: ...
    def rescale(self, ratio: float) -> None: ...

    def _resize_handle(self) -> QRectF:
        br = self.bounding_rect().adjusted(-3, -3, 3, 3)
        s = float(HANDLE_PX)
        return QRectF(br.right() - s / 2, br.bottom() - s / 2, s, s)

    def _draw_selection(self, p: QPainter) -> None:
        if not self.selected:
            return
        br = self.bounding_rect()
        p.save()
        p.setPen(QPen(QColor(0, 120, 212), 1.5, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(br.adjusted(-3, -3, 3, 3))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 120, 212))
        p.drawRect(self._resize_handle())
        p.restore()


@dataclass
class SignatureAnn(Annotation):
    pixmap: QPixmap
    x: float; y: float; w: float; h: float

    def draw(self, p: QPainter) -> None:
        scaled = self.pixmap.scaled(
            int(self.w), int(self.h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        )
        p.drawPixmap(int(self.x), int(self.y), scaled)
        self._draw_selection(p)

    def hit_test(self, pt: QPointF, margin: float = 6.0) -> bool:
        return self.bounding_rect().adjusted(-margin, -margin, margin, margin).contains(pt)

    def translate(self, dx: float, dy: float) -> None:
        self.x += dx; self.y += dy

    def rescale(self, ratio: float) -> None:
        self.x *= ratio; self.y *= ratio; self.w *= ratio; self.h *= ratio

    def bounding_rect(self) -> QRectF:
        return QRectF(self.x, self.y, self.w, self.h)


@dataclass
class TextAnn(Annotation):
    text: str
    x: float; y: float
    color: QColor
    font_size: int
    font_family: str = ""

    def _font(self) -> QFont:
        f = QFont(self.font_family) if self.font_family else QFont()
        f.setPointSize(self.font_size)
        return f

    def draw(self, p: QPainter) -> None:
        p.save()
        f = self._font(); p.setFont(f); p.setPen(self.color)
        lh = QFontMetrics(f).height()
        for i, line in enumerate(self.text.splitlines() or [""]):
            p.drawText(QPointF(self.x, self.y + (i + 1) * lh), line)
        self._draw_selection(p)
        p.restore()

    def hit_test(self, pt: QPointF, margin: float = 6.0) -> bool:
        return self.bounding_rect().adjusted(-margin, -margin, margin, margin).contains(pt)

    def translate(self, dx: float, dy: float) -> None:
        self.x += dx; self.y += dy

    def rescale(self, ratio: float) -> None:
        self.x *= ratio; self.y *= ratio

    def bounding_rect(self) -> QRectF:
        fm = QFontMetrics(self._font())
        lines = self.text.splitlines() or [""]
        w = max((fm.horizontalAdvance(l) for l in lines), default=1)
        return QRectF(self.x, self.y, float(w), float(fm.height() * len(lines)))


@dataclass
class PenAnn(Annotation):
    points: list; color: QColor; width: float

    def draw(self, p: QPainter) -> None:
        if len(self.points) < 2:
            return
        p.save(); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self.color, self.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for i in range(1, len(self.points)):
            p.drawLine(self.points[i - 1], self.points[i])
        self._draw_selection(p)
        p.restore()

    def hit_test(self, pt: QPointF, margin: float = 6.0) -> bool:
        if not self.bounding_rect().adjusted(-20, -20, 20, 20).contains(pt):
            return False
        thresh = margin + self.width / 2
        for i in range(1, len(self.points)):
            if _pt_seg_dist(pt, self.points[i - 1], self.points[i]) < thresh:
                return True
        return False

    def translate(self, dx: float, dy: float) -> None:
        self.points = [QPointF(q.x() + dx, q.y() + dy) for q in self.points]

    def rescale(self, ratio: float) -> None:
        self.points = [QPointF(q.x() * ratio, q.y() * ratio) for q in self.points]
        self.width *= ratio

    def bounding_rect(self) -> QRectF:
        if not self.points:
            return QRectF()
        xs = [q.x() for q in self.points]; ys = [q.y() for q in self.points]
        return QRectF(min(xs), min(ys), max(xs) - min(xs) or 1, max(ys) - min(ys) or 1)


@dataclass
class ShapeAnn(Annotation):
    shape: str
    x1: float; y1: float; x2: float; y2: float
    stroke: QColor; fill: QColor; width: float

    def draw(self, p: QPainter) -> None:
        p.save(); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self.stroke, self.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QBrush(self.fill) if self.fill.alpha() > 0 else Qt.NoBrush)
        r = QRectF(
            min(self.x1, self.x2), min(self.y1, self.y2),
            abs(self.x2 - self.x1) or 1, abs(self.y2 - self.y1) or 1,
        )
        if self.shape == "rect":
            p.drawRect(r)
        elif self.shape == "ellipse":
            p.drawEllipse(r)
        elif self.shape == "line":
            p.drawLine(QPointF(self.x1, self.y1), QPointF(self.x2, self.y2))
        elif self.shape == "arrow":
            _draw_arrow(p, self.x1, self.y1, self.x2, self.y2)
        self._draw_selection(p)
        p.restore()

    def hit_test(self, pt: QPointF, margin: float = 6.0) -> bool:
        return self.bounding_rect().adjusted(-margin, -margin, margin, margin).contains(pt)

    def translate(self, dx: float, dy: float) -> None:
        self.x1 += dx; self.y1 += dy; self.x2 += dx; self.y2 += dy

    def rescale(self, ratio: float) -> None:
        self.x1 *= ratio; self.y1 *= ratio; self.x2 *= ratio; self.y2 *= ratio
        self.width *= ratio

    def bounding_rect(self) -> QRectF:
        return QRectF(
            min(self.x1, self.x2), min(self.y1, self.y2),
            abs(self.x2 - self.x1) or 1, abs(self.y2 - self.y1) or 1,
        )


def _pt_seg_dist(pt: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    if dx == 0 and dy == 0:
        return math.hypot(pt.x() - a.x(), pt.y() - a.y())
    t = max(0.0, min(1.0, ((pt.x() - a.x()) * dx + (pt.y() - a.y()) * dy) / (dx * dx + dy * dy)))
    return math.hypot(pt.x() - a.x() - t * dx, pt.y() - a.y() - t * dy)


def _draw_arrow(p: QPainter, x1: float, y1: float, x2: float, y2: float) -> None:
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return
    angle = math.atan2(dy, dx); L, a = 14.0, math.pi / 6
    p.drawLine(QPointF(x2, y2), QPointF(x2 - L * math.cos(angle - a), y2 - L * math.sin(angle - a)))
    p.drawLine(QPointF(x2, y2), QPointF(x2 - L * math.cos(angle + a), y2 - L * math.sin(angle + a)))


import fitz  # noqa: E402


@dataclass
class PageEntry:
    doc: fitz.Document
    page_num: int
    source_path: str
    annotations: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{Path(self.source_path).stem}\np. {self.page_num + 1}"
