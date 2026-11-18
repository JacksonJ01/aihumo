"""Live PyQt6 keyboard prototype for a three-lane 2.5D dodge game."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QKeySequence, QLinearGradient, QPainter, QPen, QPolygonF, QShortcut
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from aihumo.lane_dodge import LaneDodgeEngine, LaneDodgeSnapshot, LaneDodgeState
from aihumo.storage import save_json_atomic
from .preferences import DesktopPreferences, PreferenceStore, PreferencesDialog
from .subapp_style import subapp_stylesheet


class LaneDodgeCanvas(QWidget):
    """Perspective road renderer; game rules remain in ``LaneDodgeEngine``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(620, 420)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.snapshot: LaneDodgeSnapshot | None = None

    def set_snapshot(self, snapshot: LaneDodgeSnapshot) -> None:
        self.snapshot = snapshot
        self.update()

    def _road_geometry(self) -> tuple[float, float, float, float, float]:
        width, height = float(self.width()), float(self.height())
        return width / 2, height * 0.15, height * 0.93, width * 0.075, width * 0.47

    @staticmethod
    def _half_width(depth: float, top: float, bottom: float) -> float:
        return top + (bottom - top) * depth

    def _lane_x(self, lane: int, depth: float, lane_count: int) -> float:
        center, _, _, top, bottom = self._road_geometry()
        half = self._half_width(depth, top, bottom)
        normalized = ((lane + 0.5) / lane_count) * 2 - 1
        return center + normalized * half

    def paintEvent(self, event):  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        sky = QLinearGradient(0, 0, 0, height)
        sky.setColorAt(0.0, QColor("#050b1b"))
        sky.setColorAt(0.48, QColor("#142858"))
        sky.setColorAt(1.0, QColor("#24133f"))
        painter.fillRect(self.rect(), sky)

        center, horizon, bottom_y, top_half, bottom_half = self._road_geometry()
        road = QPolygonF([
            QPointF(center - top_half, horizon), QPointF(center + top_half, horizon),
            QPointF(center + bottom_half, bottom_y), QPointF(center - bottom_half, bottom_y),
        ])
        road_gradient = QLinearGradient(0, horizon, 0, bottom_y)
        road_gradient.setColorAt(0, QColor("#101b38"))
        road_gradient.setColorAt(1, QColor("#080d1b"))
        painter.setPen(QPen(QColor("#22d3ee"), 2))
        painter.setBrush(road_gradient)
        painter.drawPolygon(road)

        lane_count = self.snapshot.lane_count if self.snapshot else 3
        painter.setPen(QPen(QColor(79, 209, 255, 145), 2, Qt.PenStyle.DashLine))
        for boundary in range(1, lane_count):
            fraction = boundary / lane_count
            top_x = center - top_half + fraction * top_half * 2
            bottom_x = center - bottom_half + fraction * bottom_half * 2
            painter.drawLine(QPointF(top_x, horizon), QPointF(bottom_x, bottom_y))

        # Receding cross-lines make motion readable even before an obstacle appears.
        painter.setPen(QPen(QColor(124, 92, 255, 85), 1))
        for index in range(1, 10):
            depth = (index / 10) ** 1.7
            y = horizon + (bottom_y - horizon) * depth
            half = self._half_width(depth, top_half, bottom_half)
            painter.drawLine(QPointF(center - half, y), QPointF(center + half, y))

        snapshot = self.snapshot
        if snapshot is None:
            self._draw_center_message(painter, "Press Start to enter the lane course")
            return

        for obstacle in sorted(snapshot.obstacles, key=lambda item: item.depth):
            depth = max(0.0, min(1.05, obstacle.depth))
            visual_depth = depth ** 1.55
            x = self._lane_x(obstacle.lane, visual_depth, snapshot.lane_count)
            y = horizon + (bottom_y - horizon) * visual_depth
            scale = 0.16 + visual_depth * 0.84
            obstacle_width = (self._half_width(visual_depth, top_half, bottom_half) * 1.45 / snapshot.lane_count)
            obstacle_height = 36 + 105 * scale
            rect = QRectF(x - obstacle_width / 2, y - obstacle_height, obstacle_width, obstacle_height)
            glow = QColor(255, 45, 112, 58)
            painter.setPen(QPen(QColor("#ff497d"), max(2, int(5 * scale))))
            painter.setBrush(glow)
            painter.drawRoundedRect(rect.adjusted(-5, -5, 5, 5), 12, 12)
            painter.setPen(QPen(QColor("#ffbd3d"), max(2, int(3 * scale))))
            painter.setBrush(QColor("#a31345"))
            painter.drawRoundedRect(rect, 9, 9)
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.topRight(), rect.bottomLeft())

        player_x = self._lane_x(snapshot.player_lane, 1.0, snapshot.lane_count)
        player_y = bottom_y - 15
        player = QPolygonF([
            QPointF(player_x, player_y - 62), QPointF(player_x + 38, player_y),
            QPointF(player_x, player_y - 12), QPointF(player_x - 38, player_y),
        ])
        painter.setPen(QPen(QColor("#84f7ff"), 4))
        painter.setBrush(QColor("#1675d1"))
        painter.drawPolygon(player)

        painter.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        painter.setPen(QColor("#f8fbff"))
        painter.drawText(20, 30, f"Score {snapshot.score:,}     Lives {snapshot.lives}     Streak {snapshot.streak}")
        painter.setPen(QColor("#a9c6ee"))
        painter.drawText(20, 54, "←/→ or A/D move  ·  Space starts/pauses  ·  R resets")
        if snapshot.state == LaneDodgeState.PAUSED.value:
            self._draw_center_message(painter, "PAUSED")
        elif snapshot.state == LaneDodgeState.GAME_OVER.value:
            self._draw_center_message(painter, f"COURSE OVER  ·  SCORE {snapshot.score:,}")

    def _draw_center_message(self, painter: QPainter, message: str) -> None:
        rect = QRectF(self.width() * 0.18, self.height() * 0.40, self.width() * 0.64, 72)
        painter.setPen(QPen(QColor("#34d9ed"), 2))
        painter.setBrush(QColor(5, 14, 34, 220))
        painter.drawRoundedRect(rect, 15, 15)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, message)


class LaneDodgeDialog(QDialog):
    """Playable keyboard shell that can later accept pose or phone actions."""

    def __init__(self, parent=None, *, preferences: DesktopPreferences | PreferenceStore | None = None):
        super().__init__(parent)
        self.preference_store = preferences if isinstance(preferences, PreferenceStore) else None
        self.preferences = self.preference_store.values if self.preference_store else (preferences or DesktopPreferences())
        self.setStyleSheet(subapp_stylesheet(self.preferences.theme))
        self.setWindowTitle("AIHuMo Flow Zone — Lane Dodge Prototype")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint)
        self.resize(1100, 760)
        self.engine = LaneDodgeEngine(difficulty="medium")
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 20)
        layout.setSpacing(12)
        header = QFrame(objectName="subAppHeader")
        heading = QHBoxLayout(header)
        title = QLabel("Flow Zone  ·  Live Lane Dodge", objectName="subAppTitle")
        heading.addWidget(title, 1)
        self.difficulty = QComboBox()
        for label, value in (("Easy", "easy"), ("Medium", "medium"), ("Hard", "hard")):
            self.difficulty.addItem(label, value)
        self.difficulty.setCurrentIndex(1)
        self.difficulty.currentIndexChanged.connect(self._change_difficulty)
        heading.addWidget(QLabel("Difficulty"))
        heading.addWidget(self.difficulty)
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        heading.addWidget(self.settings_button)
        close = QPushButton("Back to Flow Zone", objectName="backAction")
        close.clicked.connect(self.close)
        heading.addWidget(close)
        layout.addWidget(header)

        description = QLabel(
            "A keyboard-first 2.5D prototype. Dodge incoming obstacles now; later, the same left/right "
            "actions can be supplied by torso tracking or a phone controller."
        )
        description.setObjectName("subAppDescription")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.canvas = LaneDodgeCanvas()
        self.canvas.set_snapshot(self.engine.snapshot())
        layout.addWidget(self.canvas, 1)

        controls = QHBoxLayout()
        self.start_button = QPushButton("Start", objectName="primaryAction")
        self.start_button.clicked.connect(lambda: self.handle_action("toggle"))
        reset = QPushButton("Reset")
        reset.clicked.connect(lambda: self.handle_action("reset"))
        self.save_button = QPushButton("Save score…")
        self.save_button.clicked.connect(self.save_score)
        controls.addWidget(self.start_button)
        controls.addWidget(reset)
        controls.addWidget(self.save_button)
        controls.addStretch(1)
        self.status = QLabel("Ready · use Left/Right or A/D to choose a lane.", objectName="statusPanel")
        controls.addWidget(self.status, 1)
        layout.addLayout(controls)
        self._install_shortcuts()

    def _install_shortcuts(self) -> None:
        self.shortcuts = []
        for key, action in (
            (Qt.Key.Key_Left, "left"), (Qt.Key.Key_A, "left"),
            (Qt.Key.Key_Right, "right"), (Qt.Key.Key_D, "right"),
            (Qt.Key.Key_Space, "toggle"), (Qt.Key.Key_R, "reset"),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda action=action: self.handle_action(action))
            self.shortcuts.append(shortcut)

    def handle_action(self, action: str) -> None:
        """Controller-neutral action entry point for keyboard, pose, or phone."""
        if action == "left":
            self.engine.move(-1)
        elif action == "right":
            self.engine.move(1)
        elif action == "reset":
            self.timer.stop()
            self.engine.reset()
        elif action == "toggle":
            if self.engine.state == LaneDodgeState.RUNNING:
                self.engine.pause(); self.timer.stop()
            elif self.engine.state == LaneDodgeState.PAUSED:
                self.engine.resume(); self.timer.start()
            else:
                self.engine.start(); self.timer.start()
        self._refresh()
        self.canvas.setFocus()

    def _tick(self) -> None:
        snapshot = self.engine.step(self.timer.interval() / 1000)
        if snapshot.state == LaneDodgeState.GAME_OVER.value:
            self.timer.stop()
            if self.preferences.game_audio_cues:
                QApplication.beep()
        self._refresh(snapshot)

    def _refresh(self, snapshot: LaneDodgeSnapshot | None = None) -> None:
        snapshot = snapshot or self.engine.snapshot()
        self.canvas.set_snapshot(snapshot)
        self.start_button.setText({
            LaneDodgeState.READY.value: "Start",
            LaneDodgeState.RUNNING.value: "Pause",
            LaneDodgeState.PAUSED.value: "Resume",
            LaneDodgeState.GAME_OVER.value: "Play again",
        }[snapshot.state])
        self.status.setText(
            f"{snapshot.state.replace('_', ' ').title()} · score {snapshot.score:,} · "
            f"dodged {snapshot.dodged} · collisions {snapshot.collisions} · best streak {snapshot.best_streak}"
        )

    def _change_difficulty(self) -> None:
        self.timer.stop()
        self.engine = LaneDodgeEngine(difficulty=self.difficulty.currentData())
        self._refresh()

    def open_settings(self) -> None:
        if self.preference_store is None:
            return
        if PreferencesDialog(self.preference_store, self).exec() == QDialog.DialogCode.Accepted:
            self.preferences = self.preference_store.values
            self.setStyleSheet(subapp_stylesheet(self.preferences.theme))

    def save_score(self) -> None:
        default = Path.cwd() / "lane_dodge_results.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save Lane Dodge score", str(default), "JSON (*.json)")
        if not path:
            return
        save_json_atomic(self.engine.snapshot().to_document(), path)
        self.status.setText(f"Saved score to {path}")

    def closeEvent(self, event):  # noqa: N802 - Qt override
        self.timer.stop()
        super().closeEvent(event)
