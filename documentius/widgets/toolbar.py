from typing import Optional

import qtawesome as qta

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QColorDialog, QFontComboBox, QFrame,
    QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox, QWidget,
)

from ..i18n import _t
from ..models import Tool


_TOOL_DEFS = [
    (Tool.SELECT,  'fa5s.mouse-pointer',        '↖', _t("Seleziona/sposta  (V)", "Select/move  (V)")),
    None,
    (Tool.SIGN,    'fa5s.signature',            '✒', _t("Firma  (F)",       "Signature  (F)")),
    (Tool.TEXT,    'fa5s.font',                 'A', _t("Testo  (T)",        "Text  (T)")),
    None,
    (Tool.PEN,     'fa5s.pencil-alt',           '✏', _t("Penna libera  (P)", "Freehand pen  (P)")),
    (Tool.RECT,    'fa5r.square',               '□', _t("Rettangolo  (R)",   "Rectangle  (R)")),
    (Tool.ELLIPSE, 'fa5r.circle',               '○', _t("Ellisse  (E)",      "Ellipse  (E)")),
    (Tool.LINE,    'fa5s.minus',                '╱', _t("Linea  (L)",        "Line  (L)")),
    (Tool.ARROW,   'fa5s.arrow-right',          '↗', _t("Freccia  (A)",      "Arrow  (A)")),
]


def _qta(name: str, size: int = 16) -> QIcon:
    pal = QApplication.palette()
    normal   = pal.color(QPalette.Normal,   QPalette.ButtonText).name()
    disabled = pal.color(QPalette.Disabled, QPalette.ButtonText).name()
    try:
        return qta.icon(name, color=normal, color_disabled=disabled)
    except Exception:
        return QIcon()


class ColorSwatch(QPushButton):
    color_changed = Signal(QColor)

    def __init__(self, color: QColor, tip: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setToolTip(tip)
        self.setFixedSize(26, 26)
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self) -> QColor:
        return self._color

    def set_color(self, c: QColor) -> None:
        self._color = c
        self._refresh()

    def _pick(self) -> None:
        start = QColor(self._color)
        if start.alpha() == 0:
            start.setAlpha(200)

        dlg = QColorDialog(start, self)
        dlg.setOptions(QColorDialog.ShowAlphaChannel)

        pal = QApplication.palette()
        bg = pal.color(QPalette.Button)
        fg = pal.color(QPalette.ButtonText)
        mid = pal.color(QPalette.Mid)
        btn_style = (
            f"QPushButton {{ background: rgb({bg.red()},{bg.green()},{bg.blue()}); "
            f"color: rgb({fg.red()},{fg.green()},{fg.blue()}); "
            f"border: 1px solid rgb({mid.red()},{mid.green()},{mid.blue()}); "
            f"padding: 4px 14px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: rgb({min(bg.red()+15,255)},"
            f"{min(bg.green()+15,255)},{min(bg.blue()+15,255)}); }}"
        )
        for btn in dlg.findChildren(QPushButton):
            btn.setStyleSheet(btn_style)

        if dlg.exec():
            c = dlg.currentColor()
            if c.isValid():
                self._color = c
                self._refresh()
                self.color_changed.emit(c)

    def _refresh(self) -> None:
        r, g, b, a = (
            self._color.red(), self._color.green(),
            self._color.blue(), self._color.alpha(),
        )
        if a == 0:
            self.setStyleSheet(
                "QPushButton{"
                "background: qlineargradient("
                "x1:0,y1:0,x2:1,y2:1,"
                "stop:0 #ccc, stop:0.5 #ccc,"
                "stop:0.5 #fff, stop:1 #fff);"
                "border:1px solid #888;border-radius:4px;}"
            )
        else:
            self.setStyleSheet(
                f"QPushButton{{background:rgba({r},{g},{b},{a});"
                "border:1px solid #888;border-radius:4px;}"
            )


def _vsep() -> QFrame:
    s = QFrame()
    s.setFrameShape(QFrame.VLine)
    s.setFrameShadow(QFrame.Sunken)
    return s


class AnnotationToolbar(QWidget):
    tool_changed        = Signal(Tool)
    stroke_changed      = Signal(QColor)
    fill_changed        = Signal(QColor)
    text_color_changed  = Signal(QColor)
    width_changed       = Signal(float)
    font_size_changed   = Signal(int)
    font_family_changed = Signal(str)
    zoom_in             = Signal()
    zoom_out            = Signal()
    zoom_reset          = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._btns: dict[Tool, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        pal = QApplication.palette()
        accent = pal.color(QPalette.Highlight)
        ac = f"rgba({accent.red()},{accent.green()},{accent.blue()},210)"
        txt = pal.color(QPalette.ButtonText)
        tc = f"rgb({txt.red()},{txt.green()},{txt.blue()})"
        tool_style = (
            f"QPushButton{{border:1px solid transparent;border-radius:5px;"
            f"padding:2px;min-width:28px;min-height:26px;color:{tc};}}"
            "QPushButton:hover{border-color:#888;}"
            f"QPushButton:checked{{background:{ac};border-color:transparent;}}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(2)

        for item in _TOOL_DEFS:
            if item is None:
                lay.addSpacing(2)
                lay.addWidget(_vsep())
                lay.addSpacing(2)
                continue
            tool, qta_name, fallback, tip = item
            btn = QPushButton()
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setStyleSheet(tool_style)
            btn.setFixedSize(30, 28)
            icon = _qta(qta_name)
            if not icon.isNull():
                btn.setIcon(icon)
                btn.setIconSize(QSize(16, 16))
            else:
                btn.setText(fallback)
            btn.clicked.connect(lambda _c, t=tool: self.tool_changed.emit(t))
            self._btns[tool] = btn
            self._group.addButton(btn)
            lay.addWidget(btn)

        lay.addSpacing(4)
        lay.addWidget(_vsep())
        lay.addSpacing(4)

        lay.addWidget(QLabel(_t("Font:", "Font:")))
        self._font_combo = QFontComboBox()
        self._font_combo.setMaximumWidth(150)
        self._font_combo.setToolTip(_t("Famiglia carattere", "Font family"))
        self._font_combo.currentFontChanged.connect(
            lambda f: self.font_family_changed.emit(f.family())
        )
        lay.addWidget(self._font_combo)
        lay.addSpacing(2)

        spn = QSpinBox()
        spn.setRange(6, 120)
        spn.setValue(14)
        spn.setMaximumWidth(48)
        spn.setToolTip(_t("Dimensione testo", "Text size"))
        spn.valueChanged.connect(self.font_size_changed)
        lay.addWidget(spn)

        lay.addSpacing(2)
        self._sw_text_color = ColorSwatch(QColor(0, 0, 0), _t("Colore testo", "Text color"))
        self._sw_text_color.color_changed.connect(self.text_color_changed)
        lay.addWidget(self._sw_text_color)

        lay.addSpacing(4)
        lay.addWidget(_vsep())
        lay.addSpacing(4)

        lay.addWidget(QLabel(_t("Bordo:", "Stroke:")))
        self._sw_stroke = ColorSwatch(QColor(220, 50, 50), _t("Colore bordo/penna", "Stroke/pen color"))
        self._sw_stroke.color_changed.connect(self.stroke_changed)
        lay.addWidget(self._sw_stroke)

        lay.addSpacing(4)
        lay.addWidget(QLabel(_t("Fill:", "Fill:")))
        self._sw_fill = ColorSwatch(QColor(0, 0, 0, 0), _t("Riempimento", "Fill"))
        self._sw_fill.color_changed.connect(self.fill_changed)
        lay.addWidget(self._sw_fill)

        lay.addSpacing(4)
        lay.addWidget(QLabel(_t("Sp.:", "W:")))
        sld = QSlider(Qt.Horizontal)
        sld.setRange(1, 20)
        sld.setValue(2)
        sld.setMaximumWidth(70)
        sld.setToolTip(_t("Spessore linea", "Line width"))
        self._lbl_width = QLabel("2 px")
        self._lbl_width.setMinimumWidth(30)

        def _on_width(v: int) -> None:
            self._lbl_width.setText(f"{v} px")
            self.width_changed.emit(float(v))

        sld.valueChanged.connect(_on_width)
        lay.addWidget(sld)
        lay.addWidget(self._lbl_width)

        lay.addStretch()
        lay.addWidget(_vsep())
        lay.addSpacing(4)

        bzo = QPushButton()
        bzo.setIcon(_qta('fa5s.search-minus'))
        bzo.setIconSize(QSize(14, 14))
        bzo.setFixedSize(26, 26)
        bzo.setToolTip(_t("Riduci zoom  (Ctrl −)", "Zoom out  (Ctrl −)"))
        bzo.setStyleSheet("QPushButton{border:1px solid transparent;border-radius:4px;}"
                          "QPushButton:hover{border-color:#888;}")
        bzo.clicked.connect(self.zoom_out)
        lay.addWidget(bzo)

        self._lbl_zoom = QLabel("100%")
        self._lbl_zoom.setMinimumWidth(38)
        self._lbl_zoom.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._lbl_zoom)

        bzi = QPushButton()
        bzi.setIcon(_qta('fa5s.search-plus'))
        bzi.setIconSize(QSize(14, 14))
        bzi.setFixedSize(26, 26)
        bzi.setToolTip(_t("Aumenta zoom  (Ctrl +)", "Zoom in  (Ctrl +)"))
        bzi.setStyleSheet("QPushButton{border:1px solid transparent;border-radius:4px;}"
                          "QPushButton:hover{border-color:#888;}")
        bzi.clicked.connect(self.zoom_in)
        lay.addWidget(bzi)

        self._btns[Tool.SELECT].setChecked(True)

    def set_zoom_label(self, pct: int) -> None:
        self._lbl_zoom.setText(f"{pct}%")

    def select_tool(self, tool: Tool) -> None:
        if tool in self._btns:
            self._btns[tool].setChecked(True)
