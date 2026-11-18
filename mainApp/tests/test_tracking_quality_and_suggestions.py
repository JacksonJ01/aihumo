from __future__ import annotations

import numpy as np
import pandas as pd

from aihumo.annotation_suggestions import generate_annotation_suggestions, update_suggestion_review
from aihumo.tracking_quality import detect_tracking_anomalies


def _pose_frames(count=300, fps=30.0):
    timestamps = np.arange(count) / fps
    data = {
        "frame_id": np.arange(count),
        "timestamp_s": timestamps,
        "fps": fps,
        "pose_present": np.ones(count),
    }
    for landmark in range(33):
        data[f"lm{landmark}_x"] = np.full(count, 0.2 + landmark * 0.01)
        data[f"lm{landmark}_y"] = np.full(count, 0.3 + landmark * 0.005)
        data[f"lm{landmark}_z"] = np.zeros(count)
        data[f"lm{landmark}_visibility"] = np.ones(count)
        data[f"lm{landmark}_presence"] = np.ones(count)
    return pd.DataFrame(data)


def test_tracking_quality_finds_corroborated_jump_and_preserves_input():
    frames = _pose_frames()
    frames.loc[120, "lm15_x"] += 0.65
    frames.loc[120, "lm15_visibility"] = 0.05
    input_snapshot = frames.copy(deep=True)

    report = detect_tracking_anomalies(frames)

    reasons = {(warning["reason"], warning["landmark"]) for warning in report["warnings"]}
    assert ("coordinate_discontinuity", 15) in reasons
    assert ("low_or_abrupt_confidence", 15) in reasons
    assert all(warning["not_form_error"] for warning in report["warnings"])
    pd.testing.assert_frame_equal(input_snapshot, frames)


def test_coordinated_fast_translation_is_not_called_tracking_failure():
    frames = _pose_frames()
    for landmark in range(33):
        frames.loc[150:, f"lm{landmark}_x"] += 0.35
    report = detect_tracking_anomalies(frames)
    assert not any(
        warning["reason"] == "coordinate_discontinuity"
        for warning in report["warnings"]
    )


def test_annotation_suggestions_are_separate_stable_and_conservative():
    frames = _pose_frames(count=900)
    time = frames["timestamp_s"].to_numpy()
    active = (time >= 4.0) & (time <= 24.0)
    knee = np.zeros(len(frames))
    knee[active] = 90.0 + 35.0 * np.sin(2 * np.pi * 0.5 * time[active])
    frames["angle_left_knee"] = knee
    frames["lm25_y"] = frames["lm25_y"] + np.where(
        active, 0.10 * np.sin(2 * np.pi * 0.5 * time), 0.0
    )
    config = {
        "rep_detection": {
            "signal_candidates": ["angle_left_knee"],
            "min_rep_seconds": 1.0,
            "max_rep_seconds": 3.0,
            "min_amplitude": 0.05,
            "min_prominence": 0.01,
            "min_confidence": 0.0,
        }
    }

    document = generate_annotation_suggestions(frames, config=config, exercise_hint="squat")
    repeated = generate_annotation_suggestions(frames, config=config, exercise_hint="squat")
    layers = {item["annotation_layer"] for item in document["suggestions"]}

    assert "activity_state" in layers
    assert "set" in layers
    assert "rep" in layers
    assert "phase" not in layers
    assert "form_interval" not in layers
    assert all(item["review_status"] == "pending" for item in document["suggestions"])
    assert all(item["original_proposed_boundaries"] for item in document["suggestions"])
    assert [item["suggestion_id"] for item in document["suggestions"]] == [
        item["suggestion_id"] for item in repeated["suggestions"]
    ]
    assert document["authoritative_source"] == "annotations.json"
    assert any("Phase suggestion abstained" in item for item in document["diagnostics"]["abstentions"])
    assert any("not form errors" in item for item in document["diagnostics"]["abstentions"])

    first = document["suggestions"][0]
    reviewed = update_suggestion_review(
        document,
        first["suggestion_id"],
        "edited",
        final_boundaries={"start_frame": 5, "end_frame": 10},
        accepted_annotation_id="A00001",
    )
    changed = next(
        item for item in reviewed["suggestions"]
        if item["suggestion_id"] == first["suggestion_id"]
    )
    assert changed["review_status"] == "edited"
    assert changed["original_proposed_boundaries"] == first["original_proposed_boundaries"]
    assert changed["final_user_boundaries"] == {"start_frame": 5, "end_frame": 10}
    unchanged = next(
        item for item in document["suggestions"]
        if item["suggestion_id"] == first["suggestion_id"]
    )
    assert unchanged["review_status"] == "pending"

