from pathlib import Path

from PyQt6.QtWidgets import QCheckBox, QLabel, QTabWidget

from app.AIHuMoDataStudio import DesktopApplicationController, HomeWindow, MainHubDialog
from app.main_hub import PerspectiveAppCarousel, ThumbnailPlaceholder
from app.movement_games import load_game_definitions
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
        hub_galaxy_mode=True,
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
    assert loaded.hub_galaxy_mode is True
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
    assert not any("Galaxy" in checkbox.text() for checkbox in dialog.findChildren(QCheckBox))


def test_main_hub_exposes_pipeline_and_justice_dance_entries(qt_app):
    dialog = MainHubDialog()
    try:
        assert dialog.aihumo_button.text().startswith("AIHuMo Pipeline")
        assert dialog.justice_dance_button.text().startswith("Justice Dance")
        assert "just_dance" in dialog.game_buttons
        assert len(dialog.game_buttons) == 17
        assert dialog.NAV_ITEMS == (
            "Home", "Movement Analysis", "Games", "Training", "Rehabilitation", "Cognitive Games"
        )
        assert all(app.art for app in dialog.apps)
        artwork = [item for item in dialog.findChildren(ThumbnailPlaceholder) if item.image_path]
        assert artwork
        assert all(item.image_path.is_file() and not item.source.isNull() for item in artwork)
    finally:
        dialog.close()


def test_all_apps_carousel_keeps_artwork_and_angles_only_side_cards(qt_app):
    launches = []
    dialog = MainHubDialog()
    carousel = PerspectiveAppCarousel(dialog.apps, launches.append)
    try:
        carousel.resize(1100, 340)
        carousel.show()
        qt_app.processEvents()
        assert len(carousel.apps) == len(dialog.apps)
        assert all(not carousel._sources[app.id].isNull() for app in carousel.apps)

        center = carousel._quad_for_offset(500, 170, 420, 250, 0)
        left = carousel._quad_for_offset(300, 170, 350, 210, -1)
        right = carousel._quad_for_offset(700, 170, 350, 210, 1)
        edge_height = lambda quad, top, bottom: quad[bottom].y() - quad[top].y()
        assert edge_height(center, 0, 3) == edge_height(center, 1, 2)
        assert edge_height(left, 1, 2) > edge_height(left, 0, 3)
        assert edge_height(right, 0, 3) > edge_height(right, 1, 2)

        carousel.set_current_index(4, animated=False)
        assert carousel.current_app == dialog.apps[4]
        carousel.activate_current()
        assert launches == [dialog.apps[4]]
        assert not carousel.grab().isNull()

        dialog.search.setText("spelling")
        qt_app.processEvents()
        assert [app.id for app in dialog.all_apps_carousel.apps] == ["spelling_bee"]
        assert "Spelling Bee" in dialog.carousel_status.text()
        dialog.search.clear()
        qt_app.processEvents()
        assert len(dialog.all_apps_carousel.apps) == len(dialog.apps)
    finally:
        carousel.close()
        dialog.close()


def test_every_hub_app_button_launches_without_crashing(qt_app, tmp_path, monkeypatch):
    movement_launches = []
    cognitive_launches = []
    pipeline_modes = []
    pipeline_launches = []

    class FakeMovementDialog:
        def __init__(self, game_id, parent=None):
            movement_launches.append(game_id)

        def exec(self):
            return 0

    class FakeCognitiveDialog:
        def __init__(self, game_id, parent=None):
            cognitive_launches.append(game_id)

        def exec(self):
            return 0

    monkeypatch.setattr("app.main_hub.MovementGameDialog", FakeMovementDialog)
    monkeypatch.setattr("app.main_hub.CognitiveGameDialog", FakeCognitiveDialog)
    dialog = MainHubDialog(
        state_dir=tmp_path,
        open_pipeline=lambda: pipeline_launches.append("pipeline"),
        open_pipeline_mode=pipeline_modes.append,
    )
    try:
        cards = [card for section in dialog.home_sections.values() for card in section.grid.cards]
        assert len(cards) == len(dialog.apps)
        for card in cards:
            card.open_button.click()
            qt_app.processEvents()
        assert set(movement_launches) == {game.id for game in load_game_definitions()}
        assert set(cognitive_launches) == {"spelling_bee", "math_challenge"}
        assert pipeline_modes == [1, 2, 3, 4]
        assert pipeline_launches == ["pipeline"]
        assert len(dialog._recent_app_ids()) == 3
    finally:
        dialog.close()


def test_main_hub_supports_light_and_dark_without_galaxy(qt_app, tmp_path):
    store = PreferenceStore(tmp_path / "settings.json")
    dialog = MainHubDialog(state_dir=tmp_path, preferences=store)
    try:
        for theme in ("Light", "Dark"):
            dialog.theme_combo.setCurrentText(theme)
            dialog._visual_option_changed()
            qt_app.processEvents()
            loaded = PreferenceStore(tmp_path / "settings.json").values
            assert loaded.theme == theme
        assert not hasattr(dialog, "galaxy")
        assert not hasattr(dialog, "galaxy_toggle")
    finally:
        dialog.close()


def test_main_hub_has_three_recent_slots_and_persists_unique_apps(qt_app, tmp_path):
    dialog = MainHubDialog(state_dir=tmp_path)
    try:
        assert len(dialog.recent_cards) == 3
        assert all(card.app is None for card in dialog.recent_cards)
        for app_id in ("annotation", "spelling_bee", "balance", "annotation"):
            dialog._remember_app(dialog.app_by_id[app_id])
        assert dialog._recent_app_ids() == ["annotation", "balance", "spelling_bee"]
        assert [card.app.id for card in dialog.recent_cards if card.app] == [
            "annotation", "balance", "spelling_bee"
        ]
    finally:
        dialog.close()


def test_hub_text_wraps_and_grids_reflow(qt_app, tmp_path):
    dialog = MainHubDialog(state_dir=tmp_path)
    try:
        dialog.resize(820, 720)
        dialog.show()
        qt_app.processEvents()
        assert all(label.wordWrap() for label in dialog.category_descriptions.values())
        for grid in dialog.category_grids.values():
            assert grid.cards
            grid.resize(760, grid.height())
            grid._reflow()
            assert grid._columns == 2
            assert grid.grid.count() == len(grid.cards)
        assert all(section.description_label.wordWrap() for section in dialog.home_sections.values())
        footer_texts = [label.text() for label in dialog.findChildren(QLabel)]
        assert "Sir Jax Big Boi J" in footer_texts
        assert not dialog.home_scroll.horizontalScrollBar().isVisible()
    finally:
        dialog.close()


def test_desktop_controller_starts_at_hub_and_returns_from_pipeline(qt_app, tmp_path):
    controller = DesktopApplicationController(state_dir=tmp_path / "state", processed_root=tmp_path)
    controller.show_hub()
    try:
        assert controller.hub_window.isVisible()
        assert controller.pipeline_window is None

        controller.hub_window.aihumo_button.click()
        qt_app.processEvents()
        assert controller.pipeline_window is not None
        assert controller.pipeline_window.isVisible()
        assert not controller.hub_window.isVisible()
        assert controller.pipeline_window.windowTitle() == "AIHuMo Data Studio"

        controller.pipeline_window.back_to_hub_button.click()
        qt_app.processEvents()
        assert controller.hub_window.isVisible()
        assert not controller.pipeline_window.isVisible()
    finally:
        if controller.pipeline_window is not None:
            controller.pipeline_window._return_to_hub_callback = None
            controller.pipeline_window.close()
        controller.hub_window.close()


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

