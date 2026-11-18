"""Accessible in-app operating guides for Main Hub applications."""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .app_guides import AppGuide


def _bullet_list(items: tuple[str, ...], *, numbered: bool = False) -> QLabel:
    prefix = (lambda index: f"{index}.") if numbered else (lambda _index: "•")
    label = QLabel("\n".join(f"{prefix(index)}  {item}" for index, item in enumerate(items, 1)))
    label.setObjectName("guideText")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class HowToDialog(QDialog):
    def __init__(self, title: str, guide: AppGuide, open_app: Callable[[], None], parent=None):
        super().__init__(parent)
        self.setObjectName("howToDialog")
        self.setWindowTitle(f"How to use {title}")
        self.resize(760, 720)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        heading = QLabel(f"How to use {title}", objectName="guideTitle")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        purpose = QLabel(guide.purpose, objectName="guidePurpose")
        purpose.setWordWrap(True)
        purpose.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(purpose)

        for heading_text, items, numbered in (
            ("Before you start", guide.before_you_start, False),
            ("How to use", guide.steps, True),
            ("What to review", guide.review, False),
        ):
            layout.addWidget(QLabel(heading_text, objectName="guideSectionTitle"))
            layout.addWidget(_bullet_list(items, numbered=numbered))

        if guide.safety:
            layout.addWidget(QLabel("Safety and notes", objectName="guideSectionTitle"))
            safety = QLabel(guide.safety, objectName="guideSafety")
            safety.setWordWrap(True)
            safety.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(safety)

        video = QFrame(objectName="guideVideoPlaceholder")
        video_layout = QVBoxLayout(video)
        video_layout.addWidget(QLabel("Video guide", objectName="guideSectionTitle"))
        video_text = QLabel(guide.video_status, objectName="guideText")
        video_text.setWordWrap(True)
        video_layout.addWidget(video_text)
        layout.addWidget(video)
        layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(20, 12, 20, 18)
        close = QPushButton("Close", objectName="quietButton")
        close.clicked.connect(self.reject)
        launch = QPushButton(f"Open {title}", objectName="primaryButton")

        def launch_app() -> None:
            self.accept()
            open_app()

        launch.clicked.connect(launch_app)
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(launch)
        outer.addLayout(buttons)
