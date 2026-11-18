"""Versioned, reproducible movement encodings for confirmed repetitions.

This module writes new artifacts beside the source annotations; it never
rewrites the source feature Parquet or ``annotations.json``.  Numpy SVD keeps
the exporter usable in the standalone build while still exposing the PCA
metrics needed to compare feature groups.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .storage import load_json, save_json_atomic

ENCODING_SCHEMA_VERSION = "1.0"
PCA_TRANSFORM_VERSION = "pca_svd_v1"
FEATURE_GROUPS = ("angles", "angles_distances", "angles_distances_motion")


@dataclass(frozen=True)
class EncodingConfig:
    sample_points: int = 32
    feature_group: str = "angles_distances_motion"
    pca_components: int = 3

    def __post_init__(self):
        if int(self.sample_points) not in (32, 64):
            raise ValueError("sample_points must be 32 or 64")
        if self.feature_group not in FEATURE_GROUPS:
            raise ValueError(f"feature_group must be one of {FEATURE_GROUPS}")


@dataclass(frozen=True)
class PCAResult:
    coordinates: np.ndarray
    components: np.ndarray
    mean: np.ndarray
    explained_variance_ratio: tuple[float, ...]
    reconstruction_error: float
    retrieval_accuracy: float | None


def _resample(values: np.ndarray, points: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.ndim == 1:
        values = values[:, None]
    if len(values) == 0:
        return np.zeros((points, values.shape[1]), dtype=float)
    x_old = np.linspace(0.0, 1.0, len(values))
    x_new = np.linspace(0.0, 1.0, points)
    return np.column_stack([np.interp(x_new, x_old, np.nan_to_num(values[:, i], nan=0.0)) for i in range(values.shape[1])])


def feature_columns(columns: Iterable[str], feature_group: str) -> list[str]:
    columns = list(columns)
    if feature_group not in FEATURE_GROUPS:
        raise ValueError(f"Unknown feature group: {feature_group}")
    angle = [name for name in columns if name.startswith(("angle_", "review_omega_", "review_alpha_"))]
    distance = [name for name in columns if name.startswith(("distance_", "review_legacy_distance_", "review_world_distance_", "review_torso2d_distance_", "review_cross_mean_distance_"))]
    motion = [name for name in columns if ("_v" in name or "_a" in name or name.endswith("_speed") or "distance_rate_" in name or "distance_acceleration_" in name)]
    if feature_group == "angles":
        selected = angle
    elif feature_group == "angles_distances":
        selected = angle + distance
    else:
        selected = angle + distance + motion
    # Keep frame/time metadata out, and avoid accidental duplicate columns.
    return list(dict.fromkeys(selected))


def _pca(matrix: np.ndarray, components: int, labels: list[str] | None = None) -> PCAResult:
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("PCA input must be a 2D matrix")
    if len(matrix) == 0:
        return PCAResult(np.empty((0, 0)), np.empty((0, 0)), np.empty((0,)), (), 0.0, None)
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
    mean = matrix.mean(axis=0)
    centered = matrix - mean
    if len(matrix) == 1:
        coords = np.zeros((1, min(components, matrix.shape[1])))
        return PCAResult(coords, np.zeros((coords.shape[1], matrix.shape[1])), mean, (1.0,), 0.0, None)
    u, singular, vt = np.linalg.svd(centered, full_matrices=False)
    count = max(1, min(int(components), vt.shape[0]))
    components_array = vt[:count]
    coords = centered @ components_array.T
    variance = (singular ** 2) / max(len(matrix) - 1, 1)
    ratio = variance[:count] / max(float(variance.sum()), 1e-12)
    reconstructed = coords @ components_array + mean
    error = float(np.sqrt(np.mean((matrix - reconstructed) ** 2)))
    accuracy = None
    if labels and len(set(labels)) > 1 and len(labels) >= 3:
        # Leave-one-out nearest-neighbour retrieval in the fitted coordinates.
        correct = 0
        for index in range(len(coords)):
            distances = np.linalg.norm(coords - coords[index], axis=1)
            distances[index] = np.inf
            nearest = int(np.argmin(distances))
            correct += int(labels[nearest] == labels[index])
        accuracy = float(correct / len(coords))
    return PCAResult(coords, components_array, mean, tuple(float(value) for value in ratio), error, accuracy)


def _fingerprint(parquet_path: Path, annotation: Mapping[str, Any], config: EncodingConfig, columns: Iterable[str]) -> str:
    payload = {
        "schema": ENCODING_SCHEMA_VERSION, "source": str(parquet_path.resolve()),
        "annotation_id": annotation.get("annotation_id"), "start_frame": annotation.get("start_frame"),
        "end_frame": annotation.get("end_frame"), "config": asdict(config), "columns": list(columns),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def confirmed_repetitions(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in document.get("annotations", [])
            if item.get("annotation_type") == "rep"
            and str(item.get("review_status", "accepted")) not in {"rejected", "pending"}
            and item.get("start_frame") is not None and item.get("end_frame") is not None]


def encode_repetition(df: pd.DataFrame, annotation: Mapping[str, Any], config: EncodingConfig) -> tuple[np.ndarray, list[str]]:
    if df.empty:
        raise ValueError("Cannot encode an empty repetition")
    columns = feature_columns(df.columns, config.feature_group)
    if not columns:
        raise ValueError(f"No saved columns match feature group {config.feature_group!r}")
    values = df[columns].apply(pd.to_numeric, errors="coerce").interpolate(limit_direction="both").ffill().bfill().to_numpy(float)
    sampled = _resample(values, config.sample_points)
    scale = np.nanpercentile(np.abs(sampled), 75, axis=0)
    scale[~np.isfinite(scale) | (scale < 1e-8)] = 1.0
    return (sampled / scale).reshape(-1), columns


def export_movement_encodings(
    parquet_path: str | Path,
    annotation_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    config: EncodingConfig | None = None,
) -> dict[str, Any]:
    """Export all confirmed reps and fit/evaluate PCA for each feature group."""
    parquet_path = Path(parquet_path); annotation_path = Path(annotation_path)
    config = config or EncodingConfig()
    document = load_json(annotation_path)
    source = pd.read_parquet(parquet_path)
    output = Path(output_dir) if output_dir else annotation_path.parent.parent / "movement_atlas"
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "movement_encoding_manifest.json"
    manifest = load_json(manifest_path) if manifest_path.is_file() else {
        "schema_version": ENCODING_SCHEMA_VERSION, "pca_transform_version": PCA_TRANSFORM_VERSION,
        "encodings": [], "transforms": {},
    }
    reps = confirmed_repetitions(document)
    rows: list[dict[str, Any]] = []
    vectors: dict[str, list[np.ndarray]] = {group: [] for group in FEATURE_GROUPS}
    labels: dict[str, list[str]] = {group: [] for group in FEATURE_GROUPS}
    for annotation in reps:
        first = int(annotation["start_frame"]); last = int(annotation["end_frame"])
        segment = source[(pd.to_numeric(source.get("frame_id", pd.Series(range(len(source)))), errors="coerce") >= first) & (pd.to_numeric(source.get("frame_id", pd.Series(range(len(source)))), errors="coerce") <= last)]
        if segment.empty:
            continue
        timestamp_column = next((name for name in ("timestamp_s", "timeElapsedS", "timestamp") if name in segment.columns), None)
        duration = float(annotation.get("duration_s", 0.0) or 0.0)
        if timestamp_column and len(segment) > 1:
            times = pd.to_numeric(segment[timestamp_column], errors="coerce").to_numpy(float)
            if np.isfinite(times).any():
                duration = float(np.nanmax(times) - np.nanmin(times))
        for group in FEATURE_GROUPS:
            group_config = EncodingConfig(config.sample_points, group, config.pca_components)
            try:
                vector, columns = encode_repetition(segment, annotation, group_config)
            except ValueError:
                continue
            fingerprint = _fingerprint(parquet_path, annotation, group_config, columns)
            identity = {"fingerprint": fingerprint, "feature_group": group}
            existing = next((item for item in manifest["encodings"] if item.get("fingerprint") == fingerprint), None)
            row = {
                "fingerprint": fingerprint, "annotation_id": annotation.get("annotation_id"),
                "exercise": annotation.get("exercise"), "family": annotation.get("movement_family"),
                "session_id": annotation.get("session_id", document.get("metadata", {}).get("session_id")),
                "video_id": annotation.get("video_id", document.get("metadata", {}).get("video_id")),
                "source_annotation": str(annotation_path.resolve()), "source_parquet": str(parquet_path.resolve()),
                "start_frame": first, "end_frame": last, "duration_s": duration,
                "sample_points": config.sample_points, "feature_group": group, "feature_columns": columns,
                "vector": vector.tolist(), "provisional": False,
            }
            if existing is None:
                manifest["encodings"].append(row)
            else:
                existing.update(row)
            vectors[group].append(vector); labels[group].append(str(annotation.get("exercise") or "unknown"))
            rows.append(identity)
    metric_report = {}
    for group in FEATURE_GROUPS:
        if vectors[group]:
            matrix = np.vstack(vectors[group])
            result = _pca(matrix, config.pca_components, labels[group])
            manifest["transforms"][group] = {
                "version": PCA_TRANSFORM_VERSION, "sample_points": config.sample_points,
                "feature_group": group, "components": result.components.tolist(), "mean": result.mean.tolist(),
                "explained_variance_ratio": list(result.explained_variance_ratio),
                "reconstruction_error": result.reconstruction_error, "retrieval_accuracy": result.retrieval_accuracy,
                "coordinates": result.coordinates.tolist(), "labels": labels[group],
            }
            metric_report[group] = {"explained_variance_ratio": list(result.explained_variance_ratio), "reconstruction_error": result.reconstruction_error, "retrieval_accuracy": result.retrieval_accuracy}
    if metric_report:
        def metric_key(item):
            value = metric_report[item]
            retrieval = value["retrieval_accuracy"] if value["retrieval_accuracy"] is not None else 0.0
            variance = float(sum(value["explained_variance_ratio"]))
            return (retrieval, variance, -float(value["reconstruction_error"]))
        manifest["recommended_feature_group"] = max(metric_report, key=metric_key)
    else:
        manifest["recommended_feature_group"] = None
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_json_atomic(manifest, manifest_path)
    return {"manifest_path": str(manifest_path), "exported": rows, "metrics": metric_report, "encoding_count": len(manifest["encodings"])}

