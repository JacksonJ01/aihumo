"""Shared desktop branding assets and startup splash construction."""
from __future__ import annotations

from pathlib import Path
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QSplashScreen


BRANDING_DIR = Path(__file__).resolve().parents[1] / "assets" / "app_branding"
APP_LOGO_PNG = BRANDING_DIR / "aihumo_logo_v5.png"
APP_LOGO_ICO = BRANDING_DIR / "aihumo_logo_v5.ico"
APP_LOGO_ICNS = BRANDING_DIR / "aihumo_logo_v5.icns"
APP_SPLASH_PNG = BRANDING_DIR / "aihumo_splash_v1.png"
WINDOWS_APP_USER_MODEL_ID = "AIHuMo.DataStudio.Desktop"
STARTUP_SPLASH_MS = 3000
STARTUP_TITLE = "AIHuMo Data Studio"
STARTUP_MESSAGE = "Loading AIHuMo..."


def configure_process_identity() -> bool:
    """Give Windows launches their own taskbar identity instead of Python's.

    This must run before QApplication is constructed.  The packaged EXE also
    embeds the ICO, while this explicit identity covers development launches
    from VS Code or a terminal where the process executable is python.exe.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            WINDOWS_APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):
        return False
    return result == 0


def application_icon() -> QIcon:
    """Return the canonical logo icon, or an empty icon if packaging is incomplete."""
    return QIcon(str(APP_LOGO_PNG)) if APP_LOGO_PNG.is_file() else QIcon()


def create_startup_splash(size: int = 500) -> QSplashScreen | None:
    """Create the pre-rendered logo splash at the requested display width."""
    source = QPixmap(str(APP_SPLASH_PNG))
    if source.isNull():
        return None
    canvas = source.scaled(
        size,
        round(size * source.height() / source.width()),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    splash = QSplashScreen(canvas, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    splash.setObjectName("aihumoStartupSplash")
    splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    splash.setWindowIcon(application_icon())
    splash.setProperty("startupTitle", STARTUP_TITLE)
    splash.setProperty("startupMessage", STARTUP_MESSAGE)
    return splash
