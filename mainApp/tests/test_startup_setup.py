from pathlib import Path

from PyQt6.QtWidgets import QCheckBox, QTabWidget

from app.AIHuMoDataStudio import HomeWindow, MainHubDialog
from app.mode1_annotation import AnnotationDialog
from app.preferences import DesktopPreferences, PreferenceStore, PreferencesDialog, StartupSetupDialog


def test_startup_setup_persists_participant_and_starter_video(qt_app, tmp_path):
    store = PreferenceStore(tmp_path / "settings.json")
    dialog = StartupSetupDialog(store)
    dialog.participant_edit.setText("P001")
    dialog.camera_angle_combo.setCurrentText("Three-quarter")
    video = tmp_path / "starter.mp4"
    video.write_bytes(b"video placeholder")
    dialog.video_edit.setText(str(video))
    folders = {
        "source": str(tmp_path / "videos"),
        "skeleton": str(tmp_path / "skeleton"),
        "features": str(tmp_path / "features"),
        "annotations": str(tmp_path / "annotations"),
        "output": str(tmp_path / "output"),
    }
    dialog.source_directory.setText(folders["source"])
    dialog.skeleton_directory.setText(folders["skeleton"])
    dialog.features_directory.setText(folders["features"])
    dialog.annotations_directory.setText(folders["annotations"])
    dialog.output_directory.setText(folders["output"])
    dialog._save()

    loaded = PreferenceStore(tmp_path / "settings.json").values
    assert loaded.setup_completed is True
    assert loaded.participants == ("P001",)
    assert loaded.default_participant == "P001"
    assert loaded.starter_video == str(video)
    assert loaded.default_camera_angle == "Three-quarter"
    assert loaded.default_source_directory == folders["source"]
    assert loaded.default_features_directory == folders["features"]
    assert dialog.setup["participant"] == "P001"
    assert dialog.setup["video"] == str(video)
    assert dialog.setup["open_video"] is True
    assert dialog.setup["directories"] == folders


def test_startup_setup_skip_is_persisted_without_a_video(qt_app, tmp_path):
    store = PreferenceStore(tmp_path / "settings.json")
    dialog = StartupSetupDialog(store)
    dialog._skip()

    loaded = PreferenceStore(tmp_path / "settings.json").values
    assert loaded.setup_completed is True
    assert loaded.starter_video == ""
    assert dialog.setup == {}


def test_starter_artifacts_finds_processed_feature_pair(tmp_path):
    session = tmp_path / "S001"
    video_dir = session / "video"
    features_dir = session / "features"
    video_dir.mkdir(parents=True)
    features_dir.mkdir()
    video = video_dir / "V001_skeleton.mp4"
    parquet = features_dir / "V001_features.parquet"
    video.write_bytes(b"video")
    parquet.write_bytes(b"parquet")

    found_video, found_parquet = HomeWindow._starter_artifacts(video)
    assert found_video == video
    assert found_parquet == parquet


def test_extended_preferences_round_trip_and_bounds(tmp_path):
    path = tmp_path / "settings.json"
    store = PreferenceStore(path)
    store.save(DesktopPreferences(
        default_camera_name="side_camera",
        default_camera_angle="Side",
        default_source_directory="C:/videos",
        default_skeleton_directory="C:/skeleton",
        default_features_directory="C:/features",
        default_annotations_directory="C:/annotations",
        default_output_directory="C:/output",
        default_playback_speed=5.0,
        autosave_interval_s=45,
        theme="Dark",
        confidence_threshold=0.8,
        smoothing_method="Savitzky-Golay",
        default_annotation_layer="set",
    ))
    loaded = PreferenceStore(path).values
    assert loaded.default_camera_name == "side_camera"
    assert loaded.default_camera_angle == "Side"
    assert loaded.default_source_directory == "C:/videos"
    assert loaded.default_features_directory == "C:/features"
    assert loaded.default_playback_speed == 5.0
    assert loaded.autosave_interval_s == 45
    assert loaded.theme == "Dark"
    assert loaded.confidence_threshold == 0.8
    assert loaded.smoothing_method == "Savitzky-Golay"
    assert loaded.default_annotation_layer == "set"


def test_legacy_preferences_keep_new_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"default_frame_jump": 12, "participants": ["P001"]}', encoding="utf-8")
    loaded = PreferenceStore(path).values
    assert loaded.default_frame_jump == 12
    assert loaded.default_camera_name == "camera_01"
    assert loaded.default_playback_speed == 1.0


def test_preferences_dialog_exposes_optimization_pages(qt_app, tmp_path):
    dialog = PreferencesDialog(PreferenceStore(tmp_path / "settings.json"))
    # Use the visible tab labels rather than implementation-specific child
    # names so this remains stable if the settings layout is reorganized.
    tab_widget = next(widget for widget in dialog.findChildren(QTabWidget))
    labels = [tab_widget.tabText(index) for index in range(tab_widget.count())]
    assert {"General", "Timeline & graphs", "Playback", "Visualization", "Data & processing", "Annotation"} <= set(labels)
    assert not any(
        checkbox.text() == "Update context automatically over saved frames"
        for checkbox in dialog.findChildren(QCheckBox)
    )


def test_main_hub_exposes_pipeline_and_justice_dance_entries(qt_app):
    dialog = MainHubDialog()
    try:
        assert dialog.aihumo_button.text() == "AIHuMo Pipeline"
        assert dialog.justice_dance_button.text() == "Justice Dance"
    finally:
        dialog.close()


def test_exercise_variation_is_editable_only_on_set_layer(qt_app):
    dialog = AnnotationDialog(0, 1, 0.0, 1.0, {})
    try:
        variation = dialog.exercise_selector.exercise_variation
        assert not variation.isEnabled()
        dialog.annotation_type.setCurrentIndex(dialog.annotation_type.findData("set"))
        dialog._update_layer_ui()
        assert variation.isEnabled()
        dialog.annotation_type.setCurrentIndex(dialog.annotation_type.findData("rep"))
        dialog._update_layer_ui()
        assert not variation.isEnabled()
    finally:
        dialog.close()

