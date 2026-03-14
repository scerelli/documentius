import os
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle


class _CleanDialogStyle(QProxyStyle):

    _STRIP = frozenset({
        QStyle.SP_DialogOkButton,
        QStyle.SP_DialogCancelButton,
        QStyle.SP_DialogHelpButton,
        QStyle.SP_DialogOpenButton,
        QStyle.SP_DialogSaveButton,
        QStyle.SP_DialogCloseButton,
        QStyle.SP_DialogApplyButton,
        QStyle.SP_DialogResetButton,
        QStyle.SP_DialogDiscardButton,
        QStyle.SP_DialogYesButton,
        QStyle.SP_DialogNoButton,
        QStyle.SP_DialogAbortButton,
        QStyle.SP_DialogRetryButton,
        QStyle.SP_DialogIgnoreButton,
    })

    def standardIcon(self, standardIcon, option=None, widget=None):
        if standardIcon in self._STRIP:
            return QIcon()
        return super().standardIcon(standardIcon, option, widget)


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=2
        ).stdout.lower()
    except Exception:
        return ""


def _portal_is_dark() -> bool | None:
    try:
        out = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.freedesktop.portal.Desktop",
             "--object-path", "/org/freedesktop/portal/desktop",
             "--method", "org.freedesktop.portal.Settings.Read",
             "org.freedesktop.appearance", "color-scheme"],
            capture_output=True, text=True, timeout=2,
        ).stdout
        import re
        m = re.search(r"uint32 (\d+)", out)
        if m:
            v = int(m.group(1))
            if v == 1:
                return True
            if v == 2:
                return False
    except Exception:
        pass
    return None


def is_dark(app: QApplication) -> bool:
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False

    portal = _portal_is_dark()
    if portal is not None:
        return portal

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    if "kde" in desktop:
        out = _run(["kreadconfig5", "--file", "kdeglobals",
                    "--group", "General", "--key", "ColorScheme"])
        if out:
            return "dark" in out
        try:
            with open(os.path.expanduser("~/.config/kdeglobals")) as f:
                for line in f:
                    if "colorscheme" in line.lower() and "dark" in line.lower():
                        return True
        except OSError:
            pass

    for cmd in (
        ["dconf", "read", "/org/gnome/desktop/interface/color-scheme"],
        ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
        ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
    ):
        if "dark" in _run(cmd):
            return True

    if "dark" in os.environ.get("GTK_THEME", "").lower():
        return True

    return False


def preferred_platform_theme() -> str | None:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" in desktop or "unity" in desktop:
        return "gnome"
    if os.environ.get("GNOME_DESKTOP_SESSION_ID"):
        return "gnome"
    return None


def apply_dark_palette(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()
    dark, darker = QColor(45, 45, 45), QColor(30, 30, 30)
    text = QColor(220, 220, 220)
    accent = QColor(42, 130, 218)
    dis = QColor(110, 110, 110)
    p.setColor(QPalette.Window,          dark)
    p.setColor(QPalette.WindowText,      text)
    p.setColor(QPalette.Base,            darker)
    p.setColor(QPalette.AlternateBase,   dark)
    p.setColor(QPalette.ToolTipBase,     dark)
    p.setColor(QPalette.ToolTipText,     text)
    p.setColor(QPalette.Text,            text)
    p.setColor(QPalette.Button,          dark)
    p.setColor(QPalette.ButtonText,      text)
    p.setColor(QPalette.BrightText,      QColor(255, 80, 80))
    p.setColor(QPalette.Link,            accent)
    p.setColor(QPalette.Highlight,       accent)
    p.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    p.setColor(QPalette.Disabled, QPalette.WindowText, dis)
    p.setColor(QPalette.Disabled, QPalette.Text,       dis)
    p.setColor(QPalette.Disabled, QPalette.ButtonText, dis)
    app.setPalette(p)
