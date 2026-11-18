from pathlib import Path

import pytest

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QCheckBox, QFrame, QLabel, QTabWidget

from app.AIHuMoDataStudio import DesktopApplicationController, HomeWindow, MainHubDialog
from app.branding import (
    APP_LOGO_ICNS,
    APP_LOGO_ICO,
    APP_LOGO_PNG,
    APP_SPLASH_PNG,
    STARTUP_MESSAGE,
    STARTUP_SPLASH_MS,
    STARTUP_TITLE,
    WINDOWS_APP_USER_MODEL_ID,
    application_icon,
    create_startup_splash,
)
from app.hub_artwork import review_artwork_set
from app.main_hub import (
    HUB_CARD_DIR,
    HUB_PROFESSIONAL_CARD_DIR,
    HubBackgroundViewport,
    PerspectiveAppCarousel,
    ThumbnailPlaceholder,
    hub_apps,
    ranked_hub_apps,
)
from app.movement_games import load_game_definitions
from app.mode0_batch import BatchSessionDialog
from app.mode1_annotation import AnnotationDialog
from app.preferences import (
    BackgroundCropPreview,
    DesktopPreferences,
    HUB_BACKGROUND_DIR,
    PreferenceStore,
    PreferencesDialog,
    StartupSetupDialog,
    apply_installer_bootstrap,
)
from app.app_paths import default_processed_root, installer_bootstrap_path, user_data_dir


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


def test_installer_bootstrap_merges_into_user_settings_once(tmp_path):
    state = tmp_path / "user-state"
    store = PreferenceStore(state / "settings.json")
    bootstrap = installer_bootstrap_path(state)
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_text(
        '{"schema_version": 1, "participant": "P009", "camera_name": "side_cam", '
        '"camera_angle": "Three-quarter", "source_directory": "C:/recordings", '
        '"skeleton_directory": "C:/skeletons", "features_directory": "C:/features", '
        '"annotations_directory": "C:/annotations", "output_directory": "C:/processed", '
        '"starter_video": "C:/recordings/first.mp4", '
        '"starter_videos": ["C:/recordings/first.mp4", "C:/recordings/second.mp4"], '
        '"starter_skeleton": "C:/skeletons/first_skeleton.mp4", '
        '"starter_features": "C:/features/first_features.parquet", '
        '"starter_annotations": "C:/annotations/first.json"}',
        encoding="utf-8",
    )
    assert apply_installer_bootstrap(store, bootstrap)
    loaded = PreferenceStore(store.path).values
    assert loaded.setup_completed is False
    assert loaded.default_participant == "P009"
    assert loaded.default_camera_name == "side_cam"
    assert loaded.default_camera_angle == "Three-quarter"
    assert loaded.starter_videos == (
        "C:/recordings/first.mp4", "C:/recordings/second.mp4",
    )
    assert loaded.starter_features.endswith("first_features.parquet")
    assert not bootstrap.exists()
    assert bootstrap.with_name("installer-bootstrap.consumed.json").is_file()
    assert not apply_installer_bootstrap(store, bootstrap)


def test_user_data_paths_support_managed_override(tmp_path, monkeypatch):
    target = tmp_path / "managed-user-data"
    monkeypatch.setenv("AIHUMO_USER_DATA_DIR", str(target))
    assert user_data_dir() == target.resolve()
    assert default_processed_root() == target.resolve() / "data" / "processed"
    assert installer_bootstrap_path() == target.resolve() / "installer-bootstrap.json"


def test_native_installers_collect_setup_data_without_deleting_user_files():
    root = Path(__file__).resolve().parents[1] / "AI Humo EXE pipeline"
    windows = (root / "Windows" / "AIHuMoDataStudio.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequiredOverridesAllowed=dialog" in windows
    assert "Optional starter recording" in windows
    assert "installer-bootstrap.json" in windows
    assert "never uploads, deletes, or moves original recordings" in windows
    assert "[UninstallDelete]" not in windows
    assert "recursesubdirs createallsubdirs" in windows
    assert "hdiutil create" in (root / "macOS" / "build_portable.sh").read_text(encoding="utf-8")
    assert "dpkg-deb --build" in (root / "Linux" / "build_portable.sh").read_text(encoding="utf-8")


def test_app_branding_assets_supply_window_icon_and_startup_logo(qt_app):
    assert APP_LOGO_PNG.is_file()
    assert APP_LOGO_ICO.is_file()
    assert APP_LOGO_ICNS.is_file()
    assert APP_SPLASH_PNG.is_file()
    assert not application_icon().isNull()
    splash = create_startup_splash(320)
    assert splash is not None
    try:
        assert splash.objectName() == "aihumoStartupSplash"
        assert not splash.pixmap().isNull()
        assert splash.pixmap().width() == 320
        assert splash.pixmap().height() > 320
        assert splash.property("startupTitle") == STARTUP_TITLE
        assert splash.property("startupMessage") == STARTUP_MESSAGE
        assert not splash.windowIcon().isNull()
        assert STARTUP_SPLASH_MS == 3000
        assert WINDOWS_APP_USER_MODEL_ID == "AIHuMo.DataStudio.Desktop"
    finally:
        splash.close()


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
        hub_background_mode="Custom",
        hub_custom_background="C:/images/hub.png",
        hub_background_blur=False,
        hub_background_blur_strength=15,
        hub_background_opacity=0.37,
        hub_parallax_strength=0.61,
        hub_background_crop_x=0.2,
        hub_background_crop_y=0.8,
        hub_artwork_style="Professional",
        game_default_difficulty="hard",
        game_countdown_s=3,
        game_audio_cues=False,
        game_show_instructions=False,
        game_high_contrast_targets=True,
        game_auto_save_results=True,
        game_results_directory="C:/results",
        game_target_period_scale=0.8,
        game_calibration_s=2.5,
        confidence_threshold=0.8,
        smoothing_method="Savitzky-Golay",
        default_annotation_layer="set",
        minimum_free_storage_gib=25.0,
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
    assert loaded.hub_background_mode == "Custom"
    assert loaded.hub_custom_background == "C:/images/hub.png"
    assert loaded.hub_background_blur is False
    assert loaded.hub_background_blur_strength == 15
    assert loaded.hub_background_opacity == 0.37
    assert loaded.hub_parallax_strength == 0.61
    assert loaded.hub_background_crop_x == 0.2
    assert loaded.hub_background_crop_y == 0.8
    assert loaded.hub_artwork_style == "Professional"
    assert loaded.game_default_difficulty == "hard"
    assert loaded.game_countdown_s == 3
    assert loaded.game_audio_cues is False
    assert loaded.game_show_instructions is False
    assert loaded.game_high_contrast_targets is True
    assert loaded.game_auto_save_results is True
    assert loaded.game_results_directory == "C:/results"
    assert loaded.game_target_period_scale == 0.8
    assert loaded.game_calibration_s == 2.5
    assert loaded.confidence_threshold == 0.8
    assert loaded.smoothing_method == "Savitzky-Golay"
    assert loaded.default_annotation_layer == "set"
    assert loaded.minimum_free_storage_gib == 25.0


def test_legacy_preferences_keep_new_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"default_frame_jump": 12, "participants": ["P001"]}', encoding="utf-8")
    loaded = PreferenceStore(path).values
    assert loaded.default_frame_jump == 12
    assert loaded.default_camera_name == "camera_01"
    assert loaded.default_playback_speed == 1.0


def test_legacy_background_defaults_migrate_to_visible_dynamic_values(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        '{"hub_background_blur_strength": 8, "hub_background_opacity": 0.22, '
        '"hub_parallax_strength": 0.35}',
        encoding="utf-8",
    )
    loaded = PreferenceStore(path).values
    assert loaded.hub_background_blur_strength == 5
    assert loaded.hub_background_opacity == pytest.approx(0.48)
    assert loaded.hub_parallax_strength == pytest.approx(0.65)
    assert loaded.hub_background_style_version == 2


def test_preferences_dialog_exposes_optimization_pages(qt_app, tmp_path):
    dialog = PreferencesDialog(PreferenceStore(tmp_path / "settings.json"))
    # Use the visible tab labels rather than implementation-specific child
    # names so this remains stable if the settings layout is reorganized.
    tab_widget = next(widget for widget in dialog.findChildren(QTabWidget))
    labels = [tab_widget.tabText(index) for index in range(tab_widget.count())]
    assert {
        "General", "Timeline & graphs", "Playback", "Visualization", "Data & processing",
        "Annotation", "Games", "Hub background",
    } <= set(labels)
    assert tab_widget.tabPosition() == QTabWidget.TabPosition.West
    assert tab_widget.tabBar().tabSizeHint(0).width() > tab_widget.tabBar().tabSizeHint(0).height()
    assert not any(
        checkbox.text() == "Update context automatically over saved frames"
        for checkbox in dialog.findChildren(QCheckBox)
    )
    assert not any("Galaxy" in checkbox.text() for checkbox in dialog.findChildren(QCheckBox))


def test_preferences_dialog_uses_readable_independent_light_and_dark_palettes(qt_app, tmp_path):
    for theme, text_color, panel_color in (
        ("Light", "#15213d", "#ffffff"),
        ("Dark", "#f5f7ff", "#101d33"),
    ):
        store = PreferenceStore(tmp_path / f"{theme.casefold()}.json")
        store.save(DesktopPreferences(theme=theme))
        dialog = PreferencesDialog(store)
        try:
            stylesheet = dialog.styleSheet().casefold()
            assert text_color in stylesheet
            assert panel_color in stylesheet
            assert "qcombobox qabstractitemview" in stylesheet
            assert "qtabbar::tab:selected" in stylesheet
            assert "qscrollbar::handle:vertical" in stylesheet
        finally:
            dialog.close()


def test_hub_background_assets_crop_editor_and_parallax_render(qt_app, tmp_path):
    assert (HUB_BACKGROUND_DIR / "light.png").is_file()
    assert (HUB_BACKGROUND_DIR / "dark.png").is_file()

    image_path = tmp_path / "square.png"
    image = QImage(400, 400, QImage.Format.Format_RGB32)
    image.fill(QColor("#6a45d8"))
    assert image.save(str(image_path))

    preview = BackgroundCropPreview()
    preview.resize(640, 360)
    preview.set_image(str(image_path))
    preview.show()
    qt_app.processEvents()
    crop = preview._crop_rect()
    assert crop.width() / crop.height() == pytest.approx(16 / 9, rel=0.01)
    preview._move_crop(QPointF(crop.center().x(), preview._image_rect().bottom()))
    assert preview.crop_y == pytest.approx(1.0)

    values = DesktopPreferences(
        theme="Dark",
        hub_background_mode="Custom",
        hub_custom_background=str(image_path),
        hub_background_blur=True,
        hub_background_blur_strength=12,
        hub_background_opacity=0.4,
        hub_parallax_strength=0.75,
        hub_background_crop_y=1.0,
    )
    viewport = HubBackgroundViewport(values)
    viewport.resize(800, 480)
    viewport.set_scroll_state(80, 100)
    viewport.show()
    qt_app.processEvents()
    assert not viewport.source.isNull()
    assert not viewport.grab().isNull()
    preview.close()
    viewport.close()


def test_main_hub_exposes_pipeline_and_justice_dance_entries(qt_app):
    dialog = MainHubDialog()
    try:
        assert dialog.aihumo_button.text().startswith("AIHuMo Pipeline")
        assert dialog.justice_dance_button.text().startswith("Justice Dance")
        assert "just_dance" in dialog.game_buttons
        assert len(dialog.game_buttons) == 10
        assert len(dialog.apps) == 13
        assert [app.id for app in dialog.apps if app.section == "Movement Analysis"] == ["pipeline"]
        assert all(
            len([app for app in dialog.apps if app.section == section]) <= 3
            for section in dialog.NAV_ITEMS[1:]
        )
        assert dialog.NAV_ITEMS == (
            "Home", "Movement Analysis", "Games", "Training", "Rehabilitation", "Cognitive Games"
        )
        assert all(app.art for app in dialog.apps)
        artwork = [item for item in dialog.findChildren(ThumbnailPlaceholder) if item.image_path]
        assert artwork
        assert all(item.image_path.is_file() and not item.source.isNull() for item in artwork)
        focused_sections = [
            frame for frame in dialog.findChildren(QFrame)
            if frame.objectName() == "focusedCategorySection"
        ]
        assert len(focused_sections) == len(dialog.NAV_ITEMS) - 1
        assert "QFrame#focusedCategorySection { background: transparent; border: none; }" in dialog.styleSheet()
    finally:
        dialog.close()


def test_settings_and_batch_fit_screen_and_share_scroll_table_palettes(qt_app, tmp_path):
    store = PreferenceStore(tmp_path / "settings.json")
    store.save(DesktopPreferences(theme="Dark", setup_completed=True))
    settings = PreferencesDialog(store)
    batch = BatchSessionDialog(preferences=store)
    try:
        available = qt_app.primaryScreen().availableGeometry()
        assert settings.width() <= int(available.width() * 0.82) + 1
        assert settings.height() <= int(available.height() * 0.82) + 1
        assert batch.width() <= int(available.width() * 0.90) + 1
        assert batch.height() <= int(available.height() * 0.86) + 1
        assert not batch.windowState() & Qt.WindowState.WindowMaximized
        stylesheet = batch.styleSheet()
        assert "QScrollArea > QWidget > QWidget" in stylesheet
        assert "QTableWidget, QTableView" in stylesheet
        assert "QHeaderView::section" in stylesheet
        assert "#091426" in stylesheet
        assert batch.settings_button.isEnabled()
    finally:
        batch.close()
        settings.close()


def test_controller_refreshes_one_shared_theme_between_hub_and_pipeline(qt_app, tmp_path):
    path = tmp_path / "settings.json"
    PreferenceStore(path).save(DesktopPreferences(theme="Light", setup_completed=True))
    controller = DesktopApplicationController(state_dir=tmp_path)
    try:
        controller.show_pipeline()
        assert controller.pipeline_window is not None
        assert controller.pipeline_window.preferences is controller.preferences
        assert "#f5f7fb" in controller.pipeline_window.styleSheet()

        controller.preferences.save(DesktopPreferences(theme="Dark", setup_completed=True))
        controller.show_pipeline()
        assert "#091426" in controller.pipeline_window.styleSheet()
        controller.show_hub()
        assert "Dark" in controller.hub_window.theme_button.text()
    finally:
        if controller.pipeline_window is not None:
            controller.pipeline_window.close()
        controller.hub_window.close()


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


def test_all_apps_carousel_loops_without_changing_visible_count(qt_app):
    dialog = MainHubDialog()
    try:
        carousel = dialog.all_apps_carousel
        total = len(carousel.apps)
        carousel.set_current_index(total - 1, animated=False)
        assert carousel.current_index == total - 1
        carousel._set_position(float(total))
        assert carousel.current_index == 0
        dialog._carousel_index_changed(carousel.current_index)
        assert dialog.carousel_status.text().startswith(f"1 / {total}")
        carousel._set_position(-1.0)
        assert carousel.current_index == total - 1
        dialog._carousel_index_changed(carousel.current_index)
        assert dialog.carousel_status.text().startswith(f"{total} / {total}")
    finally:
        dialog.close()


def test_carousel_hover_translates_but_vertical_wheel_passes_to_page(qt_app):
    dialog = MainHubDialog()
    try:
        carousel = dialog.all_apps_carousel

        class HoverEvent:
            def __init__(self, x):
                self._position = QPointF(x, 100)
                self.accepted = False

            def position(self):
                return self._position

            def buttons(self):
                return Qt.MouseButton.NoButton

            def accept(self):
                self.accepted = True

        carousel._hover_x = 100
        start = carousel._position
        hover = HoverEvent(240)
        carousel.mouseMoveEvent(hover)
        assert hover.accepted
        assert carousel._position < start

        class WheelEvent:
            def __init__(self, x, y):
                self._delta = QPoint(x, y)
                self.accepted = None

            def angleDelta(self):
                return self._delta

            def accept(self):
                self.accepted = True

            def ignore(self):
                self.accepted = False

        vertical = WheelEvent(0, -120)
        carousel.wheelEvent(vertical)
        assert vertical.accepted is False
        horizontal = WheelEvent(-120, 0)
        carousel.wheelEvent(horizontal)
        assert horizontal.accepted is True
        carousel._animation.stop()
    finally:
        dialog.close()


def test_carousel_edge_hover_waits_then_advances_and_accelerates(qt_app):
    dialog = MainHubDialog()
    try:
        carousel = dialog.all_apps_carousel
        carousel.resize(1100, 340)
        advances = []
        carousel.next = lambda: advances.append("next")
        carousel.previous = lambda: advances.append("previous")

        carousel._update_edge_hover(carousel.width() - 1)
        assert carousel._edge_direction == 1
        assert carousel._edge_delay_timer.isActive()
        assert carousel._edge_delay_timer.remainingTime() <= carousel.EDGE_DWELL_MS
        assert not advances

        carousel._begin_edge_scroll()
        assert carousel._edge_active
        assert advances == ["next"]
        assert carousel._edge_step_timer.interval() == carousel.EDGE_INITIAL_INTERVAL_MS
        carousel._edge_advance()
        carousel._edge_advance()
        assert advances == ["next", "next", "next"]
        assert carousel._edge_step_timer.interval() == carousel.EDGE_FAST_INTERVAL_MS

        carousel._update_edge_hover(carousel.width() / 2)
        assert carousel._edge_direction == 0
        assert not carousel._edge_delay_timer.isActive()
        assert not carousel._edge_step_timer.isActive()

        carousel._update_edge_hover(0)
        carousel._begin_edge_scroll()
        assert advances[-1] == "previous"
    finally:
        dialog.close()


def test_hub_search_uses_game_keywords_and_relevance_order(qt_app):
    dialog = MainHubDialog()
    try:
        assert all(5 <= len(app.keywords) <= 10 for app in dialog.apps)
        pose_ids = [app.id for app in ranked_hub_apps(dialog.apps, "pose")]
        assert pose_ids[0] == "mirror_match"
        assert [app.id for app in ranked_hub_apps(dialog.apps, "dodg")] == ["flow_zone"]

        coordination = ranked_hub_apps(dialog.apps, "coordination")
        rank_groups = {}
        for app in coordination:
            rank_groups.setdefault(app.subtitle.casefold() == "coordination", []).append(app.title)
        assert rank_groups[True] == sorted(rank_groups[True], key=str.casefold)

        dialog.search.setText("pose")
        qt_app.processEvents()
        assert [app.id for app in dialog.all_apps_carousel.apps][0] == "mirror_match"
    finally:
        dialog.close()


def test_every_hub_app_button_launches_without_crashing(qt_app, tmp_path, monkeypatch):
    movement_launches = []
    cognitive_launches = []
    maximized_launches = []
    pipeline_modes = []
    pipeline_launches = []

    class FakeMovementDialog:
        def __init__(self, game_id, parent=None, *, preferences=None):
            movement_launches.append(game_id)
            assert isinstance(preferences, PreferenceStore)

        def setWindowFlag(self, *_args):
            pass

        def showMaximized(self):
            maximized_launches.append("movement")

        def exec(self):
            return 0

    class FakeCognitiveDialog:
        def __init__(self, game_id, parent=None, *, preferences=None):
            cognitive_launches.append(game_id)
            assert isinstance(preferences, PreferenceStore)

        def setWindowFlag(self, *_args):
            pass

        def showMaximized(self):
            maximized_launches.append("cognitive")

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
        assert len(maximized_launches) == len(movement_launches) + len(cognitive_launches)
        assert pipeline_modes == []
        assert pipeline_launches == ["pipeline"]
        assert len(dialog._recent_app_ids()) == 3
    finally:
        dialog.close()


def test_main_hub_supports_light_and_dark_without_galaxy(qt_app, tmp_path):
    store = PreferenceStore(tmp_path / "settings.json")
    dialog = MainHubDialog(state_dir=tmp_path, preferences=store)
    try:
        assert "Light" in dialog.theme_button.text()
        for theme in ("Dark", "Light"):
            dialog.theme_button.click()
            qt_app.processEvents()
            loaded = PreferenceStore(tmp_path / "settings.json").values
            assert loaded.theme == theme
            assert theme in dialog.theme_button.text()
            stylesheet = dialog.styleSheet()
            assert "QWidget, QLabel, QPushButton, QCheckBox" in stylesheet
            assert "QTabBar::tab:selected" in stylesheet
            assert "QComboBox QAbstractItemView::item:selected" in stylesheet
            assert "QToolTip" in stylesheet
            assert "QScrollBar::handle:vertical:hover" in stylesheet
            assert ("#7894bd" if theme == "Dark" else "#a8b6ca") in stylesheet
        assert not hasattr(dialog, "galaxy")
        assert not hasattr(dialog, "galaxy_toggle")
    finally:
        dialog.close()


def test_hub_artwork_toggle_persists_and_reloads_every_card(qt_app, tmp_path):
    store = PreferenceStore(tmp_path / "settings.json")
    dialog = MainHubDialog(state_dir=tmp_path, preferences=store)
    try:
        thumbnails = [item for item in dialog.findChildren(ThumbnailPlaceholder) if item.art]
        assert thumbnails
        assert dialog.preferences.values.hub_artwork_style == "Focus Mode"
        assert "Focus Mode" in dialog.artwork_button.text()
        assert all(item.image_path.parent == HUB_CARD_DIR for item in thumbnails)

        dialog.artwork_button.click()
        qt_app.processEvents()
        loaded = PreferenceStore(tmp_path / "settings.json").values
        assert loaded.hub_artwork_style == "Professional"
        assert "Professional" in dialog.artwork_button.text()
        assert all(item.image_path.parent == HUB_PROFESSIONAL_CARD_DIR for item in thumbnails)
        assert all(not item.source.isNull() for item in thumbnails)
        assert all(not source.isNull() for source in dialog.all_apps_carousel._sources.values())
    finally:
        dialog.close()


def test_hub_artwork_libraries_have_parity_and_pass_automated_review():
    filenames = tuple(dict.fromkeys(app.art for app in hub_apps() if app.art))
    # Retain artwork for retired cards so consolidation remains reversible,
    # while requiring complete artwork for every active Hub entry.
    assert set(filenames) <= {path.name for path in HUB_CARD_DIR.glob("*.jpg")}
    assert set(filenames) <= {path.name for path in HUB_PROFESSIONAL_CARD_DIR.glob("*.jpg")}
    focus = review_artwork_set(HUB_CARD_DIR, filenames, focus=True)
    professional = review_artwork_set(HUB_PROFESSIONAL_CARD_DIR, filenames, professional=True)
    assert all(result.passed for result in focus)
    assert all(result.passed for result in professional)


def test_main_hub_has_three_recent_slots_and_persists_unique_apps(qt_app, tmp_path):
    dialog = MainHubDialog(state_dir=tmp_path)
    try:
        assert len(dialog.recent_cards) == 3
        assert all(card.app is None for card in dialog.recent_cards)
        for app_id in ("pipeline", "spelling_bee", "balance", "pipeline"):
            dialog._remember_app(dialog.app_by_id[app_id])
        assert dialog._recent_app_ids() == ["pipeline", "balance", "spelling_bee"]
        assert [card.app.id for card in dialog.recent_cards if card.app] == [
            "pipeline", "balance", "spelling_bee"
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

