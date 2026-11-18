"""Shared movement-game engine and desktop game workspace.

Games consume the same processed feature Parquet used by Modes 1–4.  This
module deliberately does not run pose detection or create another feature
format: it reads frame IDs, timestamps, midpoints, angles, velocities, and
quality columns once and applies game-specific rules on top of them.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QProgressBar, QSlider,
    QVBoxLayout, QWidget,
)

from aihumo.game_engine import (
    GameDefinition,
    LoopState,
    MovementGameEngine as BackendMovementGameEngine,
    load_game_definitions as load_backend_game_definitions,
)
from aihumo.storage import save_json_atomic
from .preferences import DesktopPreferences, PreferenceStore, PreferencesDialog
from .lane_dodge_game import LaneDodgeDialog
from .subapp_style import subapp_stylesheet


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GAME_CONFIG_PATH = PROJECT_ROOT / "configs" / "movement_games.json"
TIME_COLUMNS = ("timeElapsedS", "timestamp_s", "time_elapsed_s")


@dataclass(frozen=True)
class GameVariant:
    """One focused challenge inside a consolidated Hub game."""

    title: str
    rule: str
    description: str
    grid: tuple[int, int] | None = None
    target_period_s: float | None = None
    tolerance: float | None = None


GAME_VARIANTS: dict[str, tuple[GameVariant, ...]] = {
    "just_dance": (
        GameVariant("Dance Routine", "dance", "Score beat timing, movement energy, and bilateral coordination."),
        GameVariant("Rhythm Drill", "rhythm", "Focus on repeatable movement that lands on each visual beat."),
        GameVariant("Partner Sync", "partner", "Compare timing and joint motion with a loaded reference recording."),
    ),
    "flow_zone": (
        GameVariant("Target Grid", "target_grid", "Enter each highlighted zone accurately.", (3, 2), 1.5, 0.28),
        GameVariant("Precision Grid", "target_grid_12", "Use a denser twelve-zone board for smaller targets.", (4, 3), 1.25, 0.18),
        GameVariant("Reaction Targets", "reaction_targets", "Reach each target before it changes.", (3, 3), 1.0, 0.22),
        GameVariant("Avoid the Zone", "avoid_zone", "Stay outside the highlighted danger zone.", (3, 2), 1.4, 0.25),
        GameVariant("Obstacle Dodge", "obstacle_dodge", "Create clearance with controlled, early evasive movement.", (3, 2), 1.15, 0.24),
    ),
    "mirror_match": (
        GameVariant("Mirror Mode", "mirror", "Match left- and right-side movement as symmetrically as possible."),
        GameVariant("Freeze Pose", "freeze_pose", "Hold the calibrated reference pose without drifting."),
        GameVariant("Reference Match", "partner", "Match the joint timing of a second processed recording."),
    ),
    "balance": (
        GameVariant("Center Control", "balance", "Keep the torso midpoint stable around center."),
        GameVariant("Freeze and Hold", "freeze_pose", "Maintain the calibrated pose while minimizing sway."),
    ),
    "path_precision": (
        GameVariant("Follow the Path", "path_follow", "Trace a smooth moving path with the torso midpoint."),
        GameVariant("Precision Targets", "target_grid_12", "Reach compact zones with controlled transitions.", (4, 3), 1.35, 0.18),
    ),
    "sports": (
        GameVariant("Reach and Recover", "sports_reaction", "Reach quickly, then recover a controlled stance.", (3, 3), 1.0, 0.22),
        GameVariant("Reaction Targets", "reaction_targets", "Respond to unpredictable targets at speed.", (3, 3), 0.9, 0.22),
        GameVariant("Obstacle Drill", "obstacle_dodge", "Sidestep or lower the body to clear changing hazards.", (3, 2), 1.1, 0.24),
    ),
    "rehab": (
        GameVariant("Controlled Range", "rehab", "Move through the available range slowly and consistently."),
        GameVariant("Stability Check", "balance", "Monitor center control during a low-speed stability task."),
    ),
    "ergonomics": (
        GameVariant("Posture Review", "ergonomics", "Review neutral posture, bending, and reaching patterns."),
    ),
    "gait": (
        GameVariant("Walking Symmetry", "gait", "Review bilateral timing, cadence, and transition consistency."),
    ),
    "sequence": (
        GameVariant("Color Memory", "sequence", "Follow the changing zone order from memory.", (3, 3), 1.75, 0.22),
        GameVariant("Speed Recall", "reaction_targets", "Recall and reach the next zone under a shorter timer.", (3, 3), 0.9, 0.22),
    ),
}


def game_variant_definitions(definition: GameDefinition) -> tuple[GameDefinition, ...]:
    """Expand one Hub game into its internal challenge definitions."""
    variants = GAME_VARIANTS.get(definition.id) or (
        GameVariant(definition.title, definition.rule, definition.description),
    )
    expanded = []
    for variant in variants:
        changes: dict[str, Any] = {"rule": variant.rule}
        if variant.grid is not None:
            changes["grid"] = variant.grid
        if variant.target_period_s is not None:
            changes["target_period_s"] = variant.target_period_s
        if variant.tolerance is not None:
            changes["tolerance"] = variant.tolerance
        expanded.append(replace(definition, **changes))
    return tuple(expanded)


def load_game_definitions(path: str | Path = GAME_CONFIG_PATH) -> tuple[GameDefinition, ...]:
    """Load the hub catalog from JSON so adding a mode does not require code."""
    return load_backend_game_definitions(path)


def feature_pair_for_parquet(parquet_path: str | Path) -> tuple[Path | None, Path]:
    """Find the matching skeleton video without changing the feature source."""
    parquet = Path(parquet_path).expanduser().resolve(strict=True)
    stem = parquet.stem.removesuffix("_features")
    candidates = (
        parquet.parent.parent / "video" / f"{stem}_skeleton.mp4",
        parquet.parent / f"{stem}_skeleton.mp4",
        parquet.with_name(f"{stem}_skeleton.mp4"),
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None), parquet


def load_feature_recording(parquet_path: str | Path) -> pd.DataFrame:
    """Read the canonical feature table used by every movement game."""
    _, parquet = feature_pair_for_parquet(parquet_path)
    frame = pd.read_parquet(parquet)
    time_column = next((name for name in TIME_COLUMNS if name in frame.columns), None)
    if "frame_id" not in frame.columns or time_column is None or frame.empty:
        raise ValueError("Choose an AIHuMo feature Parquet with frame_id, timestamps, and at least one row.")
    frame = frame.copy()
    frame["_game_time_s"] = pd.to_numeric(frame[time_column], errors="coerce")
    frame["_game_frame_id"] = pd.to_numeric(frame["frame_id"], errors="coerce")
    if frame[["_game_time_s", "_game_frame_id"]].isna().any().any():
        raise ValueError("The selected feature Parquet contains invalid frame IDs or timestamps.")
    if not np.array_equal(frame["_game_frame_id"].to_numpy(dtype=int), np.arange(len(frame))):
        raise ValueError("Feature frame IDs must run from 0 through the last frame.")
    return frame


# Keep the public import stable while routing every mode through the pure,
# stateful backend in ``aihumo.game_engine``.
MovementGameEngine = BackendMovementGameEngine


class GameCanvas(QWidget):
    """Small, dependency-free game board shared by all configured modes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(460, 320)
        self.state: dict[str, Any] = {}
        self.high_contrast = False

    def set_high_contrast(self, enabled: bool) -> None:
        self.high_contrast = bool(enabled)
        self.update()

    def set_state(self, state: dict[str, Any], *, rule: str = "target_grid") -> None:
        self.state = {**state, "rule": rule}
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        background = QLinearGradient(0, 0, width, height)
        background.setColorAt(0.0, QColor("#071426"))
        background.setColorAt(0.55, QColor("#102443"))
        background.setColorAt(1.0, QColor("#1b1740"))
        painter.fillRect(self.rect(), background)
        painter.setPen(QPen(QColor("#36c9d8"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -3, -3), 15, 15)
        rule = self.state.get("rule", "target_grid")
        cols, rows = self.state.get("grid", (3, 2))
        for column in range(cols):
            for row in range(rows):
                rect = self.rect().adjusted(column * width // cols, row * height // rows,
                                            -(cols - column - 1) * width // cols,
                                            -(rows - row - 1) * height // rows)
                painter.setPen(QPen(QColor(53, 73, 103, 180), 2))
                painter.setBrush(QBrush(QColor(22, 38, 63, 120)))
                painter.drawRect(rect)
        target = self.state.get("target", (0.5, 0.5))
        target_rect = self.rect().adjusted(int((target[0] - 0.15) * width), int((target[1] - 0.15) * height),
                                           -int((0.85 - target[0]) * width), -int((0.85 - target[1]) * height))
        danger = rule in {"avoid_zone", "obstacle_dodge"}
        if self.high_contrast:
            target_color = QColor("#ff2bd6" if danger else "#fff200")
        else:
            target_color = QColor("#ef4444" if danger else "#f59e0b")
        painter.setPen(QPen(target_color, 4))
        # QBrush accepts a QColor, not four RGBA channel arguments. Keeping
        # alpha construction inside QColor makes this valid across PyQt6
        # versions and protects every game that shares this canvas.
        painter.setBrush(QBrush(QColor(target_color.red(), target_color.green(), target_color.blue(), 70)))
        painter.drawRect(target_rect)
        position = self.state.get("position", (0.5, 0.5))
        point = (int(position[0] * width), int(position[1] * height))
        if self.high_contrast:
            player_color = QColor("#3cff00" if self.state.get("success", False) else "#ffffff")
        else:
            player_color = QColor("#22c55e" if self.state.get("success", False) else "#38bdf8")
        painter.setPen(QPen(player_color, 4))
        painter.setBrush(QBrush(player_color))
        painter.drawEllipse(point[0] - 13, point[1] - 13, 26, 26)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(5, 18, 48, 210))
        painter.drawRoundedRect(12, 8, max(160, width - 24), 32, 10, 10)
        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        painter.drawText(22, 30, self.state.get("label", "Load a processed recording to begin"))


class MovementGameDialog(QDialog):
    """Run any catalogued movement game against a processed recording."""

    def __init__(self, definition: GameDefinition | str, parent=None, *,
                 preferences: DesktopPreferences | PreferenceStore | None = None):
        super().__init__(parent)
        self.preference_store = preferences if isinstance(preferences, PreferenceStore) else None
        self.preferences = self.preference_store.values if self.preference_store else (preferences or DesktopPreferences())
        self.setStyleSheet(subapp_stylesheet(self.preferences.theme))
        definitions = {item.id: item for item in load_game_definitions()}
        self.definitions = definitions
        self.base_definition = definitions[definition] if isinstance(definition, str) else definition
        self.definition = self.base_definition
        self.selected_variant = GAME_VARIANTS[self.base_definition.id][0]
        self.engine: MovementGameEngine | None = None
        self.partner_frame: pd.DataFrame | None = None
        self.video_path: Path | None = None
        self.setWindowTitle(f"AIHuMo Movement Game — {self.definition.title}")
        self.resize(980, 720)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._countdown_tick)
        self._countdown_remaining = 0
        self._countdown_complete = False
        self._last_cue_slot = -1
        self._auto_saved = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 20)
        layout.setSpacing(12)
        header = QFrame(objectName="subAppHeader")
        heading = QHBoxLayout(header)
        heading.setContentsMargins(16, 12, 14, 12)
        self.title_label = QLabel(f"{self.definition.title}  ·  {self.definition.category}")
        self.title_label.setObjectName("subAppTitle")
        heading.addWidget(self.title_label, 1)
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        heading.addWidget(self.settings_button)
        self.back_button = QPushButton("Back to Hub Page")
        self.back_button.setObjectName("backAction")
        self.back_button.clicked.connect(self.close)
        heading.addWidget(self.back_button)
        layout.addWidget(header)
        self.description_label = QLabel(f"{self.definition.description}\nObjective: {self.definition.objective}")
        self.description_label.setObjectName("subAppDescription")
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)
        setup_group = QGroupBox("Game setup")
        controls = QFormLayout(setup_group)
        controls.setHorizontalSpacing(14)
        controls.setVerticalSpacing(9)
        self.game_combo = QComboBox()
        for item in definitions.values():
            self.game_combo.addItem(item.title, item.id)
        self.game_combo.setCurrentIndex(max(0, self.game_combo.findData(self.definition.id)))
        self.game_combo.currentIndexChanged.connect(self.change_game)
        controls.addRow("Game mode", self.game_combo)
        self.variant_combo = QComboBox()
        self.variant_combo.currentIndexChanged.connect(self.change_variant)
        controls.addRow("Challenge", self.variant_combo)
        self.difficulty_combo = QComboBox()
        for label, value in (("Adaptive", "adaptive"), ("Easy", "easy"), ("Medium", "medium"), ("Hard", "hard")):
            self.difficulty_combo.addItem(label, value)
        self.difficulty_combo.setCurrentIndex(max(0, self.difficulty_combo.findData(self.preferences.game_default_difficulty)))
        self.difficulty_combo.currentIndexChanged.connect(self.change_difficulty)
        controls.addRow("Difficulty", self.difficulty_combo)
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.load_button = QPushButton("Load processed Parquet…")
        self.load_button.clicked.connect(self.choose_recording)
        path_row = QHBoxLayout(); path_row.addWidget(self.path_edit, 1); path_row.addWidget(self.load_button)
        controls.addRow("Shared feature source", path_row)
        self.partner_path_edit = QLineEdit()
        self.partner_path_edit.setReadOnly(True)
        self.partner_button = QPushButton("Load reference / partner…")
        self.partner_button.clicked.connect(self.choose_partner_recording)
        partner_row = QHBoxLayout(); partner_row.addWidget(self.partner_path_edit, 1); partner_row.addWidget(self.partner_button)
        controls.addRow("Optional comparison source", partner_row)
        self.live_dodge_button = QPushButton("Play live keyboard lane dodge…")
        self.live_dodge_button.clicked.connect(self.open_lane_dodge)
        controls.addRow("Live prototype", self.live_dodge_button)
        layout.addWidget(setup_group)
        self._populate_variants(self.base_definition)
        self.canvas = GameCanvas()
        self.canvas.setObjectName("gameCanvas")
        self.canvas.set_high_contrast(self.preferences.game_high_contrast_targets)
        layout.addWidget(self.canvas, 1)
        metrics = QHBoxLayout()
        self.score_metric = QLabel("Score  —", objectName="metricCard")
        self.success_metric = QLabel("Success  —", objectName="metricCard")
        self.streak_metric = QLabel("Streak  —", objectName="metricCard")
        for metric in (self.score_metric, self.success_metric, self.streak_metric):
            metric.setAlignment(Qt.AlignmentFlag.AlignCenter)
            metrics.addWidget(metric)
        layout.addLayout(metrics)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("primaryAction")
        self.start_button.clicked.connect(self.toggle_play)
        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.reset_game)
        self.save_results_button = QPushButton("Save results…")
        self.save_results_button.setEnabled(False)
        self.save_results_button.clicked.connect(self.save_results)
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setEnabled(False)
        self.frame_slider.valueChanged.connect(self.seek_frame)
        actions.addWidget(self.start_button); actions.addWidget(self.reset_button); actions.addWidget(self.save_results_button)
        actions.addWidget(self.frame_slider, 1)
        layout.addLayout(actions)
        self.status = QLabel("Load one processed feature Parquet. All game modes reuse that same source.")
        self.status.setObjectName("statusPanel")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def open_settings(self) -> None:
        if self.preference_store is None:
            return
        if PreferencesDialog(self.preference_store, self).exec() == QDialog.DialogCode.Accepted:
            self.preferences = self.preference_store.values
            self.setStyleSheet(subapp_stylesheet(self.preferences.theme))
            self.canvas.set_high_contrast(self.preferences.game_high_contrast_targets)

    def _populate_variants(self, definition: GameDefinition) -> None:
        self.variant_combo.blockSignals(True)
        self.variant_combo.clear()
        for variant in GAME_VARIANTS[definition.id]:
            self.variant_combo.addItem(variant.title, variant)
        self.variant_combo.setCurrentIndex(0)
        self.variant_combo.setEnabled(self.variant_combo.count() > 1)
        self.variant_combo.blockSignals(False)
        self.selected_variant = self.variant_combo.currentData()
        self.definition = game_variant_definitions(definition)[0]
        self._update_challenge_text()

    def _update_challenge_text(self) -> None:
        selected = self.selected_variant
        self.setWindowTitle(f"AIHuMo Movement Game — {self.base_definition.title}")
        self.title_label.setText(
            f"{self.base_definition.title}  ·  {selected.title}  ·  {self.base_definition.category}"
        )
        self.description_label.setText(
            f"{self.base_definition.description}\nChallenge: {selected.description}\n"
            f"Objective: {self.base_definition.objective}"
        )
        needs_partner = self.definition.rule == "partner"
        self.partner_button.setEnabled(needs_partner)
        self.partner_path_edit.setEnabled(needs_partner)
        if needs_partner and self.partner_frame is None:
            self.partner_path_edit.setPlaceholderText("Load a reference recording for this challenge")
        self.live_dodge_button.setVisible(self.definition.rule == "obstacle_dodge")

    def open_lane_dodge(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            if self.engine is not None:
                self.engine.pause()
        preferences = self.preference_store or self.preferences
        dialog = LaneDodgeDialog(self, preferences=preferences)
        dialog.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        dialog.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        dialog.showMaximized()
        dialog.exec()

    def _reset_challenge(self) -> None:
        self.timer.stop()
        self.countdown_timer.stop()
        self._countdown_complete = False
        self._auto_saved = False
        self.start_button.setText("Start")
        if self.engine is not None:
            self.engine = self._create_engine(self.definition, self.engine.frame)
            self.frame_slider.setValue(0)
            self.render_frame(0)

    def change_game(self) -> None:
        selected = self.definitions.get(self.game_combo.currentData())
        if selected is None:
            return
        self.base_definition = selected
        self._populate_variants(selected)
        self._reset_challenge()

    def change_variant(self) -> None:
        variant = self.variant_combo.currentData()
        if not isinstance(variant, GameVariant):
            return
        self.selected_variant = variant
        index = self.variant_combo.currentIndex()
        self.definition = game_variant_definitions(self.base_definition)[index]
        self._update_challenge_text()
        self._reset_challenge()

    def change_difficulty(self) -> None:
        if self.engine is None:
            return
        self.timer.stop()
        self.countdown_timer.stop()
        self._countdown_complete = False
        self.engine = self._create_engine(self.definition, self.engine.frame)
        self.start_button.setText("Start")
        self.frame_slider.setValue(0)
        self.render_frame(0)

    def choose_recording(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select processed feature Parquet", "", "Features (*_features.parquet *.parquet)")
        if not path:
            return
        try:
            frame = load_feature_recording(path)
            self.video_path, parquet = feature_pair_for_parquet(path)
            self.engine = self._create_engine(self.definition, frame)
            self._auto_saved = False
            self._last_cue_slot = -1
            self.path_edit.setText(str(parquet))
            self.frame_slider.setRange(0, max(0, len(frame) - 1))
            self.frame_slider.setEnabled(True)
            self.save_results_button.setEnabled(True)
            self.render_frame(0)
            self.status.setText(f"Loaded {len(frame):,} frames from {parquet.name}. Press Start to run the replay.")
        except Exception as exc:
            QMessageBox.warning(self, "Could not load recording", f"{type(exc).__name__}: {exc}")

    def choose_partner_recording(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select reference or partner feature Parquet", "", "Features (*_features.parquet *.parquet)"
        )
        if not path:
            return
        try:
            self.partner_frame = load_feature_recording(path)
            self.partner_path_edit.setText(str(Path(path).resolve()))
            if self.engine is not None:
                self.timer.stop()
                self.engine = self._create_engine(self.definition, self.engine.frame)
                self.frame_slider.setValue(0)
                self.render_frame(0)
            self.status.setText(f"Loaded optional comparison source: {Path(path).name}")
        except Exception as exc:
            QMessageBox.warning(self, "Could not load comparison recording", f"{type(exc).__name__}: {exc}")

    def _create_engine(self, definition: GameDefinition, frame: pd.DataFrame) -> MovementGameEngine:
        configured = replace(
            definition,
            target_period_s=max(0.05, definition.target_period_s * self.preferences.game_target_period_scale),
            calibration_s=self.preferences.game_calibration_s,
        )
        return MovementGameEngine(
            configured,
            frame,
            difficulty=self.difficulty_combo.currentData(),
            partner_frame=self.partner_frame,
        )

    def toggle_play(self) -> None:
        if self.engine is None:
            self.choose_recording()
            return
        if (self.engine.state == LoopState.READY and self.preferences.game_countdown_s > 0
                and not self._countdown_complete and not self.countdown_timer.isActive()):
            self._countdown_remaining = self.preferences.game_countdown_s
            self.start_button.setEnabled(False)
            self.start_button.setText(str(self._countdown_remaining))
            self.status.setText(f"Starting {self.definition.title} in {self._countdown_remaining}…")
            self.countdown_timer.start()
            return
        if self.timer.isActive():
            self.timer.stop()
            self.engine.pause()
            self.start_button.setText("Resume")
        else:
            if self.engine.state == LoopState.COMPLETED:
                self.engine.reset()
                self.frame_slider.setValue(0)
            if self.engine.state == LoopState.READY:
                self.engine.start(from_index=self.frame_slider.value())
                result = self.engine.step(self.frame_slider.value())
                self.render_result(result)
                self._countdown_complete = False
            else:
                self.engine.resume()
            if self.engine.state == LoopState.COMPLETED:
                self.start_button.setText("Replay")
                self._show_completion_summary()
            else:
                self.start_button.setText("Pause")
                self._schedule_next_frame()

    def _countdown_tick(self) -> None:
        self._countdown_remaining -= 1
        if self._countdown_remaining > 0:
            self.start_button.setText(str(self._countdown_remaining))
            self.status.setText(f"Starting {self.definition.title} in {self._countdown_remaining}…")
            if self.preferences.game_audio_cues:
                QApplication.beep()
            return
        self.countdown_timer.stop()
        self.start_button.setEnabled(True)
        self.start_button.setText("Start")
        self._countdown_complete = True
        if self.preferences.game_audio_cues:
            QApplication.beep()
        self.toggle_play()

    def reset_game(self) -> None:
        self.timer.stop(); self.countdown_timer.stop(); self.start_button.setEnabled(True); self.start_button.setText("Start")
        self._countdown_complete = False; self._auto_saved = False; self._last_cue_slot = -1
        if self.engine is not None:
            self.engine.reset(); self.frame_slider.setValue(0); self.render_frame(0)
        else:
            self.score_metric.setText("Score  —")
            self.success_metric.setText("Success  —")
            self.streak_metric.setText("Streak  —")

    def seek_frame(self, index: int) -> None:
        if self.engine is not None and not self.timer.isActive():
            self.engine.seek(index)
            self.render_frame(index)

    def next_frame(self) -> None:
        if self.engine is None:
            return
        if self.engine.state not in (LoopState.RUNNING, LoopState.CALIBRATING):
            return
        index = min(self.engine.index + 1, self.engine.frame_count - 1)
        result = self.engine.step(index)
        self.frame_slider.blockSignals(True); self.frame_slider.setValue(index); self.frame_slider.blockSignals(False)
        self.render_result(result)
        if self.engine.state == LoopState.COMPLETED:
            self.timer.stop()
            self.start_button.setText("Replay")
            self._show_completion_summary()
        else:
            self._schedule_next_frame()

    def _show_completion_summary(self) -> None:
        if self.engine is None:
            return
        summary = self.engine.summary()
        self.status.setText(
            f"Complete | score {summary.average_score:.0%} | success {summary.success_rate:.0%} | "
            f"best streak {summary.max_streak} | {summary.samples} scored frames"
        )
        if self.preferences.game_auto_save_results and not self._auto_saved:
            self._auto_save_results()

    def _schedule_next_frame(self) -> None:
        if self.engine is None or self.engine.state not in (LoopState.RUNNING, LoopState.CALIBRATING):
            return
        current = self.engine.index
        if current >= self.engine.frame_count - 1:
            self.next_frame()
            return
        delay_s = float(self.engine.times[current + 1] - self.engine.times[current])
        self.timer.start(int(np.clip(delay_s * 1000, 10, 1000)))

    def render_frame(self, index: int) -> None:
        if self.engine is None:
            return
        result = self.engine.preview(index)
        self.render_result(result)

    def render_result(self, result: dict[str, Any]) -> None:
        if self.engine is None:
            return
        index = self.engine.index
        self.progress.setValue(int((index + 1) * 100 / self.engine.frame_count))
        self.score_metric.setText(f"Score  {result['average']:.0%}")
        self.success_metric.setText(f"Success  {result['success_rate']:.0%}")
        self.streak_metric.setText(f"Streak  {result['streak']}")
        self.canvas.set_state({
            **result,
            "grid": self.definition.grid,
            "label": f"Frame {result['frame']}  ·  {result['time_s']:.3f}s",
        }, rule=self.definition.rule)
        status = (
            f"Frame {result['frame']} | score {result['score']:.0%} | "
            f"running score {result['average']:.0%} | success rate {result['success_rate']:.0%} | "
            f"streak {result['streak']}"
        )
        if self.preferences.game_show_instructions:
            status += f" | {result['instruction']}"
        self.status.setText(status)
        slot = int(result.get("target_slot", -1))
        if (self.preferences.game_audio_cues and not result.get("calibrating", False)
                and slot != self._last_cue_slot):
            self._last_cue_slot = slot
            QApplication.beep()

    def _result_path(self) -> Path:
        source = Path(self.path_edit.text()) if self.path_edit.text() else Path.cwd() / "game"
        if self.preferences.game_results_directory:
            default_dir = Path(self.preferences.game_results_directory).expanduser()
        else:
            default_dir = source.parent.parent / "game_results" if source.suffix else source
        default_dir.mkdir(parents=True, exist_ok=True)
        return default_dir / f"{source.stem.removesuffix('_features')}_{self.definition.id}_results.json"

    def _auto_save_results(self) -> None:
        if self.engine is None:
            return
        try:
            path = self._result_path()
            save_json_atomic(self.engine.summary().to_document(), path)
            self._auto_saved = True
            self.status.setText(f"{self.status.text()} | saved to {path}")
        except Exception as exc:
            self.status.setText(f"{self.status.text()} | automatic save failed: {type(exc).__name__}: {exc}")

    def save_results(self) -> None:
        if self.engine is None:
            return
        default_path = self._result_path()
        path, _ = QFileDialog.getSaveFileName(self, "Save game results", str(default_path), "JSON (*.json)")
        if not path:
            return
        try:
            save_json_atomic(self.engine.summary().to_document(), path)
            self.status.setText(f"Saved game results to {path}")
        except Exception as exc:
            QMessageBox.warning(self, "Could not save results", f"{type(exc).__name__}: {exc}")
