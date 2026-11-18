"""Shared visual language for AIHuMo pipeline and game sub-applications."""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QWidget


def fit_window_to_available_screen(
    widget: QWidget,
    *,
    preferred: tuple[int, int],
    minimum: tuple[int, int] = (720, 520),
    coverage: tuple[float, float] = (0.86, 0.84),
) -> None:
    """Keep a resizable window inside the usable desktop, including its title bar."""
    screen = widget.screen() or QApplication.primaryScreen()
    if screen is None:
        widget.resize(*preferred)
        return
    available = screen.availableGeometry()
    maximum_width = max(480, int(available.width() * coverage[0]))
    maximum_height = max(420, int(available.height() * coverage[1]))
    width = min(preferred[0], maximum_width)
    height = min(preferred[1], maximum_height)
    minimum_width = min(minimum[0], width)
    minimum_height = min(minimum[1], height)
    widget.setMinimumSize(minimum_width, minimum_height)
    widget.resize(width, height)


def subapp_stylesheet(theme: str) -> str:
    dark = theme in {"Dark", "High contrast"}
    if dark:
        colors = {
            "window": "#091426", "panel": "#101d33", "card": "#16263f",
            "text": "#f5f7ff", "muted": "#b7c2d8", "border": "#354967",
            "accent": "#36c9d8", "accent2": "#7867ef", "field": "#0c192c",
            "track": "#263957",
        }
    else:
        colors = {
            "window": "#f5f7fb", "panel": "#ffffff", "card": "#ffffff",
            "text": "#15213d", "muted": "#63708a", "border": "#d4ddea",
            "accent": "#22bdd1", "accent2": "#7563e7", "field": "#eef2f7",
            "track": "#dce4ef",
        }
    return f"""
        QDialog, QMainWindow {{ background: {colors['window']}; color: {colors['text']}; font-family: "Segoe UI"; }}
        QWidget#subAppBody {{ background: {colors['window']}; color: {colors['text']}; }}
        QWidget, QLabel, QCheckBox, QRadioButton, QGroupBox {{ color: {colors['text']}; }}
        QScrollArea {{ background: {colors['window']}; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: {colors['window']}; }}
        QAbstractScrollArea::viewport {{ background: {colors['field']}; color: {colors['text']}; }}
        QFrame#subAppHeader {{ background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 14px; }}
        QLabel#subAppTitle {{ font-size: 22px; font-weight: 800; color: {colors['text']}; }}
        QLabel#subAppDescription {{ color: {colors['muted']}; font-size: 13px; padding: 4px 2px 8px 2px; }}
        QLabel#statusPanel {{ background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 11px; padding: 10px 12px; color: {colors['muted']}; }}
        QLabel#metricCard {{ background: {colors['card']}; border: 1px solid {colors['border']}; border-radius: 10px; padding: 8px 12px; font-weight: 700; min-width: 120px; }}
        QLabel#cognitivePrompt {{ background: {colors['card']}; border: 1px solid {colors['border']}; border-radius: 14px; padding: 16px; font-size: 20px; font-weight: 700; }}
        QGroupBox {{ background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 12px; margin-top: 12px; padding: 14px 10px 10px 10px; font-weight: 700; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 13px; padding: 0 6px; color: {colors['accent']}; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit, QListWidget, QTableWidget, QTableView {{ color: {colors['text']}; background: {colors['field']}; alternate-background-color: {colors['panel']}; gridline-color: {colors['border']}; border: 1px solid {colors['border']}; border-radius: 9px; padding: 7px 9px; selection-background-color: {colors['accent2']}; }}
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {colors['muted']}; background: {colors['track']}; }}
        QComboBox QAbstractItemView {{ color: {colors['text']}; background: {colors['panel']}; border: 1px solid {colors['border']}; selection-background-color: {colors['accent2']}; }}
        QHeaderView::section {{ color: {colors['text']}; background: {colors['panel']}; border: none; border-right: 1px solid {colors['border']}; border-bottom: 1px solid {colors['border']}; padding: 7px 9px; font-weight: 700; }}
        QTableCornerButton::section {{ background: {colors['panel']}; border: 1px solid {colors['border']}; }}
        QPushButton {{ color: {colors['text']}; background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 10px; padding: 8px 12px; font-weight: 650; }}
        QPushButton:hover {{ border-color: {colors['accent']}; background: {colors['card']}; }}
        QPushButton:disabled {{ color: {colors['muted']}; background: {colors['field']}; }}
        QPushButton#primaryAction {{ color: white; background: {colors['accent2']}; border: none; }}
        QPushButton#primaryAction:hover {{ color: #07152f; background: {colors['accent']}; }}
        QPushButton#backAction {{ background: transparent; }}
        QProgressBar {{ color: {colors['text']}; background: {colors['track']}; border: 1px solid {colors['border']}; border-radius: 7px; text-align: center; min-height: 13px; }}
        QProgressBar::chunk {{ background: {colors['accent']}; border-radius: 6px; }}
        QSlider::groove:horizontal {{ background: {colors['track']}; height: 7px; border-radius: 3px; }}
        QSlider::handle:horizontal {{ background: {colors['accent2']}; border: 2px solid {colors['accent']}; width: 17px; margin: -6px 0; border-radius: 9px; }}
        QScrollBar:vertical {{ background: transparent; width: 11px; margin: 3px; }}
        QScrollBar::handle:vertical {{ background: {colors['border']}; min-height: 32px; border-radius: 5px; }}
        QScrollBar::handle:vertical:hover {{ background: {colors['accent']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QToolTip {{ color: {colors['text']}; background: {colors['card']}; border: 1px solid {colors['accent']}; padding: 5px; }}
    """
