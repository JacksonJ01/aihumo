import json

import numpy as np
import pandas as pd
import pytest

from app.movement_games import (
    MovementGameDialog,
    MovementGameEngine,
    feature_pair_for_parquet,
    load_feature_recording,
    load_game_definitions,
)
from aihumo.game_engine import LoopState


def game_frame(count=90):
    time = np.cumsum(np.resize(np.array([1 / 30, 1 / 24, 1 / 15]), count))
    phase = np.linspace(0, 6 * np.pi, count)
    return pd.DataFrame({
        "frame_id": range(count),
        "timestamp_s": time - time[0],
        "pose_present": np.ones(count),
        "review_torso2d_hip_midpoint_x": 0.5 + 0.42 * np.sin(phase),
        "review_torso2d_hip_midpoint_y": 0.5 + 0.38 * np.cos(phase * 0.5),
        "angle_3d_left_knee": 110 + 35 * np.sin(phase),
        "angle_3d_right_knee": 110 + 34 * np.sin(phase + 0.08),
        "angle_3d_left_elbow": 95 + 50 * np.cos(phase),
        "angle_3d_right_elbow": 95 + 48 * np.cos(phase + 0.1),
        "angle_3d_torso_vertical": 175 + 2 * np.sin(phase / 2),
    })


def test_game_catalog_contains_all_hub_modes():
    games = load_game_definitions()
    assert len(games) >= 16
    assert {game.id for game in games} >= {
        "just_dance", "target_grid_6", "mirror", "path", "reaction", "freeze", "avoid",
        "rhythm", "obstacle", "sequence", "balance", "partner", "sports",
        "rehab", "ergonomics", "gait",
    }


def test_all_game_rules_consume_one_shared_feature_table(tmp_path):
    parquet = tmp_path / "clip_features.parquet"
    frame = pd.DataFrame({
        "frame_id": range(24),
        "timestamp_s": np.arange(24, dtype=float) / 24,
        "review_torso2d_hip_midpoint_x": np.linspace(-0.2, 0.8, 24),
        "review_torso2d_hip_midpoint_y": np.linspace(0.3, 0.7, 24),
        "angle_3d_right_knee": np.linspace(80, 140, 24),
    })
    frame.to_parquet(parquet, index=False)
    loaded = load_feature_recording(parquet)
    assert loaded is not frame and len(loaded) == 24
    for definition in load_game_definitions():
        engine = MovementGameEngine(definition, loaded)
        result = engine.evaluate(5)
        assert result["frame"] == 5
        assert 0 <= result["score"] <= 1
        assert 0 <= result["average"] <= 1
        assert len(result["position"]) == 2


def test_every_game_loop_runs_to_completion_and_exports_summary():
    frame = game_frame()
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    for definition in load_game_definitions():
        engine = MovementGameEngine(definition, frame, difficulty="medium")
        assert engine.state == LoopState.READY
        with pytest.raises(RuntimeError, match="must be running"):
            engine.step(0)
        engine.start()
        for index in range(len(frame)):
            result = engine.step(index)
            assert 0 <= result["score"] <= 1
        assert engine.state == LoopState.COMPLETED
        summary = engine.summary()
        assert summary.samples == len(frame) - engine.calibration_frames
        assert 0 <= summary.average_score <= 1
        assert 0 <= summary.success_rate <= 1
        assert summary.duration_s == pytest.approx(frame["timestamp_s"].iloc[-1])
        json.dumps(summary.to_document())


def test_pause_seek_and_preview_do_not_duplicate_scores():
    frame = game_frame(30)
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    definition = next(game for game in load_game_definitions() if game.id == "reaction")
    engine = MovementGameEngine(definition, frame)
    first_scored = engine.calibration_frames
    engine.start(from_index=first_scored)
    engine.step(first_scored)
    engine.step(first_scored + 1)
    assert engine.summary().samples == 2
    engine.pause()
    with pytest.raises(RuntimeError, match="must be running"):
        engine.step(2)
    engine.seek(20)
    engine.preview(12)
    assert engine.summary().samples == 2
    engine.resume()
    engine.step(20)
    engine.step(20)
    assert engine.summary().samples == 3
    engine.reset()
    assert engine.state == LoopState.READY
    assert engine.summary().samples == 0


def test_targets_follow_source_time_not_frame_count():
    frame = game_frame(18)
    frame["timestamp_s"] = np.array([0, .05, .10, .15, .20, .25, .5, .75, 1.0,
                                      1.2, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0, 3.5, 4.0])
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    definition = next(game for game in load_game_definitions() if game.id == "target_grid_6")
    engine = MovementGameEngine(definition, frame, seed=3)
    assert engine.preview(0)["target_slot"] == 0
    assert engine.preview(8)["target_slot"] == 0
    assert engine.preview(10)["target_slot"] == 1
    assert engine.preview(16)["target_slot"] == 2


def test_partner_and_mirror_backend_accepts_second_feature_stream():
    primary = game_frame(30)
    primary["_game_time_s"] = primary["timestamp_s"]
    primary["_game_frame_id"] = primary["frame_id"]
    matching = primary.copy()
    mismatched = primary.copy()
    for column in [name for name in mismatched if name.startswith("angle_3d_")]:
        mismatched[column] = np.clip(mismatched[column] + 55, 0, 180)
    definition = next(game for game in load_game_definitions() if game.id == "partner")
    matching_score = MovementGameEngine(definition, primary, partner_frame=matching).preview(10)["score"]
    mismatched_score = MovementGameEngine(definition, primary, partner_frame=mismatched).preview(10)["score"]
    assert matching_score > mismatched_score


def test_desktop_game_controls_drive_backend_loop(qt_app):
    frame = game_frame(12)
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    dialog = MovementGameDialog("target_grid_6")
    try:
        dialog.engine = MovementGameEngine(dialog.definition, frame)
        dialog.frame_slider.setRange(0, len(frame) - 1)
        dialog.frame_slider.setEnabled(True)
        dialog.toggle_play()
        assert dialog.engine.state in (LoopState.CALIBRATING, LoopState.RUNNING)
        assert dialog.engine.summary().samples == 0
        dialog.toggle_play()
        assert dialog.engine.state == LoopState.PAUSED
        dialog.toggle_play()
        dialog.timer.stop()
        dialog.next_frame()
        dialog.timer.stop()
        assert dialog.engine.summary().samples <= 1
        dialog.reset_game()
        assert dialog.engine.state == LoopState.READY
        assert dialog.progress.value() > 0
    finally:
        dialog.close()


def test_feature_pair_resolves_processed_skeleton_video(tmp_path):
    recording = tmp_path / "S001" / "clip"
    parquet = recording / "parquet" / "clip_features.parquet"
    video = recording / "video" / "clip_skeleton.mp4"
    parquet.parent.mkdir(parents=True)
    video.parent.mkdir(parents=True)
    parquet.write_bytes(b"placeholder")
    video.write_bytes(b"placeholder")
    found_video, found_parquet = feature_pair_for_parquet(parquet)
    assert found_parquet == parquet.resolve()
    assert found_video == video.resolve()
