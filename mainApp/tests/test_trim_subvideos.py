from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from aihumo.storage import load_json, save_json_atomic, save_parquet_atomic
from app.trim_subvideos import TrimSegment, next_session_id, processed_inventory, trim_recording_artifacts


def _write_video(path: Path, count: int = 6, fps: float = 2.0) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (32, 24))
    assert writer.isOpened()
    try:
        for index in range(count):
            frame = np.full((24, 32, 3), index * 20, dtype=np.uint8)
            writer.write(frame)
    finally:
        writer.release()


def test_trim_creates_new_sessions_with_matching_features_and_annotations(tmp_path):
    processed = tmp_path / "processed"
    source_dir = processed / "S001" / "V001"
    (source_dir / "video").mkdir(parents=True)
    (source_dir / "parquet").mkdir()
    (source_dir / "annotations").mkdir()
    video = source_dir / "video" / "V001_skeleton.mp4"
    features = source_dir / "parquet" / "V001_features.parquet"
    annotation = source_dir / "annotations" / "V001_annotations.json"
    _write_video(video)
    save_parquet_atomic(pd.DataFrame({
        "frame_id": range(6),
        "timestamp_s": np.arange(6, dtype=float) / 2,
        "angle_left_knee": np.arange(6, dtype=float),
        "angular_velocity_left_knee": np.arange(6, dtype=float),
    }), features)
    save_json_atomic({
        "schema_version": "1.0", "session_id": "S001", "video_id": "V001",
        "annotations": [{
            "annotation_id": "A00001", "segment_id": "V001_SEG0001",
            "annotation_type": "activity_state", "start_frame": 1, "end_frame": 4,
            "start_time_s": 0.5, "end_time_s": 2.0, "duration_s": 1.5,
            "activity_state": "active", "exercise": None, "set_id": None,
            "rep_id": None, "phase": "N/A", "form_label": "unlabeled",
            "issue_type": [], "error_category": [], "affected_joints": [], "notes": "",
        }],
    }, annotation)

    outputs = trim_recording_artifacts(
        video_path=video,
        features_path=features,
        output_root=processed,
        segments=[TrimSegment(0.5, 1.5, "first"), TrimSegment(1.5, 2.5, "second")],
    )

    assert [path.parent.name for path in outputs] == ["S002", "S003"]
    assert next_session_id(processed) == "S004"
    assert processed_inventory(processed)["recordingCount"] == 3
    for index, output in enumerate(outputs):
        output_features = output / "parquet" / f"{output.name}_features.parquet"
        output_video = output / "video" / f"{output.name}_skeleton.mp4"
        output_annotation = output / "annotations" / f"{output.name}_annotations.json"
        assert output_features.is_file()
        assert output_video.is_file()
        assert output_annotation.is_file()
        frame_data = pd.read_parquet(output_features)
        assert frame_data["frame_id"].tolist() == [0, 1, 2]
        assert frame_data["timestamp_s"].tolist() == [0.0, 0.5, 1.0]
        assert pd.isna(frame_data["angular_velocity_left_knee"].iloc[0])
        saved = load_json(output_annotation)
        row = saved["annotations"][0]
        assert row["start_frame"] == 0
        assert row["end_frame"] == (2 if index == 0 else 1)
        assert saved["video_id"] == output.name
