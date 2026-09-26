"""
Standalone PySide6 entry point for the fullscreen boot/hand-off overlay,
launched as its own OS process by boot_overlay_qt.py's show(), the same
way the PowerShell+WinForms version it replaces (bridge/boot_overlay.py)
already was. Kept as a separate process rather than an in-process QWidget
for the same reason as before: start_iisu_pc.py is a synchronous script
that may not be running inside any QApplication at all, and manager.py
calls show()/close() from background threads, an in-process widget
would reintroduce the "second GUI root from a non-owning thread" problem
this design exists to avoid.

Usage: python -m bridge.ui.boot_overlay_app <context> [flavor]
"""

import math
import sys

try:
    import winreg
except ImportError:
    winreg = None

import bridge.ui  # noqa: F401; import-time side effect: puts root/bridge/installer on sys.path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

# Same brand gradient used elsewhere (shared/qt_theme.py's GRADIENT_STOPS),
# kept in sync by eye since this overlay is a standalone process with
# its own tiny theme, not a consumer of that module.
_GRADIENT_HEX = ["#71e0ff", "#68ccff", "#5e84ff", "#8258fa", "#c56eff"]

_THEMES = {
    "dark": {
        "bg": QColor(4, 4, 6),
        "title": QColor("#5e84ff"),
        "context": QColor(240, 240, 245),
        "flavor": QColor(140, 140, 150),
        "track": QColor(40, 40, 44),
        "gradient_alpha": 40,
    },
    "light": {
        "bg": QColor(250, 250, 252),
        "title": QColor("#3a5ac4"),
        "context": QColor(28, 28, 34),
        "flavor": QColor(108, 108, 120),
        "track": QColor(222, 224, 232),
        "gradient_alpha": 110,
    },
}


def _detect_windows_theme() -> str:
    """Reads the same registry value Windows' own Settings > Colors page
    ("Choose your default app mode") writes, best-effort, since a
    loading screen guessing wrong about system theme is purely cosmetic,
    never worth failing the boot sequence over."""
    if winreg is None:
        return "dark"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value else "dark"
    except (OSError, AttributeError):
        return "dark"


class _AnimatedBackground(QWidget):
    """A slow-rotating, low-alpha linear gradient laid over a flat theme
    background, subtle by design (the brand gradient at ~20% opacity,
    ticking a few degrees a second) rather than a full-strength moving
    rainbow, which would fight with the text sitting on top of it."""

    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._angle = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def _tick(self) -> None:
        self._angle = (self._angle + 0.3) % 360.0
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._theme["bg"])

        rad = math.radians(self._angle)
        cx, cy = self.width() / 2, self.height() / 2
        radius = math.hypot(cx, cy)
        x1, y1 = cx + radius * math.cos(rad), cy + radius * math.sin(rad)
        x2, y2 = cx - radius * math.cos(rad), cy - radius * math.sin(rad)

        gradient = QLinearGradient(x1, y1, x2, y2)
        alpha = self._theme["gradient_alpha"]
        stop_count = len(_GRADIENT_HEX)
        for i, hex_color in enumerate(_GRADIENT_HEX):
            color = QColor(hex_color)
            color.setAlpha(alpha)
            gradient.setColorAt(i / (stop_count - 1), color)
        painter.fillRect(self.rect(), gradient)


class _BounceBar(QWidget):
    """A small filled rectangle bouncing back and forth across a track,
    Qt has no built-in "indeterminate" progress style that looks like this,
    so it's hand-painted the same way the original WinForms Panel-in-a-
    Panel + Timer version was."""

    def __init__(self, theme: dict, parent=None, width: int = 320, height: int = 4, fill_width: int = 90):
        super().__init__(parent)
        self._theme = theme
        self._track_width = width
        self._fill_width = fill_width
        self.setFixedSize(width, height)
        self._x = 0
        self._direction = 1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(12)

    def _tick(self) -> None:
        max_x = self._track_width - self._fill_width
        new_x = self._x + 3 * self._direction
        if new_x <= 0:
            new_x, self._direction = 0, 1
        elif new_x >= max_x:
            new_x, self._direction = max_x, -1
        self._x = new_x
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._theme["track"])
        painter.fillRect(self._x, 0, self._fill_width, self.height(), self._theme["title"])


class OverlayWindow(QWidget):
    _TITLE_TEXT = "iiSU-PC Starting"

    def __init__(self, context: str, flavor: str):
        super().__init__()
        theme = _THEMES[_detect_windows_theme()]

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("overlayRoot")
        self.setStyleSheet("#overlayRoot { background: transparent; }")

        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.geometry() if screen else None

        card_width = 520
        card_height = 240
        self.resize(card_width, card_height)
        if screen_geo:
            self.move(
                screen_geo.x() + (screen_geo.width() - card_width) // 2,
                screen_geo.y() + (screen_geo.height() - card_height) // 2,
            )

        card = QWidget(self)
        card.setObjectName("overlayCard")
        card_bg = "rgba(18, 18, 24, 235)" if _detect_windows_theme() == "dark" else "rgba(245, 245, 250, 235)"
        card_border = "rgba(255, 255, 255, 35)" if _detect_windows_theme() == "dark" else "rgba(0, 0, 0, 35)"
        card.setStyleSheet(f"""
            #overlayCard {{
                background-color: {card_bg};
                border: 1px solid {card_border};
                border-radius: 20px;
            }}
        """)
        card.setGeometry(0, 0, card_width, card_height)

        layout = QVBoxLayout(card)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)
        layout.setContentsMargins(36, 28, 36, 28)

        self._title = QLabel(self._TITLE_TEXT)
        self._title.setFont(QFont("Bahnschrift SemiBold", 24))
        self._title.setStyleSheet(f"color: {theme['title'].name()}; background: transparent;")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)

        context_label = QLabel(context)
        context_label.setFont(QFont("Segoe UI Semibold", 13))
        context_label.setStyleSheet(f"color: {theme['context'].name()}; background: transparent;")
        context_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(context_label)

        layout.addWidget(_BounceBar(theme, self), alignment=Qt.AlignmentFlag.AlignCenter)

        flavor_font = QFont("Segoe UI", 9)
        flavor_font.setItalic(True)
        flavor_label = QLabel(flavor)
        flavor_label.setFont(flavor_font)
        flavor_label.setStyleSheet(f"color: {theme['flavor'].name()}; background: transparent;")
        flavor_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(flavor_label)

        self._dot_count = 0
        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._tick_dots)
        self._dot_timer.start(450)

    def _tick_dots(self) -> None:
        self._dot_count = (self._dot_count + 1) % 4
        dots = "." * self._dot_count
        padding = " " * (3 - self._dot_count)
        self._title.setText(f"{self._TITLE_TEXT}{dots}{padding}")


def main() -> None:
    context = sys.argv[1] if len(sys.argv) > 1 else "Loading..."
    flavor = sys.argv[2] if len(sys.argv) > 2 else ""
    app = QApplication(sys.argv)
    window = OverlayWindow(context, flavor)
    window.show()
    window.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
