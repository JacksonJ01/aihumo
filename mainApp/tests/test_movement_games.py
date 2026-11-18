import json

import numpy as np
import pandas as pd
import pytest

from app.movement_games import (
    GAME_VARIANTS,
    MovementGameDialog,
    MovementGameEngine,
    feature_pair_for_parquet,
    game_variant_definitions,
    load_feature_recording,
    load_game_definitions,
)
from app.preferences import DesktopPreferences, PreferenceStore
from aihumo.game_engine import LoopState
from PyQt6.QtWidgets import QDialog


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


def test_movement_games_share_settings_and_refresh_theme(qt_app, tmp_path, monkeypatch):
    store = PreferenceStore(tmp_path / "settings.json")
    store.save(DesktopPreferences(theme="Light", setup_completed=True))
    dialog = MovementGameDialog("flow_zone", preferences=store)
    try:
        assert dialog.preference_store is store
        assert dialog.settings_button.isEnabled()
        assert "#f5f7fb" in dialog.styleSheet()
        store.save(DesktopPreferences(theme="Dark", game_high_contrast_targets=True, setup_completed=True))
        monkeypatch.setattr("app.movement_games.PreferencesDialog.exec", lambda _self: QDialog.DialogCode.Accepted)
        dialog.open_settings()
        assert dialog.preferences.theme == "Dark"
        assert dialog.canvas.high_contrast
        assert "#091426" in dialog.styleSheet()
    finally:
        dialog.close()


def test_game_catalog_contains_all_hub_modes():
    games = load_game_definitions()
    assert len(games) == 10
    assert {game.id for game in games} == {
        "just_dance", "flow_zone", "mirror_match", "balance", "path_precision",
        "sports", "rehab", "ergonomics", "gait", "sequence",
    }
    assert len({game.id for game in games}) == len(games)
    assert len({game.title for game in games}) == len(games)
    assert len({game.rule for game in games}) == len(games)
    assert all(game.description.strip() and game.objective.strip() for game in games)


def test_consolidated_games_preserve_every_legacy_mechanic():
    games = load_game_definitions()
    rules = {
        variant.rule
        for definition in games
        for variant in GAME_VARIANTS[definition.id]
    }
    assert rules == {
        "dance", "rhythm", "partner", "target_grid", "target_grid_12",
        "reaction_targets", "avoid_zone", "obstacle_dodge", "mirror",
        "freeze_pose", "balance", "path_follow", "sports_reaction",
        "rehab", "ergonomics", "gait", "sequence",
    }
    assert all(1 <= len(GAME_VARIANTS[definition.id]) <= 5 for definition in games)


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


def test_every_game_handles_minimal_optional_features_without_nan():
    frame = pd.DataFrame({
        "_game_frame_id": [0, 1, 2],
        "_game_time_s": [0.0, 0.1, 0.2],
    })
    for definition in load_game_definitions():
        engine = MovementGameEngine(definition, frame)
        for index in range(len(frame)):
            result = engine.preview(index)
            assert np.isfinite(result["score"]), definition.id
            assert np.isfinite(result["average"]), definition.id
            assert np.isfinite(result["position"]).all(), definition.id
            assert np.isfinite(result["target"]).all(), definition.id


def test_game_input_validation_fails_safely_and_confidence_masks_scores():
    definition = load_game_definitions()[0]
    with pytest.raises(ValueError, match="at least one"):
        MovementGameEngine(definition, pd.DataFrame())
    with pytest.raises(ValueError, match="strictly increasing"):
        MovementGameEngine(definition, pd.DataFrame({
            "_game_frame_id": [0, 1, 2],
            "_game_time_s": [0.0, 0.1, 0.1],
        }))
    frame = game_frame(4)
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    frame["pose_present"] = 0
    engine = MovementGameEngine(definition, frame)
    assert all(engine.preview(index)["score"] == 0 for index in range(len(frame)))


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


def test_every_game_variant_exposes_an_instruction_and_valid_score():
    frame = game_frame()
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    for definition in load_game_definitions():
        variants = game_variant_definitions(definition)
        assert len(variants) == len(GAME_VARIANTS[definition.id])
        for variant, configured in zip(GAME_VARIANTS[definition.id], variants, strict=True):
            engine = MovementGameEngine(configured, frame, difficulty="medium", partner_frame=frame.copy())
            result = engine.preview(50)
            assert result["instruction"], (definition.id, variant.title)
            assert 0 <= result["score"] <= 1
            assert result["state"] == LoopState.READY.value
            assert len(result["position"]) == 2
            assert len(result["target"]) == 2
            assert isinstance(result["success"], bool)


def test_pause_seek_and_preview_do_not_duplicate_scores():
    frame = game_frame(30)
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    definition = next(game for game in load_game_definitions() if game.id == "flow_zone")
    definition = game_variant_definitions(definition)[2]
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
    definition = next(game for game in load_game_definitions() if game.id == "flow_zone")
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
    definition = next(game for game in load_game_definitions() if game.id == "mirror_match")
    definition = game_variant_definitions(definition)[2]
    matching_score = MovementGameEngine(definition, primary, partner_frame=matching).preview(10)["score"]
    mismatched_score = MovementGameEngine(definition, primary, partner_frame=mismatched).preview(10)["score"]
    assert matching_score > mismatched_score


def test_desktop_game_controls_drive_backend_loop(qt_app):
    frame = game_frame(12)
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    dialog = MovementGameDialog("flow_zone")
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


def test_consolidated_dialog_switches_challenges_without_losing_recording(qt_app):
    frame = game_frame(24)
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    dialog = MovementGameDialog("flow_zone")
    try:
        dialog.engine = dialog._create_engine(dialog.definition, frame)
        assert dialog.variant_combo.count() == 5
        assert dialog.definition.rule == "target_grid"
        dialog.variant_combo.setCurrentIndex(3)
        assert dialog.selected_variant.title == "Avoid the Zone"
        assert dialog.definition.rule == "avoid_zone"
        assert dialog.engine is not None
        assert dialog.engine.definition.rule == "avoid_zone"
        assert "Avoid the Zone" in dialog.title_label.text()
    finally:
        dialog.close()


def test_obstacle_challenge_opens_maximized_keyboard_prototype(qt_app, monkeypatch):
    opened = []

    class FakeLaneDodgeDialog:
        def __init__(self, parent=None, *, preferences=None):
            opened.append(("created", parent, preferences))

        def setWindowFlag(self, flag, enabled=True):
            opened.append(("flag", flag, enabled))

        def showMaximized(self):
            opened.append(("maximized",))

        def exec(self):
            opened.append(("executed",))

    monkeypatch.setattr("app.movement_games.LaneDodgeDialog", FakeLaneDodgeDialog)
    dialog = MovementGameDialog("flow_zone")
    try:
        assert dialog.live_dodge_button.isHidden()
        dialog.variant_combo.setCurrentIndex(4)
        assert dialog.definition.rule == "obstacle_dodge"
        assert not dialog.live_dodge_button.isHidden()
        dialog.live_dodge_button.click()
        assert opened[0][0] == "created"
        assert ("maximized",) in opened and ("executed",) in opened
    finally:
        dialog.close()


def test_game_preferences_configure_loop_feedback_and_results(qt_app, tmp_path):
    frame = game_frame(18)
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    preferences = DesktopPreferences(
        game_default_difficulty="hard",
        game_countdown_s=2,
        game_audio_cues=False,
        game_show_instructions=False,
        game_high_contrast_targets=True,
        game_auto_save_results=True,
        game_results_directory=str(tmp_path),
        game_target_period_scale=0.5,
        game_calibration_s=2.25,
    )
    dialog = MovementGameDialog("flow_zone", preferences=preferences)
    try:
        original_period = dialog.definition.target_period_s
        dialog.engine = dialog._create_engine(dialog.definition, frame)
        dialog.path_edit.setText(str(tmp_path / "session_features.parquet"))
        dialog.frame_slider.setRange(0, len(frame) - 1)
        dialog.frame_slider.setEnabled(True)
        assert dialog.difficulty_combo.currentData() == "hard"
        assert dialog.canvas.high_contrast is True
        assert dialog.engine.definition.target_period_s == pytest.approx(original_period * 0.5)
        assert dialog.engine.definition.calibration_s == pytest.approx(2.25)

        dialog.toggle_play()
        assert dialog.countdown_timer.isActive()
        assert dialog.start_button.isEnabled() is False
        dialog._countdown_tick()
        dialog._countdown_tick()
        dialog.timer.stop()
        assert dialog.engine.state in (LoopState.CALIBRATING, LoopState.RUNNING)
        dialog.render_frame(0)
        assert " | " in dialog.status.text()
        assert "Move into" not in dialog.status.text()

        dialog._auto_save_results()
        result_path = tmp_path / "session_flow_zone_results.json"
        assert result_path.is_file()
        assert json.loads(result_path.read_text(encoding="utf-8"))["game_id"] == "flow_zone"
    finally:
        dialog.close()


def test_every_game_dialog_renders_shared_canvas(qt_app):
    """Exercise the Qt paint path used by every configured game mode."""
    frame = game_frame(12)
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    for definition in load_game_definitions():
        dialog = MovementGameDialog(definition)
        try:
            dialog.engine = MovementGameEngine(definition, frame)
            dialog.frame_slider.setRange(0, len(frame) - 1)
            dialog.frame_slider.setEnabled(True)
            dialog.render_frame(0)
            dialog.show()
            qt_app.processEvents()
            assert not dialog.canvas.grab().isNull(), definition.id
        finally:
            dialog.close()


def test_every_game_dialog_control_loop_is_safe(qt_app, monkeypatch, tmp_path):
    """Click each non-destructive control for every configured game mode."""
    monkeypatch.setattr("app.movement_games.QFileDialog.getOpenFileName", lambda *args: ("", ""))
    frame = game_frame(24)
    frame["_game_time_s"] = frame["timestamp_s"]
    frame["_game_frame_id"] = frame["frame_id"]
    for definition in load_game_definitions():
        dialog = MovementGameDialog(definition)
        try:
            dialog.engine = MovementGameEngine(definition, frame, partner_frame=frame.copy())
            dialog.frame_slider.setRange(0, len(frame) - 1)
            dialog.frame_slider.setEnabled(True)
            dialog.load_button.click()
            dialog.partner_button.click()
            dialog.start_button.click()
            assert dialog.engine.state in (LoopState.CALIBRATING, LoopState.RUNNING)
            dialog.start_button.click()
            assert dialog.engine.state == LoopState.PAUSED
            dialog.start_button.click()
            dialog.timer.stop()
            dialog.next_frame()
            dialog.timer.stop()
            dialog.difficulty_combo.setCurrentIndex(2)
            assert dialog.engine.difficulty == "medium"
            dialog.frame_slider.setValue(8)
            assert dialog.engine.index == 8
            dialog.reset_button.click()
            assert dialog.engine.state == LoopState.READY
            assert dialog.start_button.text() == "Start"
            result_path = tmp_path / f"{definition.id}.json"
            monkeypatch.setattr(
                "app.movement_games.QFileDialog.getSaveFileName",
                lambda *args, path=result_path: (str(path), "JSON (*.json)"),
            )
            dialog.save_results_button.setEnabled(True)
            dialog.save_results_button.click()
            assert result_path.is_file()
            dialog.back_button.click()
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
