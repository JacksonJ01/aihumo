"""Pure movement-game backend shared by all desktop game workspaces.

The backend consumes AIHuMo's canonical processed feature table.  It has no Qt
dependency, never reruns pose estimation, and keeps preview/seek operations
separate from committed game-loop scoring.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from pathlib import Path
import random
from typing import Any

import numpy as np
import pandas as pd


TIME_COLUMNS = ("timeElapsedS", "timestamp_s", "time_elapsed_s")


class LoopState(str, Enum):
    READY = "ready"
    CALIBRATING = "calibrating"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


@dataclass(frozen=True)
class GameDefinition:
    id: str
    title: str
    category: str
    rule: str
    description: str
    objective: str
    difficulty: str = "adaptive"
    feedback: str = "score"
    target_period_s: float = 1.25
    tolerance: float = 0.24
    calibration_s: float = 1.0
    grid: tuple[int, int] = (3, 2)

    @classmethod
    def from_dict(cls, item: dict[str, Any]) -> "GameDefinition":
        values = dict(item)
        if "grid" in values:
            values["grid"] = tuple(values["grid"])
        definition = cls(**values)
        if len(definition.grid) != 2 or min(definition.grid) < 1:
            raise ValueError(f"Game {definition.id!r} needs a positive [columns, rows] grid.")
        if definition.target_period_s <= 0 or definition.tolerance <= 0 or definition.calibration_s < 0:
            raise ValueError(f"Game {definition.id!r} has invalid timing or tolerance settings.")
        return definition


def load_game_definitions(path: str | Path) -> tuple[GameDefinition, ...]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    definitions = tuple(GameDefinition.from_dict(item) for item in payload["games"])
    ids = [definition.id for definition in definitions]
    if len(ids) != len(set(ids)):
        raise ValueError("Movement game IDs must be unique.")
    return definitions


@dataclass(frozen=True)
class GameEvent:
    kind: str
    frame: int
    time_s: float
    target_slot: int
    value: float | None = None
    detail: str = ""


@dataclass
class SessionSummary:
    game_id: str
    state: str
    samples: int
    average_score: float
    success_rate: float
    max_streak: int
    duration_s: float
    reaction_times_s: list[float] = field(default_factory=list)
    events: list[GameEvent] = field(default_factory=list)

    def to_document(self) -> dict[str, Any]:
        document = asdict(self)
        document["version"] = 1
        return document


class MovementSignals:
    """Validated, normalized signals derived once from a canonical feature table."""

    def __init__(self, frame: pd.DataFrame):
        if frame.empty:
            raise ValueError("A movement game needs at least one feature row.")
        time_name = "_game_time_s" if "_game_time_s" in frame else next(
            (name for name in TIME_COLUMNS if name in frame), None
        )
        frame_name = "_game_frame_id" if "_game_frame_id" in frame else "frame_id"
        if time_name is None or frame_name not in frame:
            raise ValueError("Movement features need frame IDs and source timestamps.")
        self.frame = frame
        self.times = pd.to_numeric(frame[time_name], errors="coerce").to_numpy(dtype=float)
        self.frame_ids = pd.to_numeric(frame[frame_name], errors="coerce").to_numpy(dtype=float)
        if (not np.isfinite(self.times).all() or not np.isfinite(self.frame_ids).all()
                or (len(self.times) > 1 and np.any(np.diff(self.times) <= 0))):
            raise ValueError("Game timestamps and frame IDs must be finite and strictly increasing.")
        self.frame_ids = self.frame_ids.astype(int)
        self.position_columns = self._find_position_columns()
        self.positions = self._normalised_positions()
        self.position_speed = self._position_speed()
        self.angle_columns = self._preferred_angle_columns()
        self.angles = self._angles()
        self.angle_speed = self._angle_speed()
        self.confidence = self._confidence()
        self.bilateral_pairs = self._bilateral_pairs()

    def _find_position_columns(self) -> tuple[str | None, str | None]:
        candidates = (
            ("review_torso2d_hip_midpoint_x", "review_torso2d_hip_midpoint_y"),
            ("review_projected_hip_midpoint_x", "review_projected_hip_midpoint_y"),
            ("review_torso2d_lm0_x", "review_torso2d_lm0_y"),
            ("review_projected_lm0_x", "review_projected_lm0_y"),
        )
        for pair in candidates:
            if all(name in self.frame for name in pair):
                return pair
        x_name = next((name for name in self.frame if "hip_midpoint_x" in name or name.endswith("lm0_x")), None)
        y_name = next((name for name in self.frame if "hip_midpoint_y" in name or name.endswith("lm0_y")), None)
        return x_name, y_name

    def _normalised_positions(self) -> np.ndarray:
        x_name, y_name = self.position_columns
        if not x_name or not y_name:
            return np.full((len(self.frame), 2), 0.5, dtype=float)
        values = self.frame[[x_name, y_name]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float, copy=True)
        for axis in range(2):
            column = values[:, axis]
            finite = np.isfinite(column)
            if not finite.any():
                values[:, axis] = 0.5
                continue
            low, high = np.nanpercentile(column[finite], [2, 98])
            span = max(float(high - low), 1e-9)
            fill = float(np.nanmedian(column[finite]))
            values[:, axis] = np.clip((np.nan_to_num(column, nan=fill) - low) / span, 0, 1)
        return values

    def _position_speed(self) -> np.ndarray:
        if len(self.times) < 2:
            return np.zeros(len(self.times), dtype=float)
        derivatives = np.gradient(self.positions, self.times, axis=0, edge_order=1)
        return np.linalg.norm(np.nan_to_num(derivatives), axis=1)

    def _preferred_angle_columns(self) -> list[str]:
        for prefix in ("angle_3d_", "angle_torso2d_", "angle_2d_", "angle_"):
            columns = [name for name in self.frame if name.startswith(prefix)]
            if columns:
                return columns
        return [name for name in self.frame if name.startswith("review_cross_mean_angle_")]

    def _angles(self) -> np.ndarray:
        if not self.angle_columns:
            return np.empty((len(self.frame), 0), dtype=float)
        values = self.frame[self.angle_columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float, copy=True)
        medians = np.nanmedian(values, axis=0)
        medians = np.where(np.isfinite(medians), medians, 90.0)
        missing = ~np.isfinite(values)
        values[missing] = np.take(medians, np.where(missing)[1])
        return np.clip(values, 0.0, 180.0)

    def _angle_speed(self) -> np.ndarray:
        if self.angles.shape[1] == 0 or len(self.times) < 2:
            return np.zeros(len(self.times), dtype=float)
        derivative = np.gradient(self.angles, self.times, axis=0, edge_order=1)
        return np.nanmean(np.abs(derivative), axis=1)

    def _confidence(self) -> np.ndarray:
        if "pose_present" in self.frame:
            return np.clip(pd.to_numeric(self.frame["pose_present"], errors="coerce").fillna(0).to_numpy(dtype=float), 0, 1)
        columns = [name for name in self.frame if name.endswith(("_visibility", "_presence"))]
        if columns:
            values = self.frame[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
            return np.clip(np.nanmean(values, axis=1), 0, 1)
        return np.ones(len(self.frame), dtype=float)

    def _bilateral_pairs(self) -> list[tuple[int, int]]:
        index = {name: i for i, name in enumerate(self.angle_columns)}
        pairs = []
        for name, left_index in index.items():
            if "left_" not in name:
                continue
            right_name = name.replace("left_", "right_", 1)
            if right_name in index:
                pairs.append((left_index, index[right_name]))
        return pairs


class MovementGameEngine:
    """Deterministic stateful loop for every configured movement game."""

    def __init__(self, definition: GameDefinition, frame: pd.DataFrame, *, seed: int = 17,
                 difficulty: str = "adaptive", partner_frame: pd.DataFrame | None = None):
        self.definition = definition
        self.frame = frame
        self.signals = MovementSignals(frame)
        self.partner_signals = MovementSignals(partner_frame) if partner_frame is not None else None
        self.rng = random.Random(seed)
        self.difficulty = difficulty
        self.state = LoopState.READY
        self.index = 0
        self.total_score = 0.0
        self.samples = 0
        self.successes = 0
        self.streak = 0
        self.max_streak = 0
        self.events: list[GameEvent] = []
        self.reaction_times: list[float] = []
        self._scored_frames: set[int] = set()
        self._hit_slots: set[int] = set()
        self._sequence_progress = 0
        self._targets = self._build_targets()
        self._calibration_end = self._calibration_end_index()
        self._pose_reference = self._reference_pose()

    @property
    def times(self) -> np.ndarray:
        return self.signals.times

    @property
    def frame_count(self) -> int:
        return len(self.frame)

    @property
    def is_finished(self) -> bool:
        return self.state == LoopState.COMPLETED

    @property
    def calibration_frames(self) -> int:
        return self._calibration_end + 1

    def _calibration_end_index(self) -> int:
        duration = max(0.0, float(self.times[-1] - self.times[0]))
        # Keep calibration useful for short clips without consuming the whole
        # session. Long recordings use the configured duration; short ones use
        # at most the first 15 percent.
        calibration_s = min(self.definition.calibration_s, duration * 0.15)
        limit = self.times[0] + calibration_s
        return int(np.clip(np.searchsorted(self.times, limit, side="right") - 1, 0, self.frame_count - 1))

    def _reference_pose(self) -> np.ndarray:
        if self.signals.angles.shape[1] == 0:
            return np.empty(0, dtype=float)
        return np.nanmedian(self.signals.angles[:self._calibration_end + 1], axis=0)

    def _difficulty_factor(self) -> float:
        return {"easy": 1.30, "medium": 1.0, "hard": 0.72, "adaptive": 1.0}.get(self.difficulty, 1.0)

    def _build_targets(self) -> list[tuple[float, float]]:
        columns, rows = self.definition.grid
        centers = [((column + 0.5) / columns, (row + 0.5) / rows)
                   for row in range(rows) for column in range(columns)]
        duration = max(0.0, float(self.times[-1] - self.times[0]))
        count = max(1, int(np.ceil(duration / self.definition.target_period_s)) + 1)
        targets = []
        previous = None
        for _ in range(count):
            choices = [center for center in centers if center != previous] or centers
            previous = self.rng.choice(choices)
            targets.append(previous)
        return targets

    def _target_slot(self, index: int) -> int:
        elapsed = max(0.0, float(self.times[index] - self.times[0]))
        return min(len(self._targets) - 1, int(elapsed / self.definition.target_period_s))

    def target(self, index: int | None = None) -> tuple[float, float]:
        index = self.index if index is None else int(np.clip(index, 0, self.frame_count - 1))
        return self._targets[self._target_slot(index)]

    def start(self, *, from_index: int | None = None) -> None:
        if self.state == LoopState.COMPLETED:
            self.reset()
        if from_index is not None:
            self.index = int(np.clip(from_index, 0, self.frame_count - 1))
        self.state = LoopState.CALIBRATING if self.index <= self._calibration_end else LoopState.RUNNING

    def pause(self) -> None:
        if self.state in (LoopState.RUNNING, LoopState.CALIBRATING):
            self.state = LoopState.PAUSED

    def resume(self) -> None:
        if self.state in (LoopState.PAUSED, LoopState.READY):
            self.state = LoopState.CALIBRATING if self.index <= self._calibration_end else LoopState.RUNNING

    def reset(self) -> None:
        self.state = LoopState.READY
        self.index = 0
        self.total_score = 0.0
        self.samples = 0
        self.successes = 0
        self.streak = 0
        self.max_streak = 0
        self.events.clear()
        self.reaction_times.clear()
        self._scored_frames.clear()
        self._hit_slots.clear()
        self._sequence_progress = 0

    def seek(self, index: int) -> dict[str, Any]:
        self.index = int(np.clip(index, 0, self.frame_count - 1))
        return self.preview(self.index)

    def preview(self, index: int | None = None) -> dict[str, Any]:
        return self.evaluate(index, commit=False)

    def step(self, index: int | None = None) -> dict[str, Any]:
        if self.state not in (LoopState.RUNNING, LoopState.CALIBRATING):
            raise RuntimeError("The movement game must be running before a frame can be scored.")
        next_index = min(self.index + 1, self.frame_count - 1) if index is None else index
        result = self.evaluate(next_index, commit=True)
        if self.state == LoopState.CALIBRATING and self.index >= self._calibration_end:
            self.state = LoopState.RUNNING
            result["state"] = self.state.value
        if self.index >= self.frame_count - 1:
            self.state = LoopState.COMPLETED
            result["state"] = self.state.value
        return result

    def evaluate(self, index: int | None = None, *, commit: bool = False) -> dict[str, Any]:
        index = self.index if index is None else int(np.clip(index, 0, self.frame_count - 1))
        self.index = index
        score, success, instruction, reaction = self._score(index)
        calibrating = index <= self._calibration_end
        if calibrating:
            instruction = "Calibration: move through a comfortable range"
        score *= float(self.signals.confidence[index])
        score = float(np.clip(score, 0.0, 1.0))
        slot = self._target_slot(index)
        committed = bool(commit and not calibrating and index not in self._scored_frames)
        if committed:
            self._scored_frames.add(index)
            self.samples += 1
            self.total_score += score
            self.successes += int(success)
            self.streak = self.streak + 1 if success else 0
            self.max_streak = max(self.max_streak, self.streak)
            if self.definition.rule == "sequence" and success:
                self._sequence_progress = max(self._sequence_progress, slot + 1)
            if reaction is not None and slot not in self._hit_slots:
                self._hit_slots.add(slot)
                self.reaction_times.append(reaction)
                self.events.append(GameEvent("target_hit", int(self.signals.frame_ids[index]),
                                             float(self.times[index]), slot, reaction, instruction))
        return {
            "frame": int(self.signals.frame_ids[index]),
            "time_s": float(self.times[index]),
            "position": tuple(float(value) for value in self.signals.positions[index]),
            "target": tuple(float(value) for value in self._display_target(index)),
            "target_slot": slot,
            "score": score,
            "success": bool(success),
            "average": self.total_score / max(1, self.samples),
            "success_rate": self.successes / max(1, self.samples),
            "streak": self.streak,
            "instruction": instruction,
            "reaction_s": reaction,
            "confidence": float(self.signals.confidence[index]),
            "calibrating": calibrating,
            "committed": committed,
            "state": self.state.value,
        }

    def _display_target(self, index: int) -> np.ndarray:
        if self.definition.rule == "path_follow":
            return self._path_target(index)
        if self.definition.rule in {
            "mirror", "partner", "freeze_pose", "rhythm", "balance", "rehab", "ergonomics", "gait"
        }:
            return np.asarray((0.5, 0.5))
        return np.asarray(self.target(index), dtype=float)

    def _score(self, index: int) -> tuple[float, bool, str, float | None]:
        rule = self.definition.rule
        position = self.signals.positions[index]
        target = np.asarray(self.target(index), dtype=float)
        distance = float(np.linalg.norm(position - target))
        tolerance = self.definition.tolerance * self._difficulty_factor()
        slot = self._target_slot(index)
        slot_start = self.times[0] + slot * self.definition.target_period_s
        reaction = max(0.0, float(self.times[index] - slot_start)) if distance <= tolerance else None

        if rule in {"target_grid", "target_grid_12", "reaction_targets"}:
            score = 1.0 - distance / max(tolerance * 2, 1e-6)
            return score, distance <= tolerance, "Enter the highlighted target", reaction
        if rule == "sequence":
            expected = self._sequence_progress
            success = distance <= tolerance and slot >= expected
            return 1.0 - distance / max(tolerance * 2, 1e-6), success, "Follow the target sequence", reaction
        if rule in {"avoid_zone", "obstacle_dodge"}:
            success = distance >= tolerance
            return distance / max(tolerance * 2, 1e-6), success, "Stay outside the danger zone", None
        if rule == "path_follow":
            desired = self._path_target(index)
            error = float(np.linalg.norm(position - desired))
            return 1.0 - error / max(tolerance * 2, 1e-6), error <= tolerance, "Follow the moving path", None
        if rule in {"mirror", "partner"}:
            symmetry = self._symmetry_score(index)
            return symmetry, symmetry >= 0.72, "Match left and right movement timing", None
        if rule == "freeze_pose":
            pose_score = self._pose_score(index)
            stability = max(0.0, 1.0 - self.signals.position_speed[index] / 1.5)
            score = 0.65 * pose_score + 0.35 * stability
            return score, score >= 0.75, "Hold the reference pose", None
        if rule == "rhythm":
            beat_phase = ((self.times[index] - self.times[0]) % self.definition.target_period_s) / self.definition.target_period_s
            beat_distance = min(beat_phase, 1.0 - beat_phase)
            movement = min(1.0, self.signals.position_speed[index] / 1.5)
            score = 0.55 * (1.0 - beat_distance * 2.0) + 0.45 * movement
            return score, score >= 0.65, "Move on the beat", None
        if rule == "balance":
            center_error = float(np.linalg.norm(position - np.asarray((0.5, 0.5))))
            sway = min(1.0, self.signals.position_speed[index] / 1.2)
            score = 1.0 - min(1.0, center_error * 1.5 + sway * 0.4)
            return score, score >= 0.7, "Keep your center stable", None
        if rule == "sports_reaction":
            reach = 1.0 - distance / max(tolerance * 2, 1e-6)
            speed_bonus = min(1.0, self.signals.position_speed[index] / 2.0)
            score = 0.75 * reach + 0.25 * speed_bonus
            return score, distance <= tolerance, "Reach, then recover your stance", reaction
        if rule == "rehab":
            pose = self._pose_score(index)
            control = max(0.0, 1.0 - self.signals.angle_speed[index] / 180.0)
            score = 0.6 * pose + 0.4 * control
            return score, score >= 0.72, "Move through the range with control", None
        if rule == "ergonomics":
            risk = self._ergonomic_risk(index)
            return 1.0 - risk, risk <= 0.3, "Maintain a neutral working posture", None
        if rule == "gait":
            symmetry = self._symmetry_score(index)
            cadence = min(1.0, self.signals.angle_speed[index] / 120.0)
            score = 0.7 * symmetry + 0.3 * cadence
            return score, score >= 0.65, "Maintain symmetric, consistent steps", None
        return 0.5, False, "Continue moving", None

    def _path_target(self, index: int) -> np.ndarray:
        phase = 2 * np.pi * (self.times[index] - self.times[0]) / max(self.definition.target_period_s * 4, 1e-6)
        return np.asarray((0.5 + 0.32 * np.sin(phase), 0.5 + 0.24 * np.sin(phase * 2)))

    def _pose_score(self, index: int) -> float:
        if self._pose_reference.size == 0:
            return max(0.0, 1.0 - float(np.linalg.norm(
                self.signals.positions[index] - self.signals.positions[self._calibration_end]
            )) * 2.0)
        error = float(np.nanmean(np.abs(self.signals.angles[index] - self._pose_reference)))
        return max(0.0, 1.0 - error / 45.0)

    def _symmetry_score(self, index: int) -> float:
        if self.partner_signals is not None:
            partner_index = int(np.clip(
                np.searchsorted(self.partner_signals.times, self.times[index], side="left"),
                0, len(self.partner_signals.times) - 1,
            ))
            primary_columns = {name: column for column, name in enumerate(self.signals.angle_columns)}
            partner_columns = {name: column for column, name in enumerate(self.partner_signals.angle_columns)}
            common = sorted(primary_columns.keys() & partner_columns.keys())
            if common:
                errors = [abs(
                    self.signals.angles[index, primary_columns[name]]
                    - self.partner_signals.angles[partner_index, partner_columns[name]]
                ) for name in common]
                angle_score = max(0.0, 1.0 - float(np.mean(errors)) / 60.0)
            else:
                angle_score = 0.5
            position_error = float(np.linalg.norm(
                self.signals.positions[index] - self.partner_signals.positions[partner_index]
            ))
            return float(np.clip(0.75 * angle_score + 0.25 * (1.0 - position_error), 0.0, 1.0))
        if not self.signals.bilateral_pairs:
            center_error = abs(float(self.signals.positions[index, 0]) - 0.5)
            return max(0.0, 1.0 - center_error * 2.0)
        errors = [abs(self.signals.angles[index, left] - self.signals.angles[index, right])
                  for left, right in self.signals.bilateral_pairs]
        return max(0.0, 1.0 - float(np.mean(errors)) / 60.0)

    def _ergonomic_risk(self, index: int) -> float:
        if self.signals.angles.shape[1] == 0:
            return min(1.0, self.signals.position_speed[index] / 2.0)
        names = self.signals.angle_columns
        selected = [i for i, name in enumerate(names)
                    if any(token in name for token in ("torso_vertical", "torso_nose", "hip"))]
        values = self.signals.angles[index, selected or range(self.signals.angles.shape[1])]
        deviation = np.minimum(np.abs(values - 90.0), np.abs(values - 180.0))
        return float(np.clip(np.nanmean(deviation) / 75.0, 0.0, 1.0))

    def summary(self) -> SessionSummary:
        duration = float(self.times[max(self._scored_frames, default=0)] - self.times[0])
        return SessionSummary(
            game_id=self.definition.id,
            state=self.state.value,
            samples=self.samples,
            average_score=self.total_score / max(1, self.samples),
            success_rate=self.successes / max(1, self.samples),
            max_streak=self.max_streak,
            duration_s=max(0.0, duration),
            reaction_times_s=list(self.reaction_times),
            events=list(self.events),
        )
