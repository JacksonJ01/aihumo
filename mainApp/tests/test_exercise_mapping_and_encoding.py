import json

import numpy as np
import pandas as pd

from aihumo.exercise_mapping import ExerciseRegistry, infer_parent_intervals, rank_exercises, validate_annotation_hierarchy
from aihumo.movement_encoding import EncodingConfig, export_movement_encodings


def _features(rows=48):
    t = np.arange(rows, dtype=float) / 30
    return pd.DataFrame({
        "frame_id": np.arange(rows), "timestamp_s": t,
        "angle_left_elbow": 70 + 50 * np.sin(t * 4),
        "angle_right_elbow": 70 + 50 * np.sin(t * 4),
        "angle_left_shoulder": np.full(rows, 20.0),
        "angle_right_shoulder": np.full(rows, 20.0),
        "n15_x": np.sin(t * 4), "n15_y": np.cos(t * 4),
        "distance_left_shoulder_to_wrist": 0.4 + 0.2 * np.sin(t * 4),
        "n15_vx": np.cos(t * 4), "n15_ax": -np.sin(t * 4),
    })


def test_registry_reuses_existing_exercise_ids_and_is_configurable(tmp_path):
    path = tmp_path / "signatures.json"
    path.write_text(json.dumps({"schemaVersion": "x", "signatures": [{"exerciseId": "biceps_curl", "distinguishing": ["test"]}]}))
    registry = ExerciseRegistry.from_json(path)
    assert registry.get("biceps_curl").exercise_id == "biceps_curl"
    assert registry.get("biceps_curl").distinguishing == ("test",)
    assert registry.get("bodyweight_squat") is not None


def test_mapping_returns_provisional_ranked_evidence():
    suggestions = rank_exercises(_features(), ExerciseRegistry.from_existing(), top_k=5)
    assert suggestions
    assert all(item.provisional and item.evidence for item in suggestions)
    assert all(0 <= item.score <= 1 for item in suggestions)


def test_hierarchy_inference_and_conflict_detection():
    rows = [{"annotation_type": "rep", "start_frame": 10, "end_frame": 20, "exercise": "biceps_curl"}]
    inferred = infer_parent_intervals(rows)
    assert {item["annotation_type"] for item in inferred} == {"activity_state", "set"}
    assert validate_annotation_hierarchy(rows)


def test_pca_export_is_versioned_and_deduplicated(tmp_path):
    features = tmp_path / "video_features.parquet"
    annotations = tmp_path / "video_annotations.json"
    _features().to_parquet(features)
    annotations.write_text(json.dumps({"metadata": {"session_id": "S1", "video_id": "V1"}, "annotations": [{
        "annotation_id": "A1", "annotation_type": "rep", "start_frame": 0, "end_frame": 47,
        "exercise": "biceps_curl", "set_id": 1, "rep_id": 1,
    }]}))
    first = export_movement_encodings(features, annotations, tmp_path / "atlas", config=EncodingConfig())
    second = export_movement_encodings(features, annotations, tmp_path / "atlas", config=EncodingConfig())
    assert first["encoding_count"] == second["encoding_count"] == 3
    manifest = json.loads((tmp_path / "atlas" / "movement_encoding_manifest.json").read_text())
    assert len(manifest["encodings"]) == 3
    assert "explained_variance_ratio" in manifest["transforms"]["angles"]
