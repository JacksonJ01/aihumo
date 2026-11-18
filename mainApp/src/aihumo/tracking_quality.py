"""Timestamp-aware, non-destructive pose tracking anomaly detection."""
from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd


TRACKING_QUALITY_SCHEMA_VERSION = "1.0"
LIMB_EDGES = (
    (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 25), (25, 27), (24, 26), (26, 28),
)


def _timestamps(df: pd.DataFrame) -> np.ndarray:
    values = pd.to_numeric(df.get("timestamp_s"), errors="coerce").to_numpy(dtype=float)
    if len(values) and np.isfinite(values).all() and np.all(np.diff(values) > 0):
        return values
    fps_values = pd.to_numeric(df.get("fps", pd.Series(30.0, index=df.index)), errors="coerce")
    fps = float(fps_values.dropna().median()) if fps_values.notna().any() else 30.0
    return np.arange(len(df), dtype=float) / max(fps, 1e-9)


def _rolling_robust(values: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    series = pd.Series(values)
    median = series.rolling(window, center=True, min_periods=max(3, window // 3)).median()
    deviation = (series - median).abs()
    mad = deviation.rolling(window, center=True, min_periods=max(3, window // 3)).median()
    return median.to_numpy(dtype=float), mad.to_numpy(dtype=float)


def _segments(mask: np.ndarray) -> list[tuple[int, int]]:
    indices = np.flatnonzero(mask)
    if not len(indices):
        return []
    boundaries = np.flatnonzero(np.diff(indices) > 1)
    starts = np.r_[indices[0], indices[boundaries + 1]]
    ends = np.r_[indices[boundaries], indices[-1]]
    return list(zip(starts.tolist(), ends.tolist()))


def _warning_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "TQ-" + hashlib.sha256(encoded).hexdigest()[:14]


def detect_tracking_anomalies(
    df: pd.DataFrame,
    *,
    visibility_threshold: float = 0.35,
    window_seconds: float = 0.75,
    hampel_sigma: float = 6.0,
) -> dict[str, Any]:
    """Return separate quality warnings without changing any feature value.

    Coordinate jumps require corroborating low/changing confidence or unstable
    limb geometry. This intentionally avoids classifying rapid genuine motion
    as a tracking failure solely because velocity is high.
    """
    if df.empty:
        return {
            "schema_version": TRACKING_QUALITY_SCHEMA_VERSION,
            "source": "derived tracking-quality analysis",
            "warnings": [],
            "summary": {"warning_count": 0, "affected_frames": 0},
        }
    timestamps = _timestamps(df)
    frame_ids = pd.to_numeric(
        df.get("frame_id", pd.Series(np.arange(len(df)), index=df.index)), errors="coerce"
    ).fillna(pd.Series(np.arange(len(df)), index=df.index)).astype(int).to_numpy()
    dt = np.diff(timestamps)
    median_dt = float(np.median(dt[dt > 0])) if np.any(dt > 0) else 1 / 30.0
    window = max(5, int(round(window_seconds / max(median_dt, 1e-9))))
    if window % 2 == 0:
        window += 1

    pose_present = pd.to_numeric(
        df.get("pose_present", pd.Series(1, index=df.index)), errors="coerce"
    ).fillna(0).to_numpy() > 0
    landmark_masks: dict[tuple[int, str], np.ndarray] = {}
    landmark_scores: dict[tuple[int, str], np.ndarray] = {}
    coordinate_jump: dict[int, np.ndarray] = {}
    low_confidence: dict[int, np.ndarray] = {}

    for landmark in range(33):
        columns = [f"lm{landmark}_{axis}" for axis in "xyz"]
        if not all(column in df.columns for column in columns):
            continue
        coords = np.column_stack([
            pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)
            for column in columns
        ])
        missing = ~np.isfinite(coords).all(axis=1) | ~pose_present
        visibility = pd.to_numeric(
            df.get(f"lm{landmark}_visibility", pd.Series(np.nan, index=df.index)),
            errors="coerce",
        ).to_numpy(dtype=float)
        presence = pd.to_numeric(
            df.get(f"lm{landmark}_presence", pd.Series(np.nan, index=df.index)),
            errors="coerce",
        ).to_numpy(dtype=float)
        confidence = np.where(np.isfinite(visibility), visibility, presence)
        low = np.isfinite(confidence) & (confidence < visibility_threshold)
        drop = np.r_[False, np.diff(np.nan_to_num(confidence, nan=0.0)) < -0.40]
        delta = np.r_[0.0, np.linalg.norm(np.diff(coords, axis=0), axis=1)]
        median, mad = _rolling_robust(delta, window)
        threshold = median + hampel_sigma * 1.4826 * np.maximum(mad, 1e-5)
        jump = np.isfinite(delta) & (delta > np.maximum(threshold, 0.05))
        coordinate_jump[landmark] = jump
        low_confidence[landmark] = low | drop
        landmark_masks[landmark, "missing_landmark"] = missing
        landmark_scores[landmark, "missing_landmark"] = missing.astype(float)
        landmark_masks[landmark, "low_or_abrupt_confidence"] = low | drop
        landmark_scores[landmark, "low_or_abrupt_confidence"] = np.clip(
            1.0 - np.nan_to_num(confidence, nan=0.0), 0.0, 1.0
        )

    geometry_flags: dict[int, np.ndarray] = {
        landmark: np.zeros(len(df), dtype=bool) for landmark in range(33)
    }
    for first, second in LIMB_EDGES:
        first_columns = [f"lm{first}_{axis}" for axis in "xy"]
        second_columns = [f"lm{second}_{axis}" for axis in "xy"]
        if not all(column in df.columns for column in (*first_columns, *second_columns)):
            continue
        a = np.column_stack([pd.to_numeric(df[column], errors="coerce") for column in first_columns])
        b = np.column_stack([pd.to_numeric(df[column], errors="coerce") for column in second_columns])
        lengths = np.linalg.norm(a - b, axis=1)
        median, mad = _rolling_robust(lengths, window)
        unstable = np.isfinite(lengths) & (
            np.abs(lengths - median) > np.maximum(5.0 * 1.4826 * mad, np.maximum(0.04, median * 0.30))
        )
        geometry_flags[first] |= unstable
        geometry_flags[second] |= unstable

    for landmark, jump in coordinate_jump.items():
        corroborated = jump & (low_confidence[landmark] | geometry_flags[landmark])
        landmark_masks[landmark, "coordinate_discontinuity"] = corroborated
        landmark_scores[landmark, "coordinate_discontinuity"] = np.where(corroborated, 0.85, 0.0)
        landmark_masks[landmark, "inconsistent_limb_geometry"] = geometry_flags[landmark]
        landmark_scores[landmark, "inconsistent_limb_geometry"] = np.where(
            geometry_flags[landmark], 0.75, 0.0
        )

    warnings: list[dict[str, Any]] = []
    affected = np.zeros(len(df), dtype=bool)
    for (landmark, reason), mask in landmark_masks.items():
        score_values = landmark_scores[landmark, reason]
        for start, end in _segments(mask):
            affected[start:end + 1] = True
            payload = {
                "reason": reason,
                "landmark": landmark,
                "start_frame": int(frame_ids[start]),
                "end_frame": int(frame_ids[end]),
                "start_time_s": float(timestamps[start]),
                "end_time_s": float(timestamps[end]),
            }
            warnings.append({
                "warning_id": _warning_id(payload),
                **payload,
                "affected_landmarks": [f"lm{landmark}"],
                "score": float(np.nanmax(score_values[start:end + 1])),
                "classification": "tracking_quality",
                "not_form_error": True,
            })
    warnings.sort(key=lambda item: (item["start_time_s"], item["reason"], item["landmark"]))
    return {
        "schema_version": TRACKING_QUALITY_SCHEMA_VERSION,
        "source": "derived tracking-quality analysis",
        "authoritative_measurements": "feature and landmark Parquet files remain unchanged",
        "parameters": {
            "visibility_threshold": visibility_threshold,
            "window_seconds": window_seconds,
            "hampel_sigma": hampel_sigma,
        },
        "warnings": warnings,
        "summary": {
            "warning_count": len(warnings),
            "affected_frames": int(affected.sum()),
            "affected_fraction": float(affected.mean()),
        },
    }

