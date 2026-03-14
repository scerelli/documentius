import math
import os
import tempfile

import fitz

from PySide6.QtGui import QImage, QPixmap

from .models import Annotation, PageEntry, PenAnn, ShapeAnn, SignatureAnn, TextAnn


def render_thumbnail(fitz_page: fitz.Page, width: int = 100) -> QPixmap:
    r = fitz_page.rect
    scale = width / max(r.width, 1)
    pix = fitz_page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    img = QImage(
        pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888
    ).copy()
    return QPixmap.fromImage(img)


def export_pages(pages: list[PageEntry], dst: str, scale: float) -> None:
    out = fitz.open()
    for entry in pages:
        out.insert_pdf(entry.doc, from_page=entry.page_num, to_page=entry.page_num)
        if entry.annotations:
            _apply_anns_to_page(out[-1], entry.annotations, scale)
    out.save(dst, garbage=4, deflate=True)
    out.close()


def _apply_anns_to_page(
    page: fitz.Page, anns: list[Annotation], scale: float
) -> None:
    shape = page.new_shape()
    for ann in anns:
        if isinstance(ann, SignatureAnn):
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            try:
                ann.pixmap.save(tmp.name, "PNG")
                page.insert_image(
                    fitz.Rect(
                        ann.x / scale, ann.y / scale,
                        (ann.x + ann.w) / scale, (ann.y + ann.h) / scale,
                    ),
                    filename=tmp.name,
                    overlay=True,
                )
            finally:
                os.unlink(tmp.name)

        elif isinstance(ann, TextAnn):
            c = (ann.color.redF(), ann.color.greenF(), ann.color.blueF())
            for i, line in enumerate(ann.text.splitlines() or [""]):
                page.insert_text(
                    fitz.Point(ann.x / scale, (ann.y + ann.font_size * (i + 1)) / scale),
                    line,
                    fontsize=ann.font_size,
                    color=c,
                )

        elif isinstance(ann, PenAnn):
            if len(ann.points) < 2:
                continue
            pts = [fitz.Point(q.x() / scale, q.y() / scale) for q in ann.points]
            c = (ann.color.redF(), ann.color.greenF(), ann.color.blueF())
            shape.draw_polyline(pts)
            shape.finish(color=c, width=max(0.5, ann.width / scale), closePath=False)

        elif isinstance(ann, ShapeAnn):
            x1, y1 = ann.x1 / scale, ann.y1 / scale
            x2, y2 = ann.x2 / scale, ann.y2 / scale
            sc = (ann.stroke.redF(), ann.stroke.greenF(), ann.stroke.blueF())
            fl = (
                (ann.fill.redF(), ann.fill.greenF(), ann.fill.blueF())
                if ann.fill.alpha() > 0 else None
            )
            fo = ann.fill.alphaF() if fl else 0.0
            w = max(0.5, ann.width / scale)

            if ann.shape == "rect":
                shape.draw_rect(fitz.Rect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
                shape.finish(color=sc, fill=fl, fill_opacity=fo, width=w)
            elif ann.shape == "ellipse":
                shape.draw_oval(fitz.Rect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
                shape.finish(color=sc, fill=fl, fill_opacity=fo, width=w)
            elif ann.shape in ("line", "arrow"):
                shape.draw_line(fitz.Point(x1, y1), fitz.Point(x2, y2))
                shape.finish(color=sc, width=w)
                if ann.shape == "arrow":
                    dx, dy = x2 - x1, y2 - y1
                    if dx != 0 or dy != 0:
                        ang = math.atan2(dy, dx); L, a = 8.0, math.pi / 6
                        shape.draw_line(
                            fitz.Point(x2, y2),
                            fitz.Point(x2 - L * math.cos(ang - a), y2 - L * math.sin(ang - a)),
                        )
                        shape.finish(color=sc, width=w)
                        shape.draw_line(
                            fitz.Point(x2, y2),
                            fitz.Point(x2 - L * math.cos(ang + a), y2 - L * math.sin(ang + a)),
                        )
                        shape.finish(color=sc, width=w)
    shape.commit()
