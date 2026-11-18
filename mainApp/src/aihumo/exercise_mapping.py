"""Interpretable exercise mapping built on the saved AIHuMo feature schema.

The mapper is intentionally conservative.  It combines temporal trajectories,
normalised landmarks, distances and motion derivatives; a single moving joint
is never sufficient evidence for a classification.  Registry entries are
derived from :mod:`aihumo.exercise_library` and can be replaced or extended by
loading a JSON file with the same ``exerciseId``/``signatures`` shape.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .exercise_library import starter_library

REGISTRY_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ExerciseSignature:
    exercise_id: str
    name: str
    family: str
    primary_joints: tuple[str, ...] = ()
    secondary_joints: tuple[str, ...] = ()
    angle_patterns: tuple[str, ...] = ()
    landmark_patterns: tuple[str, ...] = ()
    distance_patterns: tuple[str, ...] = ()
    motion_patterns: tuple[str, ...] = ()
    angle_trajectories: tuple[str, ...] = ()
    landmark_trajectories: tuple[str, ...] = ()
    distance_trajectories: tuple[str, ...] = ()
    coordination: tuple[str, ...] = ()
    phases: tuple[str, ...] = ("eccentric", "concentric", "hold")
    distinguishing: tuple[str, ...] = ()
    weights: Mapping[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["weights"] = dict(self.weights)
        return value


@dataclass(frozen=True)
class ExerciseSuggestion:
    exercise_id: str
    name: str
    family: str
    score: float
    uncertainty: float
    evidence: tuple[str, ...] = ()
    matched_features: tuple[str, ...] = ()
    method: str = "trajectory_similarity_v1"
    provisional: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _family_defaults(family: str, exercise_id: str) -> dict[str, Any]:
    """Return broad, explainable expectations shared by related exercises."""
    family = str(family)
    if family == "pull" or "curl" in exercise_id or "row" in exercise_id:
        return {
            "primary_joints": ("elbow", "wrist"),
            "secondary_joints": ("shoulder", "hip"),
            "angle_patterns": ("*elbow", "*shoulder"),
            "landmark_patterns": ("*wrist", "*elbow"),
            "distance_patterns": ("*shoulder_to_wrist", "*wrist_to_wrist"),
            "motion_patterns": ("*wrist*velocity", "*elbow*velocity"),
            "coordination": ("bilateral_or_unilateral_elbow_flexion", "wrist_tracks_elbow"),
            "distinguishing": ("elbow trajectory and wrist-to-shoulder distance are evaluated together",),
            "angle_trajectories": ("elbow flexes and extends periodically",),
            "landmark_trajectories": ("wrist follows the forearm with limited shoulder elevation",),
            "distance_trajectories": ("shoulder-to-wrist distance changes with elbow phase",),
        }
    if family == "push" or "press" in exercise_id:
        return {
            "primary_joints": ("shoulder", "elbow", "wrist"),
            "secondary_joints": ("hip", "torso"),
            "angle_patterns": ("*shoulder", "*elbow"),
            "landmark_patterns": ("*wrist", "*shoulder"),
            "distance_patterns": ("*shoulder_to_wrist", "*wrist_to_wrist"),
            "motion_patterns": ("*wrist*velocity", "*shoulder*velocity"),
            "coordination": ("wrist_and_shoulder_elevate_together", "torso_remains_stable"),
            "distinguishing": ("shoulder elevation and wrist height separate a press from a curl",),
            "angle_trajectories": ("shoulder and elbow angles change together during elevation",),
            "landmark_trajectories": ("wrist rises above the shoulder during the concentric phase",),
            "distance_trajectories": ("wrist-to-shoulder distance increases during press",),
        }
    if family in {"squat", "lunge", "jump_conditioning"}:
        return {
            "primary_joints": ("hip", "knee", "ankle"),
            "secondary_joints": ("torso",),
            "angle_patterns": ("*knee", "*hip", "torso*"),
            "landmark_patterns": ("*hip", "*knee", "*ankle"),
            "distance_patterns": ("*knee_to_knee", "*hip_to_ankle"),
            "motion_patterns": ("*knee*velocity", "*hip*velocity"),
            "coordination": ("bilateral_lower_limb_flexion", "hip_and_knee_phase_lock"),
            "distinguishing": ("hip/knee flexion and bilateral symmetry are evaluated over a full cycle",),
            "angle_trajectories": ("hip and knee flexion share a lower-body cycle",),
            "landmark_trajectories": ("hip descends relative to the torso and ankles",),
            "distance_trajectories": ("hip-to-ankle and bilateral knee distances change coherently",),
        }
    if family == "hinge":
        return {
            "primary_joints": ("hip", "knee", "torso"),
            "secondary_joints": ("ankle",),
            "angle_patterns": ("*hip", "*knee", "torso*"),
            "landmark_patterns": ("*hip", "*shoulder", "*ankle"),
            "distance_patterns": ("*hip_to_ankle", "*shoulder_to_wrist"),
            "motion_patterns": ("*hip*velocity", "*torso*velocity"),
            "coordination": ("hip_dominant_motion", "torso_changes_without_large_knee_excursion"),
            "distinguishing": ("hip/torso trajectory is weighted more than isolated knee motion",),
            "angle_trajectories": ("hip angle changes with comparatively smaller knee excursion",),
            "landmark_trajectories": ("shoulder and torso move forward over a stable foot base",),
            "distance_trajectories": ("hip-to-ankle distance remains coordinated with torso angle",),
        }
    if family in {"carry", "core", "rotate"}:
        return {
            "primary_joints": ("torso", "hip"),
            "secondary_joints": ("shoulder", "wrist"),
            "angle_patterns": ("torso*", "*shoulder", "*hip"),
            "landmark_patterns": ("*shoulder", "*hip", "*wrist"),
            "distance_patterns": ("*shoulder_to_wrist", "*hip_to_ankle"),
            "motion_patterns": ("*torso*velocity", "*shoulder*velocity"),
            "coordination": ("trunk_motion_is_consistent",),
            "distinguishing": ("trunk and bilateral coordination are required",),
            "angle_trajectories": ("trunk angles exhibit a repeated or sustained pattern",),
            "landmark_trajectories": ("selected landmarks move as a coordinated body segment",),
            "distance_trajectories": ("relevant distances change consistently across the interval",),
        }
    return {
        "primary_joints": tuple(), "secondary_joints": tuple(),
        "angle_patterns": ("angle_*",), "landmark_patterns": ("n*", "torso_norm_lm*"),
        "distance_patterns": ("distance_*", "review_*distance*"),
        "motion_patterns": ("*_v*", "*_a*", "*_speed"),
        "coordination": ("temporal trajectory similarity",),
        "distinguishing": ("no exercise-specific signature is configured",),
        "angle_trajectories": ("trajectory expectation is not configured",),
        "landmark_trajectories": ("trajectory expectation is not configured",),
        "distance_trajectories": ("trajectory expectation is not configured",),
    }


class ExerciseRegistry:
    """Configurable registry of stable exercise IDs and movement signatures."""

    def __init__(self, signatures: Iterable[ExerciseSignature], *, version: str = REGISTRY_SCHEMA_VERSION):
        self.version = str(version)
        self._signatures = {item.exercise_id: item for item in signatures}

    @classmethod
    def from_existing(cls, path: str | Path | None = None) -> "ExerciseRegistry":
        base = {item["exerciseId"]: item for item in starter_library()["exercises"]}
        overrides: dict[str, dict[str, Any]] = {}
        version = REGISTRY_SCHEMA_VERSION
        if path is not None and Path(path).is_file():
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            version = str(payload.get("schemaVersion", version))
            for item in payload.get("signatures", payload.get("exercises", [])):
                key = item.get("exerciseId", item.get("exercise_id"))
                if key:
                    overrides[str(key)] = item
        signatures = []
        for exercise_id, item in base.items():
            values = _family_defaults(item.get("family", ""), exercise_id)
            values.update({key: value for key, value in overrides.get(exercise_id, {}).items() if key not in {"exerciseId", "exercise_id"}})
            signatures.append(ExerciseSignature(
                exercise_id=exercise_id,
                name=str(item.get("name", exercise_id.replace("_", " ").title())),
                family=str(item.get("family", "other")),
                primary_joints=tuple(values.get("primary_joints", values.get("primaryJoints", ()))),
                secondary_joints=tuple(values.get("secondary_joints", values.get("secondaryJoints", ()))),
                angle_patterns=tuple(values.get("angle_patterns", values.get("anglePatterns", ()))),
                landmark_patterns=tuple(values.get("landmark_patterns", values.get("landmarkPatterns", ()))),
                distance_patterns=tuple(values.get("distance_patterns", values.get("distancePatterns", ()))),
                motion_patterns=tuple(values.get("motion_patterns", values.get("motionPatterns", ()))),
                angle_trajectories=tuple(values.get("angle_trajectories", values.get("angleTrajectories", ()))),
                landmark_trajectories=tuple(values.get("landmark_trajectories", values.get("landmarkTrajectories", ()))),
                distance_trajectories=tuple(values.get("distance_trajectories", values.get("distanceTrajectories", ()))),
                coordination=tuple(values.get("coordination", ())),
                phases=tuple(values.get("phases", values.get("movementPhases", ("eccentric", "concentric", "hold")))),
                distinguishing=tuple(values.get("distinguishing", ())),
                weights=dict(values.get("weights", {})),
            ))
        for exercise_id, item in overrides.items():
            if exercise_id in base:
                continue
            values = _family_defaults(item.get("family", "other"), exercise_id)
            values.update(item)
            signatures.append(ExerciseSignature(
                exercise_id=exercise_id, name=str(item.get("name", exercise_id.replace("_", " ").title())),
                family=str(item.get("family", "other")),
                primary_joints=tuple(values.get("primary_joints", values.get("primaryJoints", ()))),
                secondary_joints=tuple(values.get("secondary_joints", values.get("secondaryJoints", ()))),
                angle_patterns=tuple(values.get("angle_patterns", values.get("anglePatterns", ()))),
                landmark_patterns=tuple(values.get("landmark_patterns", values.get("landmarkPatterns", ()))),
                distance_patterns=tuple(values.get("distance_patterns", values.get("distancePatterns", ()))),
                motion_patterns=tuple(values.get("motion_patterns", values.get("motionPatterns", ()))),
                angle_trajectories=tuple(values.get("angle_trajectories", values.get("angleTrajectories", ()))),
                landmark_trajectories=tuple(values.get("landmark_trajectories", values.get("landmarkTrajectories", ()))),
                distance_trajectories=tuple(values.get("distance_trajectories", values.get("distanceTrajectories", ()))),
                coordination=tuple(values.get("coordination", ())), phases=tuple(values.get("phases", ("eccentric", "concentric", "hold"))),
                distinguishing=tuple(values.get("distinguishing", ())), weights=dict(values.get("weights", {})),
            ))
        return cls(signatures, version=version)

    @classmethod
    def from_json(cls, path: str | Path) -> "ExerciseRegistry":
        return cls.from_existing(path)

    load = from_json

    @property
    def signatures(self) -> tuple[ExerciseSignature, ...]:
        return self.all()

    def all(self) -> tuple[ExerciseSignature, ...]:
        return tuple(self._signatures.values())

    def get(self, exercise_id: str) -> ExerciseSignature | None:
        return self._signatures.get(str(exercise_id))

    def to_dict(self) -> dict[str, Any]:
        return {"schemaVersion": self.version, "signatures": [item.to_dict() for item in self.all()]}


def _numeric(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    present = [name for name in columns if name in df.columns]
    if not present:
        return pd.DataFrame(index=df.index)
    values = df[present].apply(pd.to_numeric, errors="coerce")
    return values.interpolate(limit_direction="both").ffill().bfill()


def _resample(values: np.ndarray, points: int = 32) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.ndim == 1:
        values = values[:, None]
    if len(values) == 0:
        return np.zeros((points, values.shape[1]), dtype=float)
    x_old = np.linspace(0.0, 1.0, len(values))
    x_new = np.linspace(0.0, 1.0, points)
    return np.column_stack([np.interp(x_new, x_old, np.nan_to_num(values[:, i], nan=0.0)) for i in range(values.shape[1])])


def _dtw_distance(first: np.ndarray, second: np.ndarray) -> float:
    first = np.asarray(first, dtype=float); second = np.asarray(second, dtype=float)
    if first.ndim == 1: first = first[:, None]
    if second.ndim == 1: second = second[:, None]
    cost = np.full((len(first) + 1, len(second) + 1), np.inf, dtype=float); cost[0, 0] = 0.0
    for i in range(1, len(first) + 1):
        local = np.linalg.norm(first[i - 1, None, :] - second, axis=1)
        cost[i, 1:] = local + np.minimum(cost[i - 1, :-1], np.minimum(cost[i - 1, 1:], cost[i, :-1]))
    return float(cost[-1, -1] / max(len(first) + len(second), 1))


def _columns_for(signature: ExerciseSignature, columns: Iterable[str], category: str) -> list[str]:
    columns = list(columns)
    patterns = getattr(signature, category)
    if not patterns:
        return []
    result = []
    for column in columns:
        lower = column.lower()
        if category == "angle_patterns" and not lower.startswith(("angle_", "review_omega_", "review_alpha_")):
            continue
        if category == "landmark_patterns" and not lower.startswith(("lm", "n", "world", "torso_norm_lm", "hip_norm_lm", "shoulder_norm_lm", "torso_length_norm_lm", "body_aligned_lm")):
            continue
        if category == "distance_patterns" and "distance" not in lower:
            continue
        if category == "motion_patterns" and not ("_v" in lower or "_a" in lower or lower.endswith("_speed") or "velocity" in lower or "acceleration" in lower):
            continue
        if any(pattern.lower().replace("*", "") in lower for pattern in patterns):
            result.append(column)
    return result


def _feature_matrix(df: pd.DataFrame, signature: ExerciseSignature, *, include_motion: bool = True) -> tuple[np.ndarray, list[str]]:
    groups = ["angle_patterns", "landmark_patterns", "distance_patterns"]
    if include_motion:
        groups.append("motion_patterns")
    selected = []
    for group in groups:
        selected.extend(_columns_for(signature, df.columns, group))
    selected = list(dict.fromkeys(selected))
    if not selected:
        return np.zeros((len(df), 1)), []
    values = _numeric(df, selected).to_numpy(dtype=float)
    values = np.nan_to_num(values, nan=0.0)
    scale = np.nanpercentile(np.abs(values), 75, axis=0)
    scale[~np.isfinite(scale) | (scale < 1e-6)] = 1.0
    return values / scale, selected


def _periodicity_score(df: pd.DataFrame) -> float:
    if len(df) < 8:
        return 0.0
    candidates = [name for name in df.columns if name.startswith("angle_") or name.endswith("_speed")]
    if not candidates:
        return 0.0
    signal = pd.to_numeric(df[candidates[0]], errors="coerce").interpolate(limit_direction="both").to_numpy(float).copy()
    signal -= np.mean(signal)
    if np.std(signal) < 1e-8:
        return 0.0
    corr = np.correlate(signal, signal, mode="full")[len(signal) - 1:]
    corr /= max(corr[0], 1e-9)
    return float(np.max(corr[2:]) if len(corr) > 2 else 0.0)


def _joint_activity(df: pd.DataFrame, joint: str) -> float:
    columns = [name for name in df.columns if joint in str(name).lower() and str(name).lower().startswith(("angle_", "n", "lm", "world", "torso_norm_lm"))]
    if not columns:
        return 0.0
    values = df[columns].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    return float(np.nanmedian(np.nanstd(values, axis=0))) if np.isfinite(values).any() else 0.0


def _cue_bonus(df: pd.DataFrame, signature: ExerciseSignature) -> float:
    elbow = _joint_activity(df, "elbow"); shoulder = _joint_activity(df, "shoulder")
    hip = _joint_activity(df, "hip"); knee = _joint_activity(df, "knee"); wrist = _joint_activity(df, "wrist")
    if "curl" in signature.exercise_id:
        return 0.22 if elbow > max(shoulder * 1.35, 1e-6) else 0.0
    if "press" in signature.exercise_id or signature.family == "push":
        return 0.16 if shoulder > max(elbow * 0.85, 1e-6) and wrist > 0 else 0.0
    if signature.family in {"squat", "lunge", "jump_conditioning"}:
        return 0.12 if max(hip, knee) > max(elbow, shoulder) else 0.0
    if signature.family == "hinge":
        return 0.12 if hip > max(knee * 0.8, 1e-6) else 0.0
    return 0.0


def rank_exercises(
    frame_df: pd.DataFrame,
    registry: ExerciseRegistry | None = None,
    *,
    interval: tuple[int, int] | None = None,
    confirmed_examples: Mapping[str, Iterable[pd.DataFrame]] | None = None,
    top_k: int = 5,
) -> list[ExerciseSuggestion]:
    """Return ranked, provisional suggestions with human-readable evidence."""
    if frame_df is None or frame_df.empty:
        return []
    df = frame_df
    if interval is not None and "frame_id" in df:
        first, last = interval
        df = df[(pd.to_numeric(df["frame_id"], errors="coerce") >= first) & (pd.to_numeric(df["frame_id"], errors="coerce") <= last)]
    if df.empty:
        return []
    registry = registry or ExerciseRegistry.from_existing()
    rows: list[ExerciseSuggestion] = []
    for signature in registry.all():
        matrix, columns = _feature_matrix(df, signature)
        trajectory = _resample(matrix)
        baseline = float(np.mean(np.linalg.norm(np.diff(trajectory, axis=0), axis=1))) if len(trajectory) > 1 else 0.0
        # A signature with no observable columns is an abstention, not a
        # perfect match.  This prevents an old/partial Parquet from ranking
        # every unrelated exercise above a signature it can actually assess.
        coverage = min(1.0, len(columns) / 4.0)
        score = ((0.35 * coverage + 0.65 / (1.0 + baseline)) + _cue_bonus(df, signature)) if columns else 0.05
        score = float(np.clip(score, 0.0, 1.0))
        method = "trajectory_similarity_v1"
        if confirmed_examples and signature.exercise_id in confirmed_examples:
            examples = list(confirmed_examples[signature.exercise_id])
            if examples:
                distances = []
                for example in examples[:20]:
                    ex_matrix, _ = _feature_matrix(example, signature)
                    distances.append(_dtw_distance(trajectory, _resample(ex_matrix)))
                if distances:
                    score = 1.0 / (1.0 + float(np.mean(distances)))
                    method = "dtw_nearest_confirmed_v1"
        evidence = list(signature.distinguishing[:2])
        if columns:
            evidence.append(f"matched {len(columns)} saved feature columns")
        if _periodicity_score(df) > 0.35:
            evidence.append("periodic trajectory detected")
        uncertainty = float(np.clip(1.0 - score, 0.0, 1.0))
        rows.append(ExerciseSuggestion(signature.exercise_id, signature.name, signature.family, float(score), uncertainty, tuple(evidence), tuple(columns), method))
    rows.sort(key=lambda item: item.score, reverse=True)
    return rows[:max(1, int(top_k))]


def infer_parent_intervals(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Infer provisional activity/set parents from repetition timestamps."""
    items = [dict(item) for item in rows]
    reps = [item for item in items if item.get("annotation_type") == "rep" and item.get("start_frame") is not None]
    if not reps:
        return []
    start = min(int(item["start_frame"]) for item in reps); end = max(int(item["end_frame"]) for item in reps)
    exercise = next((item.get("exercise") for item in reps if item.get("exercise")), None)
    return [
        {"annotation_type": "activity_state", "activity_state": "active", "start_frame": start, "end_frame": end,
         "exercise": exercise, "provisional": True, "source": "exercise_mapping"},
        {"annotation_type": "set", "set_id": 1, "start_frame": start, "end_frame": end,
         "exercise": exercise, "provisional": True, "source": "exercise_mapping"},
    ]


def validate_annotation_hierarchy(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Report hierarchy conflicts without mutating annotations."""
    items = [dict(item) for item in rows]
    issues: list[str] = []
    activities = [item for item in items if item.get("annotation_type") == "activity_state" and item.get("activity_state") == "active"]
    sets = [item for item in items if item.get("annotation_type") == "set"]
    reps = [item for item in items if item.get("annotation_type") == "rep"]
    def contained(child, parents):
        return any(int(parent.get("start_frame", 0)) <= int(child.get("start_frame", 0)) and int(child.get("end_frame", 0)) <= int(parent.get("end_frame", -1)) for parent in parents)
    for item in sets + reps:
        if not contained(item, activities):
            issues.append(f"{item.get('annotation_id', item.get('annotation_type'))} is outside an active activity interval")
    for rep in reps:
        matching = [item for item in sets if item.get("set_id") == rep.get("set_id")]
        if matching and not contained(rep, matching):
            issues.append(f"{rep.get('annotation_id', 'rep')} is outside its set interval")
    return issues


# Public wording used by the UI and future integrations.
suggest_exercises = rank_exercises

