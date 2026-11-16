"""Shared movement-game engine and desktop game workspace.

Games consume the same processed feature Parquet used by Modes 1–4.  This
module deliberately does not run pose detection or create another feature
format: it reads frame IDs, timestamps, midpoints, angles, velocities, and
quality columns once and applies game-specific rules on top of them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GAME_CONFIG_PATH = PROJECT_ROOT / "configs" / "movement_games.json"
TIME_COLUMNS = ("timeElapsedS", "timestamp_s", "time_elapsed_s")


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

    def set_state(self, state: dict[str, Any], *, rule: str = "target_grid") -> None:
        self.state = {**state, "rule": rule}
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101827"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        rule = self.state.get("rule", "target_grid")
        cols, rows = self.state.get("grid", (3, 2))
        for column in range(cols):
            for row in range(rows):
                rect = self.rect().adjusted(column * width // cols, row * height // rows,
                                            -(cols - column - 1) * width // cols,
                                            -(rows - row - 1) * height // rows)
                painter.setPen(QPen(QColor("#334155"), 2))
                painter.setBrush(QBrush(QColor("#172236")))
                painter.drawRect(rect)
        target = self.state.get("target", (0.5, 0.5))
        target_rect = self.rect().adjusted(int((target[0] - 0.15) * width), int((target[1] - 0.15) * height),
                                           -int((0.85 - target[0]) * width), -int((0.85 - target[1]) * height))
        danger = rule in {"avoid_zone", "obstacle_dodge"}
        target_color = QColor("#ef4444" if danger else "#f59e0b")
        painter.setPen(QPen(target_color, 4))
        painter.setBrush(QBrush(target_color.red(), target_color.green(), target_color.blue(), 70))
        painter.drawRect(target_rect)
        position = self.state.get("position", (0.5, 0.5))
        point = (int(position[0] * width), int(position[1] * height))
        player_color = QColor("#22c55e" if self.state.get("success", False) else "#38bdf8")
        painter.setPen(QPen(player_color, 4))
        painter.setBrush(QBrush(player_color))
        painter.drawEllipse(point[0] - 13, point[1] - 13, 26, 26)
        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        painter.drawText(18, 28, self.state.get("label", "Load a processed recording to begin"))


class MovementGameDialog(QDialog):
    """Run any catalogued movement game against a processed recording."""

    def __init__(self, definition: GameDefinition | str, parent=None):
        super().__init__(parent)
        definitions = {item.id: item for item in load_game_definitions()}
        self.definitions = definitions
        self.definition = definitions[definition] if isinstance(definition, str) else definition
        self.engine: MovementGameEngine | None = None
        self.partner_frame: pd.DataFrame | None = None
        self.video_path: Path | None = None
        self.setWindowTitle(f"AIHuMo Movement Game — {self.definition.title}")
        self.resize(980, 720)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        self.title_label = QLabel(f"{self.definition.title}  ·  {self.definition.category}")
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        heading.addWidget(self.title_label, 1)
        back = QPushButton("Back to Hub Page")
        back.clicked.connect(self.close)
        heading.addWidget(back)
        layout.addLayout(heading)
        self.description_label = QLabel(f"{self.definition.description}\nObjective: {self.definition.objective}")
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)
        controls = QFormLayout()
        self.game_combo = QComboBox()
        for item in definitions.values():
            self.game_combo.addItem(item.title, item.id)
        self.game_combo.setCurrentIndex(max(0, self.game_combo.findData(self.definition.id)))
        self.game_combo.currentIndexChanged.connect(self.change_game)
        controls.addRow("Game mode", self.game_combo)
        self.difficulty_combo = QComboBox()
        for label, value in (("Adaptive", "adaptive"), ("Easy", "easy"), ("Medium", "medium"), ("Hard", "hard")):
            self.difficulty_combo.addItem(label, value)
        self.difficulty_combo.currentIndexChanged.connect(self.change_difficulty)
        controls.addRow("Difficulty", self.difficulty_combo)
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        choose = QPushButton("Load processed Parquet…")
        choose.clicked.connect(self.choose_recording)
        path_row = QHBoxLayout(); path_row.addWidget(self.path_edit, 1); path_row.addWidget(choose)
        controls.addRow("Shared feature source", path_row)
        self.partner_path_edit = QLineEdit()
        self.partner_path_edit.setReadOnly(True)
        choose_partner = QPushButton("Load reference / partner…")
        choose_partner.clicked.connect(self.choose_partner_recording)
        partner_row = QHBoxLayout(); partner_row.addWidget(self.partner_path_edit, 1); partner_row.addWidget(choose_partner)
        controls.addRow("Optional comparison source", partner_row)
        layout.addLayout(controls)
        self.canvas = GameCanvas()
        layout.addWidget(self.canvas, 1)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.toggle_play)
        reset = QPushButton("Reset")
        reset.clicked.connect(self.reset_game)
        self.save_results_button = QPushButton("Save results…")
        self.save_results_button.setEnabled(False)
        self.save_results_button.clicked.connect(self.save_results)
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setEnabled(False)
        self.frame_slider.valueChanged.connect(self.seek_frame)
        actions.addWidget(self.start_button); actions.addWidget(reset); actions.addWidget(self.save_results_button)
        actions.addWidget(self.frame_slider, 1)
        layout.addLayout(actions)
        self.status = QLabel("Load one processed feature Parquet. All game modes reuse that same source.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def change_game(self) -> None:
        selected = self.definitions.get(self.game_combo.currentData())
        if selected is None:
            return
        self.definition = selected
        self.setWindowTitle(f"AIHuMo Movement Game — {selected.title}")
        self.title_label.setText(f"{selected.title}  ·  {selected.category}")
        self.description_label.setText(f"{selected.description}\nObjective: {selected.objective}")
        self.timer.stop()
        self.start_button.setText("Start")
        if self.engine is not None:
            self.engine = self._create_engine(selected, self.engine.frame)
            self.frame_slider.setValue(0)
            self.render_frame(0)

    def change_difficulty(self) -> None:
        if self.engine is None:
            return
        self.timer.stop()
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
        return MovementGameEngine(
            definition,
            frame,
            difficulty=self.difficulty_combo.currentData(),
            partner_frame=self.partner_frame,
        )

    def toggle_play(self) -> None:
        if self.engine is None:
            self.choose_recording()
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
            else:
                self.engine.resume()
            if self.engine.state == LoopState.COMPLETED:
                self.start_button.setText("Replay")
                self._show_completion_summary()
            else:
                self.start_button.setText("Pause")
                self._schedule_next_frame()

    def reset_game(self) -> None:
        self.timer.stop(); self.start_button.setText("Start")
        if self.engine is not None:
            self.engine.reset(); self.frame_slider.setValue(0); self.render_frame(0)

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
        self.canvas.set_state({
            **result,
            "grid": self.definition.grid,
            "label": f"Frame {result['frame']}  ·  {result['time_s']:.3f}s",
        }, rule=self.definition.rule)
        self.status.setText(
            f"Frame {result['frame']} | score {result['score']:.0%} | "
            f"running score {result['average']:.0%} | success rate {result['success_rate']:.0%} | "
            f"streak {result['streak']} | {result['instruction']}"
        )

    def save_results(self) -> None:
        if self.engine is None:
            return
        source = Path(self.path_edit.text()) if self.path_edit.text() else Path.cwd() / "game"
        default_dir = source.parent.parent / "game_results" if source.suffix else source
        default_dir.mkdir(parents=True, exist_ok=True)
        default_path = default_dir / f"{source.stem.removesuffix('_features')}_{self.definition.id}_results.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save game results", str(default_path), "JSON (*.json)")
        if not path:
            return
        try:
            save_json_atomic(self.engine.summary().to_document(), path)
            self.status.setText(f"Saved game results to {path}")
        except Exception as exc:
            QMessageBox.warning(self, "Could not save results", f"{type(exc).__name__}: {exc}")
