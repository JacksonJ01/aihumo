from __future__ import annotations

import json
from pathlib import Path

from aihumo.performance import ProcessingPerformanceTracker, observed_processing_fps
from aihumo.processing import classify_processing_progress


def test_processing_stage_classification_is_bounded_and_complete():
    expected = {
        0.02: "inspection_and_decoding",
        0.20: "pose_estimation",
        0.50: "skeleton_rendering",
        0.70: "feature_extraction",
        0.89: "tracking_quality_and_suggestions",
        0.93: "parquet_and_metadata_export",
        0.99: "finalization_and_validation",
    }
    for fraction, stage in expected.items():
        actual_stage, stage_fraction = classify_processing_progress(fraction)
        assert actual_stage == stage
        assert 0.0 <= stage_fraction <= 1.0
    assert classify_processing_progress(-1)[1] == 0.0
    assert classify_processing_progress(2) == ("finalization_and_validation", 1.0)


def test_performance_tracker_writes_technical_local_history(tmp_path):
    source = tmp_path / "workout.mp4"
    model = tmp_path / "pose.task"
    feature = tmp_path / "features.parquet"
    source.write_bytes(b"video-bytes")
    model.write_bytes(b"model")
    feature.write_bytes(b"features")
    performance_path = tmp_path / "metadata" / "performance.json"
    history_path = tmp_path / ".aihumo" / "performance_history.json"

    tracker = ProcessingPerformanceTracker(temp_path=tmp_path / ".processing")
    tracker.observe("pose_estimation", throughput_fps=24.0)
    tracker.observe("feature_extraction")
    document = tracker.finish(
        performance_path=performance_path,
        history_path=history_path,
        video_info={
            "duration_s": 10.0, "frame_count": 300, "width": 1280,
            "height": 720, "source_fps": 30.0,
        },
        source_video=source,
        model_path=model,
        profile="standard",
        output_paths=[feature],
    )

    assert document["pose_estimation_fps"] == 24.0
    assert document["output_sizes_bytes"]["features.parquet"] == len(b"features")
    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert len(history["records"]) == 1
    assert "source_name" not in history["records"][0]
    measured = observed_processing_fps(history_path, profile="standard")
    assert measured is not None
    assert 1 <= measured.low <= measured.high

