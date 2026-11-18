"""Local desktop preferences and the shared Mode 0 participant picker."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import logging
from pathlib import Path
import re

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QDoubleSpinBox, QHBoxLayout, QInputDialog, QLabel, QListWidget, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QScrollArea, QSizePolicy, QSlider, QTabBar, QTabWidget, QVBoxLayout, QWidget,
)

from aihumo.storage import load_json, save_json_atomic
from .app_paths import installer_bootstrap_path
from .subapp_style import fit_window_to_available_screen
from .timeline_layers import LAYERS, SEMANTIC_COLORS, timeline_preferences, valid_thresholds

LOGGER = logging.getLogger(__name__)
DEFAULT_FRAME_JUMP = 50
MAX_FRAME_JUMP = 10_000
COLOR_FIELDS = {
    "launcher_accent": "Selected workflow border",
    "skeleton_line": "Skeleton lines",
    "skeleton_joint": "Skeleton joints",
}
HUB_BACKGROUND_DIR = Path(__file__).resolve().parents[1] / "assets" / "hub_backgrounds"


@dataclass(frozen=True)
class DesktopPreferences:
    launcher_accent: str = "#20a253"
    skeleton_line: str = "#00ff00"
    skeleton_joint: str = "#ff0000"
    participants: tuple[str, ...] = ()
    default_participant: str = ""
    starter_video: str = ""
    starter_videos: tuple[str, ...] = ()
    starter_skeleton: str = ""
    starter_features: str = ""
    starter_annotations: str = ""
    setup_completed: bool = False
    default_frame_jump: int = DEFAULT_FRAME_JUMP
    default_camera_name: str = "camera_01"
    default_viewpoint: str = ""
    default_camera_angle: str = "Front"
    default_source_directory: str = ""
    default_skeleton_directory: str = ""
    default_features_directory: str = ""
    default_annotations_directory: str = ""
    default_output_directory: str = ""
    default_playback_speed: float = 1.0
    playback_loop: bool = False
    autosave_interval_s: int = 30
    interface_scale: float = 1.0
    theme: str = "System"
    hub_galaxy_mode: bool = False
    hub_background_mode: str = "Default"
    hub_custom_background: str = ""
    hub_background_blur: bool = True
    hub_background_blur_strength: int = 5
    hub_background_opacity: float = 0.48
    hub_parallax_strength: float = 0.65
    hub_background_style_version: int = 2
    hub_background_crop_x: float = 0.5
    hub_background_crop_y: float = 0.5
    hub_artwork_style: str = "Focus Mode"
    game_default_difficulty: str = "adaptive"
    game_countdown_s: int = 0
    game_audio_cues: bool = True
    game_show_instructions: bool = True
    game_high_contrast_targets: bool = False
    game_auto_save_results: bool = False
    game_results_directory: str = ""
    game_target_period_scale: float = 1.0
    game_calibration_s: float = 1.0
    arrow_keys_navigate: bool = True
    loop_selected_interval: bool = False
    pause_at_annotation_boundary: bool = False
    default_visualization_mode: str = "2D"
    show_skeleton_by_default: bool = True
    show_midpoint_overlay: bool = False
    show_angle_overlay: bool = False
    raw_curves_by_default: bool = True
    graph_time_window_s: float = 1.0
    zoom_to_annotation: bool = True
    smoothing_method: str = "None"
    smoothing_window: int = 5
    confidence_threshold: float = 0.5
    missing_landmark_policy: str = "Show gaps"
    derivative_gap_policy: str = "Do not cross gaps"
    generate_graph_previews: bool = True
    export_graph_images: bool = False
    output_versioning: str = "Create new version"
    minimum_free_storage_gib: float = 0.0
    default_annotation_layer: str = "activity_state"
    default_activity_state: str = "active"
    default_phase_schema: str = "eccentric, concentric, hold"
    inherit_annotation_context: bool = True
    default_form_label: str = "unlabeled"
    timeline: dict = field(default_factory=timeline_preferences)


class PreferenceStore:
    def __init__(self, path: Path):
        self.path = path
        self.values = DesktopPreferences()
        if not path.is_file():
            return
        try:
            data = load_json(path)
            if not isinstance(data, dict):
                raise ValueError("Settings must contain a JSON object.")
            colors = {
                name: color.lower() for name in COLOR_FIELDS
                if isinstance(color := data.get(name), str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)
            }
            raw = data.get("participants")
            participants = tuple(dict.fromkeys(
                value.strip() for value in raw if isinstance(value, str) and value.strip()
            )) if isinstance(raw, list) else ()
            default = data.get("default_participant")
            starter_video = data.get("starter_video")
            raw_starter_videos = data.get("starter_videos")
            starter_videos = tuple(dict.fromkeys(
                value.strip() for value in raw_starter_videos
                if isinstance(value, str) and value.strip()
            )) if isinstance(raw_starter_videos, list) else ()
            jump = data.get("default_frame_jump")
            def text(name, fallback=""):
                value = data.get(name, fallback)
                return value.strip() if isinstance(value, str) else fallback

            def bounded_number(name, fallback, low, high, integer=False):
                value = data.get(name, fallback)
                if integer and type(value) is int:
                    return max(low, min(high, value))
                if not integer and isinstance(value, (int, float)) and not isinstance(value, bool):
                    return max(low, min(high, float(value)))
                return fallback

            def flag(name, fallback):
                return data.get(name, fallback) if type(data.get(name, fallback)) is bool else fallback

            background_version = bounded_number("hub_background_style_version", 1, 1, 2, integer=True)
            background_blur_strength = bounded_number("hub_background_blur_strength", 5, 0, 30, integer=True)
            background_opacity = bounded_number("hub_background_opacity", 0.48, 0.0, 1.0)
            background_parallax = bounded_number("hub_parallax_strength", 0.65, 0.0, 1.0)
            # Version 1 shipped with values that made the light artwork nearly
            # invisible and the motion difficult to notice. Migrate only the
            # exact old defaults so deliberate user choices remain untouched.
            if background_version < 2:
                if background_blur_strength == 8:
                    background_blur_strength = 5
                if abs(background_opacity - 0.22) < 1e-9:
                    background_opacity = 0.48
                if abs(background_parallax - 0.35) < 1e-9:
                    background_parallax = 0.65

            self.values = DesktopPreferences(
                **colors, participants=participants,
                default_participant=default if default in participants else "",
                starter_video=starter_video.strip() if isinstance(starter_video, str) else "",
                starter_videos=starter_videos,
                starter_skeleton=text("starter_skeleton"),
                starter_features=text("starter_features"),
                starter_annotations=text("starter_annotations"),
                # Existing settings files are already configured users. Only a
                # brand-new settings file should show the optional first-run flow.
                setup_completed=bool(data.get("setup_completed", True)),
                default_frame_jump=jump if type(jump) is int and 1 <= jump <= MAX_FRAME_JUMP else DEFAULT_FRAME_JUMP,
                default_camera_name=text("default_camera_name", "camera_01"),
                default_viewpoint=text("default_viewpoint"),
                default_camera_angle=text("default_camera_angle", "Front") if text("default_camera_angle", "Front") in {"N/A", "Front", "Side", "Rear", "Three-quarter", "Low angle", "High angle", "Camera adjustment", "Unknown"} else "Front",
                default_source_directory=text("default_source_directory"),
                default_skeleton_directory=text("default_skeleton_directory"),
                default_features_directory=text("default_features_directory"),
                default_annotations_directory=text("default_annotations_directory"),
                default_output_directory=text("default_output_directory"),
                default_playback_speed=bounded_number("default_playback_speed", 1.0, 0.1, 5.0),
                playback_loop=flag("playback_loop", False),
                autosave_interval_s=bounded_number("autosave_interval_s", 30, 0, 3600, integer=True),
                interface_scale=bounded_number("interface_scale", 1.0, 0.75, 2.0),
                theme=text("theme", "System") if text("theme", "System") in {"System", "Light", "Dark", "High contrast"} else "System",
                hub_galaxy_mode=flag("hub_galaxy_mode", False),
                hub_background_mode=text("hub_background_mode", "Default") if text("hub_background_mode", "Default") in {"Default", "Custom"} else "Default",
                hub_custom_background=text("hub_custom_background"),
                hub_background_blur=flag("hub_background_blur", True),
                hub_background_blur_strength=background_blur_strength,
                hub_background_opacity=background_opacity,
                hub_parallax_strength=background_parallax,
                hub_background_style_version=2,
                hub_background_crop_x=bounded_number("hub_background_crop_x", 0.5, 0.0, 1.0),
                hub_background_crop_y=bounded_number("hub_background_crop_y", 0.5, 0.0, 1.0),
                hub_artwork_style=(
                    "Focus Mode" if text("hub_artwork_style", "Focus Mode") == "Vibrant"
                    else text("hub_artwork_style", "Focus Mode")
                    if text("hub_artwork_style", "Focus Mode") in {"Focus Mode", "Professional"}
                    else "Focus Mode"
                ),
                game_default_difficulty=text("game_default_difficulty", "adaptive") if text("game_default_difficulty", "adaptive") in {"adaptive", "easy", "medium", "hard"} else "adaptive",
                game_countdown_s=bounded_number("game_countdown_s", 0, 0, 10, integer=True),
                game_audio_cues=flag("game_audio_cues", True),
                game_show_instructions=flag("game_show_instructions", True),
                game_high_contrast_targets=flag("game_high_contrast_targets", False),
                game_auto_save_results=flag("game_auto_save_results", False),
                game_results_directory=text("game_results_directory"),
                game_target_period_scale=bounded_number("game_target_period_scale", 1.0, 0.5, 2.0),
                game_calibration_s=bounded_number("game_calibration_s", 1.0, 0.0, 10.0),
                arrow_keys_navigate=flag("arrow_keys_navigate", True),
                loop_selected_interval=flag("loop_selected_interval", False),
                pause_at_annotation_boundary=flag("pause_at_annotation_boundary", False),
                default_visualization_mode=text("default_visualization_mode", "2D") if text("default_visualization_mode", "2D") in {"2D", "3D"} else "2D",
                show_skeleton_by_default=flag("show_skeleton_by_default", True),
                show_midpoint_overlay=flag("show_midpoint_overlay", False),
                show_angle_overlay=flag("show_angle_overlay", False),
                raw_curves_by_default=flag("raw_curves_by_default", True),
                graph_time_window_s=bounded_number("graph_time_window_s", 1.0, 0.05, 86400.0),
                zoom_to_annotation=flag("zoom_to_annotation", True),
                smoothing_method=text("smoothing_method", "None") if text("smoothing_method", "None") in {"None", "Moving average", "Exponential moving average", "Savitzky-Golay"} else "None",
                smoothing_window=bounded_number("smoothing_window", 5, 3, 101, integer=True),
                confidence_threshold=bounded_number("confidence_threshold", 0.5, 0.0, 1.0),
                missing_landmark_policy=text("missing_landmark_policy", "Show gaps"),
                derivative_gap_policy=text("derivative_gap_policy", "Do not cross gaps"),
                generate_graph_previews=flag("generate_graph_previews", True),
                export_graph_images=flag("export_graph_images", False),
                output_versioning=text("output_versioning", "Create new version"),
                minimum_free_storage_gib=bounded_number("minimum_free_storage_gib", 0.0, 0.0, 100000.0),
                default_annotation_layer=text("default_annotation_layer", "activity_state"),
                default_activity_state=text("default_activity_state", "active"),
                default_phase_schema=text("default_phase_schema", "eccentric, concentric, hold"),
                inherit_annotation_context=flag("inherit_annotation_context", True),
                default_form_label=text("default_form_label", "unlabeled"),
                timeline=timeline_preferences(data.get("timeline")),
            )
        except (OSError, ValueError):
            LOGGER.exception("Could not read desktop settings from %s", path)

    def save(self, values: DesktopPreferences) -> None:
        save_json_atomic(asdict(values), self.path)
        self.values = values

    def reload(self) -> DesktopPreferences:
        """Refresh values written by another open AIHuMo window."""
        self.values = type(self)(self.path).values
        return self.values

    def add_participant(self, participant: str) -> None:
        participant = participant.strip()
        if participant and participant not in self.values.participants:
            self.save(replace(self.values, participants=(*self.values.participants, participant)))


def apply_installer_bootstrap(store: PreferenceStore, path: Path | None = None) -> bool:
    """Merge a native installer's one-time setup plan into desktop settings.

    Existing non-empty preferences win, so reinstalling or upgrading cannot
    silently replace a user's established folders or participant identity.
    Invalid paths remain visible in setup but are never copied or opened until
    the user confirms the first-run screen.
    """
    path = path or installer_bootstrap_path(store.path.parent)
    if not path.is_file():
        return False
    data = load_json(path)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("The installer setup plan has an unsupported format.")

    def clean(name: str) -> str:
        value = data.get(name, "")
        return value.strip() if isinstance(value, str) else ""

    raw_videos = data.get("starter_videos", [])
    videos = tuple(dict.fromkeys(
        value.strip() for value in raw_videos if isinstance(value, str) and value.strip()
    )) if isinstance(raw_videos, list) else ()
    primary = clean("starter_video") or (videos[0] if videos else "")
    current = store.values
    participant = clean("participant")
    participants = current.participants
    if participant and participant not in participants:
        participants = (*participants, participant)

    def keep(current_value: str, incoming: str) -> str:
        return current_value or incoming

    angle = clean("camera_angle")
    if angle not in {"N/A", "Front", "Side", "Rear", "Three-quarter", "Low angle", "High angle", "Camera adjustment", "Unknown"}:
        angle = ""
    store.save(replace(
        current,
        participants=participants,
        default_participant=keep(current.default_participant, participant),
        default_camera_name=keep(current.default_camera_name if current.default_camera_name != "camera_01" else "", clean("camera_name")) or "camera_01",
        default_camera_angle=angle or current.default_camera_angle,
        starter_video=keep(current.starter_video, primary),
        starter_videos=current.starter_videos or videos,
        starter_skeleton=keep(current.starter_skeleton, clean("starter_skeleton")),
        starter_features=keep(current.starter_features, clean("starter_features")),
        starter_annotations=keep(current.starter_annotations, clean("starter_annotations")),
        default_source_directory=keep(current.default_source_directory, clean("source_directory")),
        default_skeleton_directory=keep(current.default_skeleton_directory, clean("skeleton_directory")),
        default_features_directory=keep(current.default_features_directory, clean("features_directory")),
        default_annotations_directory=keep(current.default_annotations_directory, clean("annotations_directory")),
        default_output_directory=keep(current.default_output_directory, clean("output_directory")),
        setup_completed=False,
    ))
    consumed = path.with_name("installer-bootstrap.consumed.json")
    path.replace(consumed)
    return True


class StartupSetupDialog(QDialog):
    """Optional first-run setup for a participant and an opening video.

    The selected video is only bookmarked; it is never copied or uploaded.
    When it has a matching processed feature Parquet, the launcher opens the
    graph viewer. Otherwise it opens Mode 0 with the source video prefilled.
    """

    def __init__(self, store: PreferenceStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("AIHuMo first-run setup")
        self.resize(820, 720)
        outer = QVBoxLayout(self)
        intro = QLabel(
            "Set up the first-run workspace for this computer. AIHuMo remembers the "
            "participant, preferred camera angle, starter recordings, and default folders "
            "used by later file pickers. Nothing is copied or uploaded. Add several raw "
            "videos, or pair the primary video with existing processed files to open Mode 1 directly."
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)

        form = QFormLayout()
        self.participant_edit = QLineEdit(store.values.default_participant)
        self.participant_edit.setPlaceholderText("e.g. P001 or Alex")
        form.addRow("Participant ID (optional)", self.participant_edit)

        self.camera_angle_combo = QComboBox()
        for label in ("N/A", "Front", "Side", "Rear", "Three-quarter", "Low angle", "High angle", "Camera adjustment", "Unknown"):
            self.camera_angle_combo.addItem(label, label)
        self.camera_angle_combo.setCurrentText(store.values.default_camera_angle)
        form.addRow("Default camera angle", self.camera_angle_combo)

        video_row = QWidget()
        video_layout = QHBoxLayout(video_row)
        video_layout.setContentsMargins(0, 0, 0, 0)
        self.video_edit = QLineEdit(store.values.starter_video)
        self.video_edit.setPlaceholderText("Choose a source or processed skeleton video")
        browse = QPushButton("Add videos…")
        browse.clicked.connect(self._browse_videos)
        video_layout.addWidget(self.video_edit, 1)
        video_layout.addWidget(browse)
        form.addRow("Primary starter video (optional)", video_row)

        self.additional_videos = QListWidget()
        self.additional_videos.setMaximumHeight(88)
        for path in store.values.starter_videos:
            if path and path != store.values.starter_video:
                self.additional_videos.addItem(path)
        remove_video = QPushButton("Remove selected additional video")
        remove_video.clicked.connect(lambda: self.additional_videos.takeItem(self.additional_videos.currentRow()))
        starter_group = QWidget()
        starter_layout = QVBoxLayout(starter_group)
        starter_layout.setContentsMargins(0, 0, 0, 0)
        starter_layout.addWidget(self.additional_videos)
        starter_layout.addWidget(remove_video)
        form.addRow("Additional source videos", starter_group)

        self.starter_skeleton = QLineEdit(store.values.starter_skeleton)
        self.starter_features = QLineEdit(store.values.starter_features)
        self.starter_annotations = QLineEdit(store.values.starter_annotations)
        form.addRow("Matching skeleton video", self._file_row(
            self.starter_skeleton, "Choose matching skeleton video", "Video Files (*.mp4 *.mov *.avi *.mkv *.webm)"
        ))
        form.addRow("Matching feature Parquet", self._file_row(
            self.starter_features, "Choose matching feature Parquet", "Parquet Files (*.parquet)"
        ))
        form.addRow("Matching annotations", self._file_row(
            self.starter_annotations, "Choose matching annotations", "Annotation JSON (*.json)"
        ))

        self.source_directory = QLineEdit(store.values.default_source_directory)
        self.skeleton_directory = QLineEdit(store.values.default_skeleton_directory)
        self.features_directory = QLineEdit(store.values.default_features_directory)
        self.annotations_directory = QLineEdit(store.values.default_annotations_directory)
        self.output_directory = QLineEdit(store.values.default_output_directory)
        form.addRow("Default video folder", self._directory_row(self.source_directory, "Choose default video folder"))
        form.addRow("Default skeleton folder", self._directory_row(self.skeleton_directory, "Choose default skeleton folder"))
        form.addRow("Default features folder", self._directory_row(self.features_directory, "Choose default Parquet folder"))
        form.addRow("Default annotations folder", self._directory_row(self.annotations_directory, "Choose default annotation folder"))
        form.addRow("Default output folder", self._directory_row(self.output_directory, "Choose default output folder"))
        outer.addLayout(form)

        self.open_video = QCheckBox("Open the starter video after setup")
        self.open_video.setChecked(bool(store.values.starter_video))
        self.open_video.setEnabled(bool(store.values.starter_video))
        self.video_edit.textChanged.connect(self._starter_video_changed)
        outer.addWidget(self.open_video)

        actions = QHBoxLayout()
        skip = QPushButton("Skip setup")
        skip.clicked.connect(self._skip)
        actions.addWidget(skip)
        actions.addStretch(1)
        save = QPushButton("Save and continue")
        save.setDefault(True)
        save.clicked.connect(self._save)
        actions.addWidget(save)
        outer.addLayout(actions)
        self.setup = {}

    def _directory_row(self, edit: QLineEdit, title: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Browse…")
        button.clicked.connect(lambda: self._browse_directory(edit, title))
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return row

    def _file_row(self, edit: QLineEdit, title: str, file_filter: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Browse…")
        button.clicked.connect(lambda: self._browse_file(edit, title, file_filter))
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return row

    def _browse_file(self, edit: QLineEdit, title: str, file_filter: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, title, edit.text().strip() or "", file_filter)
        if path:
            edit.setText(path)

    def _browse_directory(self, edit: QLineEdit, title: str) -> None:
        path = QFileDialog.getExistingDirectory(self, title, edit.text().strip() or "")
        if path:
            edit.setText(path)

    def _starter_video_changed(self, text: str) -> None:
        has_video = bool(text.strip())
        if has_video and not self.open_video.isEnabled():
            self.open_video.setChecked(True)
        self.open_video.setEnabled(has_video)

    def _browse_video(self) -> None:
        """Backward-compatible single-file entry point used by older tests."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose starter video", self.source_directory.text().strip() or "",
            "Video Files (*.mp4 *.mov *.avi *.mkv *.webm);;All Files (*)",
        )
        if paths:
            self._set_starter_videos(paths)

    def _browse_videos(self) -> None:
        self._browse_video()

    def _set_starter_videos(self, paths: list[str]) -> None:
        paths = list(dict.fromkeys(path.strip() for path in paths if path.strip()))
        if not paths:
            return
        if not self.video_edit.text().strip():
            self.video_edit.setText(paths.pop(0))
        existing = {self.additional_videos.item(index).text() for index in range(self.additional_videos.count())}
        existing.add(self.video_edit.text().strip())
        for path in paths:
            if path not in existing:
                self.additional_videos.addItem(path)
                existing.add(path)

    def _persist(self) -> None:
        participant = self.participant_edit.text().strip()
        participants = tuple(dict.fromkeys((*self.store.values.participants, participant))) if participant else self.store.values.participants
        video = self.video_edit.text().strip()
        videos = tuple(dict.fromkeys(filter(None, (
            video,
            *(self.additional_videos.item(index).text().strip() for index in range(self.additional_videos.count())),
        ))))
        self.store.save(replace(
            self.store.values,
            participants=participants,
            default_participant=participant if participant else self.store.values.default_participant,
            starter_video=video,
            starter_videos=videos,
            starter_skeleton=self.starter_skeleton.text().strip(),
            starter_features=self.starter_features.text().strip(),
            starter_annotations=self.starter_annotations.text().strip(),
            setup_completed=True,
            default_camera_angle=self.camera_angle_combo.currentData() or "Front",
            default_source_directory=self.source_directory.text().strip(),
            default_skeleton_directory=self.skeleton_directory.text().strip(),
            default_features_directory=self.features_directory.text().strip(),
            default_annotations_directory=self.annotations_directory.text().strip(),
            default_output_directory=self.output_directory.text().strip(),
        ))
        self.setup = {
            "participant": participant,
            "video": video,
            "videos": list(videos),
            "skeleton": self.starter_skeleton.text().strip(),
            "features": self.starter_features.text().strip(),
            "annotations": self.starter_annotations.text().strip(),
            "open_video": bool(video and self.open_video.isChecked()),
            "camera_angle": self.camera_angle_combo.currentData() or "Front",
            "directories": {
                "source": self.source_directory.text().strip(),
                "skeleton": self.skeleton_directory.text().strip(),
                "features": self.features_directory.text().strip(),
                "annotations": self.annotations_directory.text().strip(),
                "output": self.output_directory.text().strip(),
            },
        }

    def _save(self) -> None:
        try:
            self._persist()
        except OSError as exc:
            QMessageBox.warning(self, "Could not save setup", str(exc))
            return
        self.accept()

    def _skip(self) -> None:
        try:
            self.store.save(replace(self.store.values, setup_completed=True))
        except OSError as exc:
            QMessageBox.warning(self, "Could not save setup", str(exc))
            return
        self.setup = {}
        self.reject()


class ParticipantPicker(QWidget):
    def __init__(self, store: PreferenceStore, parent=None):
        super().__init__(parent)
        self.store = store
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.edit = self.combo.lineEdit()
        self.edit.setPlaceholderText("Choose or enter a participant ID")
        self.combo.addItems(store.values.participants)
        self.combo.setCurrentIndex(self.combo.findText(store.values.default_participant))
        save = QPushButton("Save participant")
        save.setToolTip("Add the entered participant ID to Settings for future recordings.")
        save.clicked.connect(self._save_participant)
        layout.addWidget(self.combo, 1)
        layout.addWidget(save)

    def _save_participant(self) -> None:
        participant = self.edit.text().strip()
        if not participant:
            QMessageBox.information(self, "Participant ID", "Enter a participant ID to save.")
            return
        try:
            self.store.add_participant(participant)
        except OSError as exc:
            QMessageBox.warning(self, "Could not save participant", str(exc))
            return
        index = self.combo.findText(participant)
        if index < 0:
            self.combo.addItem(participant)
            index = self.combo.count() - 1
        self.combo.setCurrentIndex(index)


class BackgroundCropPreview(QWidget):
    """Draggable, normalized 16:9 crop selector for custom Hub backgrounds."""

    cropChanged = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = QPixmap()
        self.crop_x = 0.5
        self.crop_y = 0.5
        self._dragging = False
        self.setMinimumHeight(250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("Drag the cyan display window to choose the saved Hub framing.")

    def set_image(self, path: str) -> None:
        self.source = QPixmap(path) if path and Path(path).is_file() else QPixmap()
        self.update()

    def set_crop(self, x: float, y: float) -> None:
        self.crop_x = max(0.0, min(1.0, float(x)))
        self.crop_y = max(0.0, min(1.0, float(y)))
        self.update()

    def _image_rect(self) -> QRectF:
        area = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        if self.source.isNull():
            return area
        scale = min(area.width() / self.source.width(), area.height() / self.source.height())
        width, height = self.source.width() * scale, self.source.height() * scale
        return QRectF(area.center().x() - width / 2, area.center().y() - height / 2, width, height)

    def _crop_rect(self) -> QRectF:
        image = self._image_rect()
        aspect = 16 / 9
        if image.width() / max(1.0, image.height()) >= aspect:
            height = image.height()
            width = height * aspect
        else:
            width = image.width()
            height = width / aspect
        travel_x = max(0.0, image.width() - width)
        travel_y = max(0.0, image.height() - height)
        return QRectF(
            image.left() + travel_x * self.crop_x,
            image.top() + travel_y * self.crop_y,
            width,
            height,
        )

    def _move_crop(self, point: QPointF) -> None:
        image = self._image_rect()
        crop = self._crop_rect()
        travel_x = max(0.0, image.width() - crop.width())
        travel_y = max(0.0, image.height() - crop.height())
        if travel_x:
            self.crop_x = max(0.0, min(1.0, (point.x() - image.left() - crop.width() / 2) / travel_x))
        if travel_y:
            self.crop_y = max(0.0, min(1.0, (point.y() - image.top() - crop.height() / 2) / travel_y))
        self.cropChanged.emit(self.crop_x, self.crop_y)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        image = self._image_rect()
        painter.fillRect(self.rect(), QColor("#0c192c"))
        if self.source.isNull():
            painter.setPen(QColor("#b7c2d8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Choose a custom image to adjust its framing")
            painter.end()
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(image, self.source, QRectF(self.source.rect()))
        crop = self._crop_rect()
        mask = QPainterPath()
        mask.setFillRule(Qt.FillRule.OddEvenFill)
        mask.addRect(image)
        mask.addRoundedRect(crop, 9, 9)
        painter.fillPath(mask, QColor(3, 9, 22, 155))
        painter.setPen(QPen(QColor("#36c9d8"), 3))
        painter.drawRoundedRect(crop, 9, 9)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(crop.adjusted(10, 8, -10, -8), Qt.AlignmentFlag.AlignTop, "Hub display window")
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._crop_rect().contains(event.position()):
            self._dragging = True
            self._move_crop(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self._move_crop(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._move_crop(event.position())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class SettingsTabBar(QTabBar):
    """West-side tab menu with upright, horizontally readable labels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.window_color = QColor("#eef3f9")
        self.panel_color = QColor("#ffffff")
        self.text_color = QColor("#15213d")
        self.muted_color = QColor("#63708a")
        self.border_color = QColor("#cbd5e3")
        self.accent_color = QColor("#22bdd1")
        self._hover_index = -1
        self.setMouseTracking(True)
        self.setExpanding(False)

    def set_colors(self, *, window: str, panel: str, text: str, muted: str,
                   border: str, accent: str) -> None:
        self.window_color = QColor(window)
        self.panel_color = QColor(panel)
        self.text_color = QColor(text)
        self.muted_color = QColor(muted)
        self.border_color = QColor(border)
        self.accent_color = QColor(accent)
        self.update()

    def tabSizeHint(self, index: int) -> QSize:
        return QSize(198, 58)

    def mouseMoveEvent(self, event) -> None:
        hover = self.tabAt(event.position().toPoint())
        if hover != self._hover_index:
            self._hover_index = hover
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_index = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.window_color)
        for index in range(self.count()):
            rect = self.tabRect(index).adjusted(5, 4, -5, -4)
            selected = index == self.currentIndex()
            hovered = index == self._hover_index
            fill = self.panel_color if selected else self.window_color
            if hovered and not selected:
                fill = QColor(self.panel_color)
                fill.setAlpha(150)
            painter.setPen(QPen(self.accent_color if hovered else self.border_color, 1))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 10, 10)
            if selected:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self.accent_color)
                painter.drawRoundedRect(QRectF(rect.left(), rect.top() + 7, 4, rect.height() - 14), 2, 2)
            font = painter.font()
            font.setBold(selected)
            painter.setFont(font)
            painter.setPen(self.text_color if selected or hovered else self.muted_color)
            painter.drawText(rect.adjusted(18, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             self.tabText(index))
        painter.end()


class PreferencesDialog(QDialog):
    def __init__(self, store: PreferenceStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("AIHuMo Settings")
        fit_window_to_available_screen(
            self, preferred=(980, 700), minimum=(760, 520), coverage=(0.82, 0.82)
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)
        title = QLabel("Personalize AIHuMo", objectName="settingsTitle")
        subtitle = QLabel(
            "Choose defaults for processing, annotation, visualization, games, and the Hub background.",
            objectName="settingsSubtitle",
        )
        subtitle.setWordWrap(True)
        outer.addWidget(title)
        outer.addWidget(subtitle)
        tabs = QTabWidget(objectName="settingsTabs")
        self.settings_tab_bar = SettingsTabBar()
        tabs.setTabBar(self.settings_tab_bar)
        tabs.setTabPosition(QTabWidget.TabPosition.West)
        tabs.setDocumentMode(True)
        self.tabs = tabs
        outer.addWidget(tabs)
        general_scroll = QScrollArea()
        general_scroll.setWidgetResizable(True)
        general_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        general = QWidget(objectName="settingsPage")
        general_scroll.setWidget(general)
        tabs.addTab(general_scroll, "General")
        layout = QVBoxLayout(general)
        self.timeline = TimelineSettingsPanel(store.values.timeline)
        self.timeline.setObjectName("settingsPage")
        tabs.addTab(self.timeline, "Timeline & graphs")
        colors = QFormLayout()
        self.color_buttons = {}
        for name, title in COLOR_FIELDS.items():
            button = QPushButton()
            button.clicked.connect(lambda checked=False, field=name: self._choose_color(field))
            self.color_buttons[name] = button
            self._set_color(name, getattr(store.values, name))
            colors.addRow(title, button)
        layout.addLayout(colors)
        help_text = QLabel("Skeleton colors apply when Mode 0 renders a skeleton video.")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        layout.addWidget(QLabel("Saved participant IDs"))
        self.participants = QListWidget()
        self.participants.addItems(store.values.participants)
        layout.addWidget(self.participants)
        actions = QHBoxLayout()
        actions.addWidget(QPushButton("Add participant…", clicked=self._add_participant))
        actions.addWidget(QPushButton("Remove selected", clicked=self._remove_participant))
        actions.addStretch(1)
        layout.addLayout(actions)
        self.default_participant = QComboBox()
        self._refresh_defaults(store.values.default_participant)
        defaults = QFormLayout()
        defaults.addRow("Default in Mode 0", self.default_participant)
        self.default_frame_jump = QSpinBox()
        self.default_frame_jump.setRange(1, MAX_FRAME_JUMP)
        self.default_frame_jump.setValue(store.values.default_frame_jump)
        self.default_frame_jump.setSuffix(" frames")
        self.default_frame_jump.setToolTip("Starting Up/Down jump in Mode 1 and the Interactive Graph Viewer.")
        defaults.addRow("Default frame jump", self.default_frame_jump)
        self.default_camera_angle = QComboBox()
        self.default_camera_angle.addItems(("N/A", "Front", "Side", "Rear", "Three-quarter", "Low angle", "High angle", "Camera adjustment", "Unknown"))
        self.default_camera_angle.setCurrentText(store.values.default_camera_angle)
        defaults.addRow("Default camera angle", self.default_camera_angle)
        self.default_source_directory = QLineEdit(store.values.default_source_directory)
        self.default_skeleton_directory = QLineEdit(store.values.default_skeleton_directory)
        self.default_features_directory = QLineEdit(store.values.default_features_directory)
        self.default_annotations_directory = QLineEdit(store.values.default_annotations_directory)
        self.default_output_directory = QLineEdit(store.values.default_output_directory)
        defaults.addRow("Video folder", self._directory_row(self.default_source_directory, "Choose default video folder"))
        defaults.addRow("Skeleton folder", self._directory_row(self.default_skeleton_directory, "Choose default skeleton folder"))
        defaults.addRow("Features folder", self._directory_row(self.default_features_directory, "Choose default Parquet folder"))
        defaults.addRow("Annotations folder", self._directory_row(self.default_annotations_directory, "Choose default annotation folder"))
        defaults.addRow("Output folder", self._directory_row(self.default_output_directory, "Choose default output folder"))
        layout.addLayout(defaults)

        # Keep the existing General and Timeline pages stable while exposing
        # the broader desktop controls as additive preference pages.  Every
        # control has a safe default so older settings files remain valid.
        playback = QWidget(); tabs.addTab(playback, "Playback")
        playback.setObjectName("settingsPage")
        playback_form = QFormLayout(playback)
        self.default_camera_name = QLineEdit(store.values.default_camera_name)
        self.default_viewpoint = QLineEdit(store.values.default_viewpoint)
        self.default_playback_speed = QDoubleSpinBox(); self.default_playback_speed.setRange(0.1, 5.0); self.default_playback_speed.setSingleStep(0.1); self.default_playback_speed.setValue(store.values.default_playback_speed); self.default_playback_speed.setSuffix("×")
        self.playback_loop = QCheckBox("Loop playback"); self.playback_loop.setChecked(store.values.playback_loop)
        self.autosave_interval_s = QSpinBox(); self.autosave_interval_s.setRange(0, 3600); self.autosave_interval_s.setValue(store.values.autosave_interval_s); self.autosave_interval_s.setSuffix(" s")
        self.interface_scale = QDoubleSpinBox(); self.interface_scale.setRange(0.75, 2.0); self.interface_scale.setSingleStep(0.05); self.interface_scale.setValue(store.values.interface_scale); self.interface_scale.setSuffix("×")
        self.theme = QComboBox(); self.theme.addItems(("System", "Light", "Dark", "High contrast")); self.theme.setCurrentText(store.values.theme)
        playback_form.addRow("Default camera name", self.default_camera_name)
        playback_form.addRow("Default viewpoint", self.default_viewpoint)
        playback_form.addRow("Default playback speed", self.default_playback_speed)
        playback_form.addRow(self.playback_loop)
        playback_form.addRow("Autosave interval", self.autosave_interval_s)
        playback_form.addRow("Interface scale", self.interface_scale)
        playback_form.addRow("Theme", self.theme)

        visualization = QWidget(); tabs.addTab(visualization, "Visualization")
        visualization.setObjectName("settingsPage")
        visualization_form = QFormLayout(visualization)
        self.default_visualization_mode = QComboBox(); self.default_visualization_mode.addItems(("2D", "3D")); self.default_visualization_mode.setCurrentText(store.values.default_visualization_mode)
        self.show_skeleton_by_default = QCheckBox("Show skeleton by default"); self.show_skeleton_by_default.setChecked(store.values.show_skeleton_by_default)
        self.show_midpoint_overlay = QCheckBox("Show midpoint overlay by default"); self.show_midpoint_overlay.setChecked(store.values.show_midpoint_overlay)
        self.show_angle_overlay = QCheckBox("Show angle overlay by default"); self.show_angle_overlay.setChecked(store.values.show_angle_overlay)
        self.raw_curves_by_default = QCheckBox("Show raw curves by default"); self.raw_curves_by_default.setChecked(store.values.raw_curves_by_default)
        self.graph_time_window_s = QDoubleSpinBox(); self.graph_time_window_s.setRange(0.05, 86400.0); self.graph_time_window_s.setDecimals(2); self.graph_time_window_s.setValue(store.values.graph_time_window_s); self.graph_time_window_s.setSuffix(" s")
        self.zoom_to_annotation = QCheckBox("Zoom graphs to the selected annotation"); self.zoom_to_annotation.setChecked(store.values.zoom_to_annotation)
        self.arrow_keys_navigate = QCheckBox("Arrow keys always navigate frames"); self.arrow_keys_navigate.setChecked(store.values.arrow_keys_navigate)
        self.loop_selected_interval = QCheckBox("Loop the selected interval"); self.loop_selected_interval.setChecked(store.values.loop_selected_interval)
        self.pause_at_annotation_boundary = QCheckBox("Pause at annotation boundaries"); self.pause_at_annotation_boundary.setChecked(store.values.pause_at_annotation_boundary)
        visualization_form.addRow("Default viewer", self.default_visualization_mode)
        for control in (self.show_skeleton_by_default, self.show_midpoint_overlay, self.show_angle_overlay,
                        self.raw_curves_by_default, self.zoom_to_annotation, self.arrow_keys_navigate,
                        self.loop_selected_interval, self.pause_at_annotation_boundary):
            visualization_form.addRow(control)
        visualization_form.addRow("Default graph window", self.graph_time_window_s)

        data_page = QWidget(); tabs.addTab(data_page, "Data & processing")
        data_page.setObjectName("settingsPage")
        data_form = QFormLayout(data_page)
        self.smoothing_method = QComboBox(); self.smoothing_method.addItems(("None", "Moving average", "Exponential moving average", "Savitzky-Golay")); self.smoothing_method.setCurrentText(store.values.smoothing_method)
        self.smoothing_window = QSpinBox(); self.smoothing_window.setRange(3, 101); self.smoothing_window.setSingleStep(2); self.smoothing_window.setValue(store.values.smoothing_window)
        self.confidence_threshold = QDoubleSpinBox(); self.confidence_threshold.setRange(0.0, 1.0); self.confidence_threshold.setSingleStep(0.05); self.confidence_threshold.setValue(store.values.confidence_threshold)
        self.missing_landmark_policy = QComboBox(); self.missing_landmark_policy.addItems(("Show gaps", "Interpolate for display", "Hide invalid frames")); self.missing_landmark_policy.setCurrentText(store.values.missing_landmark_policy)
        self.derivative_gap_policy = QComboBox(); self.derivative_gap_policy.addItems(("Do not cross gaps", "Allow documented interpolation")); self.derivative_gap_policy.setCurrentText(store.values.derivative_gap_policy)
        self.generate_graph_previews = QCheckBox("Generate graph previews after Mode 0"); self.generate_graph_previews.setChecked(store.values.generate_graph_previews)
        self.export_graph_images = QCheckBox("Export PNG/SVG graph images"); self.export_graph_images.setChecked(store.values.export_graph_images)
        self.output_versioning = QComboBox(); self.output_versioning.addItems(("Create new version", "Require confirmation", "Reuse only explicitly selected version")); self.output_versioning.setCurrentText(store.values.output_versioning)
        self.minimum_free_storage_gib = QDoubleSpinBox(); self.minimum_free_storage_gib.setRange(0.0, 100000.0); self.minimum_free_storage_gib.setDecimals(1); self.minimum_free_storage_gib.setSingleStep(1.0); self.minimum_free_storage_gib.setValue(store.values.minimum_free_storage_gib); self.minimum_free_storage_gib.setSuffix(" GiB"); self.minimum_free_storage_gib.setSpecialValueText("Automatic (5% or 2 GiB)")
        data_form.addRow("Smoothing", self.smoothing_method)
        data_form.addRow("Smoothing window", self.smoothing_window)
        data_form.addRow("Confidence threshold", self.confidence_threshold)
        data_form.addRow("Missing landmark policy", self.missing_landmark_policy)
        data_form.addRow("Derivative gap policy", self.derivative_gap_policy)
        data_form.addRow(self.generate_graph_previews)
        data_form.addRow(self.export_graph_images)
        data_form.addRow("Output versioning", self.output_versioning)
        data_form.addRow("Keep this much storage free", self.minimum_free_storage_gib)

        annotation_page = QWidget(); tabs.addTab(annotation_page, "Annotation")
        annotation_page.setObjectName("settingsPage")
        annotation_form = QFormLayout(annotation_page)
        self.default_annotation_layer = QComboBox(); self.default_annotation_layer.addItems(("activity_state", "set", "rep", "phase", "form_interval", "other")); self.default_annotation_layer.setCurrentText(store.values.default_annotation_layer)
        self.default_activity_state = QComboBox(); self.default_activity_state.addItems(("active", "idle", "transition")); self.default_activity_state.setCurrentText(store.values.default_activity_state)
        self.default_phase_schema = QLineEdit(store.values.default_phase_schema)
        self.inherit_annotation_context = QCheckBox("Inherit parent set/rep context"); self.inherit_annotation_context.setChecked(store.values.inherit_annotation_context)
        self.default_form_label = QComboBox(); self.default_form_label.addItems(("unlabeled", "good", "acceptable", "poor")); self.default_form_label.setCurrentText(store.values.default_form_label)
        annotation_form.addRow("Default annotation layer", self.default_annotation_layer)
        annotation_form.addRow("Default activity state", self.default_activity_state)
        annotation_form.addRow("Default phases", self.default_phase_schema)
        annotation_form.addRow(self.inherit_annotation_context)
        annotation_form.addRow("Default form label", self.default_form_label)

        games_page = QWidget(objectName="settingsPage"); tabs.addTab(games_page, "Games")
        games_form = QFormLayout(games_page)
        self.game_default_difficulty = QComboBox()
        for label, value in (("Adaptive", "adaptive"), ("Easy", "easy"), ("Medium", "medium"), ("Hard", "hard")):
            self.game_default_difficulty.addItem(label, value)
        self.game_default_difficulty.setCurrentIndex(max(0, self.game_default_difficulty.findData(store.values.game_default_difficulty)))
        self.game_countdown_s = QSpinBox(); self.game_countdown_s.setRange(0, 10); self.game_countdown_s.setValue(store.values.game_countdown_s); self.game_countdown_s.setSuffix(" s")
        self.game_calibration_s = QDoubleSpinBox(); self.game_calibration_s.setRange(0.0, 10.0); self.game_calibration_s.setSingleStep(0.25); self.game_calibration_s.setValue(store.values.game_calibration_s); self.game_calibration_s.setSuffix(" s")
        self.game_target_period_scale = QDoubleSpinBox(); self.game_target_period_scale.setRange(0.5, 2.0); self.game_target_period_scale.setSingleStep(0.1); self.game_target_period_scale.setValue(store.values.game_target_period_scale); self.game_target_period_scale.setSuffix("×")
        self.game_target_period_scale.setToolTip("Below 1× changes targets faster; above 1× gives the player more time.")
        self.game_audio_cues = QCheckBox("Play target and success cues"); self.game_audio_cues.setChecked(store.values.game_audio_cues)
        self.game_show_instructions = QCheckBox("Show live game instructions"); self.game_show_instructions.setChecked(store.values.game_show_instructions)
        self.game_high_contrast_targets = QCheckBox("Use high-contrast targets"); self.game_high_contrast_targets.setChecked(store.values.game_high_contrast_targets)
        self.game_auto_save_results = QCheckBox("Automatically save completed game results"); self.game_auto_save_results.setChecked(store.values.game_auto_save_results)
        self.game_results_directory = QLineEdit(store.values.game_results_directory)
        games_form.addRow("Default difficulty", self.game_default_difficulty)
        games_form.addRow("Start countdown", self.game_countdown_s)
        games_form.addRow("Calibration duration", self.game_calibration_s)
        games_form.addRow("Target timing", self.game_target_period_scale)
        games_form.addRow(self.game_audio_cues)
        games_form.addRow(self.game_show_instructions)
        games_form.addRow(self.game_high_contrast_targets)
        games_form.addRow(self.game_auto_save_results)
        games_form.addRow("Results folder", self._directory_row(self.game_results_directory, "Choose game results folder"))

        background_page = QWidget(objectName="settingsPage"); tabs.addTab(background_page, "Hub background")
        background_layout = QVBoxLayout(background_page)
        background_form = QFormLayout()
        self.hub_background_mode = QComboBox(); self.hub_background_mode.addItems(("Default", "Custom")); self.hub_background_mode.setCurrentText(store.values.hub_background_mode)
        self.hub_artwork_style = QComboBox(); self.hub_artwork_style.addItems(("Focus Mode", "Professional")); self.hub_artwork_style.setCurrentText(store.values.hub_artwork_style)
        self.hub_custom_background = QLineEdit(store.values.hub_custom_background); self.hub_custom_background.setReadOnly(True)
        image_row = QWidget(); image_row_layout = QHBoxLayout(image_row); image_row_layout.setContentsMargins(0, 0, 0, 0)
        image_row_layout.addWidget(self.hub_custom_background, 1)
        choose_background = QPushButton("Choose image…"); choose_background.clicked.connect(self._browse_background)
        clear_background = QPushButton("Use default"); clear_background.clicked.connect(self._clear_background)
        image_row_layout.addWidget(choose_background); image_row_layout.addWidget(clear_background)
        self.hub_background_blur = QCheckBox("Blur the background"); self.hub_background_blur.setChecked(store.values.hub_background_blur)
        self.hub_background_blur_strength = QSpinBox(); self.hub_background_blur_strength.setRange(0, 30); self.hub_background_blur_strength.setValue(store.values.hub_background_blur_strength); self.hub_background_blur_strength.setSuffix(" px")
        self.hub_background_opacity = QSlider(Qt.Orientation.Horizontal)
        self.hub_background_opacity.setRange(0, 100)
        self.hub_background_opacity.setValue(round(store.values.hub_background_opacity * 100))
        self.hub_background_opacity.setToolTip("Increase this to make the background artwork more visible.")
        self.hub_background_opacity_value = QLabel()
        opacity_row = QWidget(); opacity_layout = QHBoxLayout(opacity_row); opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.addWidget(QLabel("Subtle")); opacity_layout.addWidget(self.hub_background_opacity, 1); opacity_layout.addWidget(QLabel("Bold")); opacity_layout.addWidget(self.hub_background_opacity_value)
        self.hub_parallax_strength = QSlider(Qt.Orientation.Horizontal)
        self.hub_parallax_strength.setRange(0, 100)
        self.hub_parallax_strength.setValue(round(store.values.hub_parallax_strength * 100))
        self.hub_parallax_strength.setToolTip("Sticky keeps the artwork anchored; Dynamic lets it travel more as the page scrolls.")
        self.hub_parallax_value = QLabel()
        parallax_row = QWidget(); parallax_layout = QHBoxLayout(parallax_row); parallax_layout.setContentsMargins(0, 0, 0, 0)
        parallax_layout.addWidget(QLabel("Sticky")); parallax_layout.addWidget(self.hub_parallax_strength, 1); parallax_layout.addWidget(QLabel("Dynamic")); parallax_layout.addWidget(self.hub_parallax_value)
        background_form.addRow("Artwork style", self.hub_artwork_style)
        background_form.addRow("Background source", self.hub_background_mode)
        background_form.addRow("Custom image", image_row)
        background_form.addRow(self.hub_background_blur)
        background_form.addRow("Blur strength", self.hub_background_blur_strength)
        background_form.addRow("Background strength", opacity_row)
        background_form.addRow("Scroll behavior", parallax_row)
        background_layout.addLayout(background_form)
        framing = QLabel("Drag the cyan rectangle to choose which part of the image remains visible after it fills the Hub window.", objectName="settingsHint")
        framing.setWordWrap(True)
        background_layout.addWidget(framing)
        self.background_crop_preview = BackgroundCropPreview()
        self.background_crop_preview.set_crop(store.values.hub_background_crop_x, store.values.hub_background_crop_y)
        self.background_crop_preview.cropChanged.connect(self._background_crop_changed)
        background_layout.addWidget(self.background_crop_preview)
        self._refresh_background_preview()
        self.hub_background_mode.currentTextChanged.connect(self._background_mode_changed)
        self.hub_background_blur.toggled.connect(self.hub_background_blur_strength.setEnabled)
        self.hub_background_opacity.valueChanged.connect(self._update_background_slider_labels)
        self.hub_parallax_strength.valueChanged.connect(self._update_background_slider_labels)
        self.hub_background_blur_strength.setEnabled(self.hub_background_blur.isChecked())
        self._update_background_slider_labels()
        self._background_mode_changed(self.hub_background_mode.currentText())

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        for form in self.findChildren(QFormLayout):
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(12)
        self._apply_style()

    def _update_background_slider_labels(self, *_args) -> None:
        self.hub_background_opacity_value.setText(f"{self.hub_background_opacity.value()}%")
        movement = self.hub_parallax_strength.value()
        if movement == 0:
            label = "Sticky"
        elif movement < 35:
            label = "Gentle"
        elif movement < 70:
            label = "Balanced"
        else:
            label = "Dynamic"
        self.hub_parallax_value.setText(f"{label} · {movement}%")

    def _apply_style(self) -> None:
        dark = self.store.values.theme in {"Dark", "High contrast"}
        if dark:
            window, panel, field = "#091426", "#101d33", "#16263f"
            text, muted, border, accent = "#f5f7ff", "#b7c2d8", "#496384", "#36c9d8"
        else:
            window, panel, field = "#eef3f9", "#ffffff", "#f7f9fc"
            text, muted, border, accent = "#15213d", "#63708a", "#cbd5e3", "#22bdd1"
        self.settings_tab_bar.set_colors(
            window=window, panel=panel, text=text, muted=muted, border=border, accent=accent,
        )
        self.setStyleSheet(f"""
            QDialog {{ background: {window}; color: {text}; font-family: "Segoe UI"; }}
            QWidget, QLabel, QCheckBox, QGroupBox {{ color: {text}; }}
            QLabel#settingsTitle {{ font-size: 25px; font-weight: 800; }}
            QLabel#settingsSubtitle, QLabel#settingsHint {{ color: {muted}; font-size: 13px; }}
            QTabWidget#settingsTabs::pane {{ background: {panel}; border: 1px solid {border}; border-radius: 14px; }}
            QTabBar::tab {{ color: {muted}; background: {window}; border: 1px solid {border}; min-width: 180px; padding: 12px 14px; text-align: left; }}
            QTabBar::tab:selected {{ color: {text}; background: {panel}; border-left: 4px solid {accent}; font-weight: 700; }}
            QTabBar::tab:hover {{ color: {text}; border-color: {accent}; }}
            QWidget#settingsPage {{ background: {panel}; }}
            QScrollArea, QScrollArea > QWidget > QWidget {{ background: {panel}; border: none; }}
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget {{ color: {text}; background: {field}; border: 1px solid {border}; border-radius: 9px; padding: 7px 9px; selection-background-color: {accent}; }}
            QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {muted}; background: {window}; }}
            QComboBox QAbstractItemView {{ color: {text}; background: {panel}; border: 1px solid {border}; selection-background-color: {accent}; selection-color: #07152f; }}
            QPushButton {{ color: {text}; background: {field}; border: 1px solid {border}; border-radius: 9px; min-height: 22px; padding: 8px 12px; }}
            QPushButton:hover {{ border-color: {accent}; }}
            QPushButton:default, QDialogButtonBox QPushButton {{ background: {accent}; color: #07152f; font-weight: 700; }}
            QToolTip {{ color: {text}; background: {panel}; border: 1px solid {accent}; }}
            QSlider::groove:horizontal {{ background: {border}; height: 6px; border-radius: 3px; }}
            QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {panel}; border: 2px solid {accent}; width: 18px; margin: -7px 0; border-radius: 9px; }}
            QSlider::handle:horizontal:hover {{ background: {accent}; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px; }}
            QScrollBar::handle:vertical {{ background: {accent}; min-height: 35px; border-radius: 5px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def _default_background_path(self) -> str:
        dark = self.store.values.theme in {"Dark", "High contrast"}
        return str(HUB_BACKGROUND_DIR / ("dark.png" if dark else "light.png"))

    def _refresh_background_preview(self) -> None:
        custom = self.hub_custom_background.text().strip()
        path = custom if self.hub_background_mode.currentText() == "Custom" and Path(custom).is_file() else self._default_background_path()
        self.background_crop_preview.set_image(path)

    def _background_mode_changed(self, mode: str) -> None:
        self.hub_custom_background.setEnabled(mode == "Custom")
        self._refresh_background_preview()

    def _browse_background(self) -> None:
        start = self.hub_custom_background.text().strip() or self.store.values.default_source_directory
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Hub background", start,
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)",
        )
        if path:
            self.hub_custom_background.setText(path)
            self.hub_background_mode.setCurrentText("Custom")
            self._refresh_background_preview()

    def _clear_background(self) -> None:
        self.hub_custom_background.clear()
        self.hub_background_mode.setCurrentText("Default")
        self._refresh_background_preview()

    def _background_crop_changed(self, x: float, y: float) -> None:
        # The preview owns the normalized values; this slot exists so future
        # live-preview consumers can subscribe without changing the widget API.
        self.background_crop_preview.crop_x = x
        self.background_crop_preview.crop_y = y

    def _directory_row(self, edit: QLineEdit, title: str) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Browse…")
        button.clicked.connect(lambda: self._browse_directory(edit, title))
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(button)
        return row

    def _browse_directory(self, edit: QLineEdit, title: str) -> None:
        path = QFileDialog.getExistingDirectory(self, title, edit.text().strip() or "")
        if path:
            edit.setText(path)

    def _set_color(self, field: str, color: str) -> None:
        button = self.color_buttons[field]
        button.setText(color)
        button.setStyleSheet(f"border-left: 16px solid {color}; padding: 4px 12px;")

    def _choose_color(self, field: str) -> None:
        choice = QColorDialog.getColor(QColor(self.color_buttons[field].text()), self, COLOR_FIELDS[field])
        if choice.isValid():
            self._set_color(field, choice.name())

    def _ids(self) -> tuple[str, ...]:
        return tuple(self.participants.item(i).text() for i in range(self.participants.count()))

    def _refresh_defaults(self, selected: str) -> None:
        self.default_participant.clear()
        self.default_participant.addItem("Choose when processing", "")
        for participant in self._ids():
            self.default_participant.addItem(participant, participant)
        self.default_participant.setCurrentIndex(max(0, self.default_participant.findData(selected)))

    def _add_participant(self) -> None:
        text, accepted = QInputDialog.getText(self, "Add participant", "Participant ID")
        participant = text.strip()
        if accepted and participant and participant not in self._ids():
            self.participants.addItem(participant)
            self._refresh_defaults(self.default_participant.currentData())

    def _remove_participant(self) -> None:
        row = self.participants.currentRow()
        if row >= 0:
            self.participants.takeItem(row)
            self._refresh_defaults(self.default_participant.currentData())

    def _save(self) -> None:
        timeline = self.timeline.values()
        if not valid_thresholds(timeline["thresholds"]):
            QMessageBox.warning(self, "Semantic zoom", "Use Activity/Exercise ≥ Set ≥ Repetition ≥ Phase.")
            return
        values = DesktopPreferences(
            **{name: button.text() for name, button in self.color_buttons.items()},
            participants=self._ids(), default_participant=self.default_participant.currentData(),
            starter_video=self.store.values.starter_video,
            setup_completed=self.store.values.setup_completed,
            default_frame_jump=self.default_frame_jump.value(),
            default_camera_name=self.default_camera_name.text().strip(),
            default_viewpoint=self.default_viewpoint.text().strip(),
            default_camera_angle=self.default_camera_angle.currentText(),
            default_source_directory=self.default_source_directory.text().strip(),
            default_skeleton_directory=self.default_skeleton_directory.text().strip(),
            default_features_directory=self.default_features_directory.text().strip(),
            default_annotations_directory=self.default_annotations_directory.text().strip(),
            default_output_directory=self.default_output_directory.text().strip(),
            default_playback_speed=self.default_playback_speed.value(),
            playback_loop=self.playback_loop.isChecked(),
            autosave_interval_s=self.autosave_interval_s.value(),
            interface_scale=self.interface_scale.value(),
            theme=self.theme.currentText(),
            # Keep the legacy value readable so old settings files remain
            # compatible, but the retired Galaxy layout is no longer exposed.
            hub_galaxy_mode=False,
            hub_background_mode=self.hub_background_mode.currentText(),
            hub_custom_background=self.hub_custom_background.text().strip(),
            hub_background_blur=self.hub_background_blur.isChecked(),
            hub_background_blur_strength=self.hub_background_blur_strength.value(),
            hub_background_opacity=self.hub_background_opacity.value() / 100,
            hub_parallax_strength=self.hub_parallax_strength.value() / 100,
            hub_background_crop_x=self.background_crop_preview.crop_x,
            hub_background_crop_y=self.background_crop_preview.crop_y,
            hub_artwork_style=self.hub_artwork_style.currentText(),
            game_default_difficulty=self.game_default_difficulty.currentData(),
            game_countdown_s=self.game_countdown_s.value(),
            game_audio_cues=self.game_audio_cues.isChecked(),
            game_show_instructions=self.game_show_instructions.isChecked(),
            game_high_contrast_targets=self.game_high_contrast_targets.isChecked(),
            game_auto_save_results=self.game_auto_save_results.isChecked(),
            game_results_directory=self.game_results_directory.text().strip(),
            game_target_period_scale=self.game_target_period_scale.value(),
            game_calibration_s=self.game_calibration_s.value(),
            arrow_keys_navigate=self.arrow_keys_navigate.isChecked(),
            loop_selected_interval=self.loop_selected_interval.isChecked(),
            pause_at_annotation_boundary=self.pause_at_annotation_boundary.isChecked(),
            default_visualization_mode=self.default_visualization_mode.currentText(),
            show_skeleton_by_default=self.show_skeleton_by_default.isChecked(),
            show_midpoint_overlay=self.show_midpoint_overlay.isChecked(),
            show_angle_overlay=self.show_angle_overlay.isChecked(),
            raw_curves_by_default=self.raw_curves_by_default.isChecked(),
            graph_time_window_s=self.graph_time_window_s.value(),
            zoom_to_annotation=self.zoom_to_annotation.isChecked(),
            smoothing_method=self.smoothing_method.currentText(),
            smoothing_window=self.smoothing_window.value(),
            confidence_threshold=self.confidence_threshold.value(),
            missing_landmark_policy=self.missing_landmark_policy.currentText(),
            derivative_gap_policy=self.derivative_gap_policy.currentText(),
            generate_graph_previews=self.generate_graph_previews.isChecked(),
            export_graph_images=self.export_graph_images.isChecked(),
            output_versioning=self.output_versioning.currentText(),
            minimum_free_storage_gib=self.minimum_free_storage_gib.value(),
            default_annotation_layer=self.default_annotation_layer.currentText(),
            default_activity_state=self.default_activity_state.currentText(),
            default_phase_schema=self.default_phase_schema.text().strip(),
            inherit_annotation_context=self.inherit_annotation_context.isChecked(),
            default_form_label=self.default_form_label.currentText(),
            timeline=timeline,
        )
        try:
            self.store.save(values)
        except OSError as exc:
            QMessageBox.warning(self, "Could not save settings", str(exc))
            return
        self.accept()


class TimelineSettingsPanel(QWidget):
    def __init__(self, settings):
        super().__init__()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.style = QComboBox()
        self.style.addItems(("Off", "Overlay", "Timeline"))
        form.addRow("Default view", self.style)
        self.auto = QCheckBox("Use visible duration")
        form.addRow("Semantic zoom", self.auto)
        self.thresholds = []
        for label in ("Activity / Exercise", "Set", "Repetition", "Phase / Form / Quality"):
            field = QSpinBox()
            field.setRange(1, 86400)
            field.setSuffix(" s")
            form.addRow(label, field)
            self.thresholds.append(field)
        self.category = QComboBox()
        for key, label in LAYERS.items():
            self.category.addItem(label, key)
        form.addRow("Layer appearance", self.category)
        self.layer_stack = QTabWidget()
        self.layer_stack.tabBar().hide()
        layout.addWidget(self.layer_stack, 1)
        self.fields = {}
        for key, label in LAYERS.items():
            page = QWidget()
            rows = QFormLayout(page)
            visible, alternate = QCheckBox("Show layer"), QCheckBox("Alternate neighboring intervals")
            rows.addRow(visible)
            rows.addRow(alternate)
            primary, secondary = self._color_button(), self._color_button()
            rows.addRow("Primary", primary)
            rows.addRow("Alternate", secondary)
            alternate.toggled.connect(secondary.setEnabled)
            opacity = QSpinBox()
            opacity.setRange(0, 100)
            opacity.setSuffix(" %")
            rows.addRow("Overlay opacity", opacity)
            semantic = {}
            for state in SEMANTIC_COLORS.get(key, {}):
                semantic[state] = button = self._color_button()
                rows.addRow(state.replace("_", " ").title(), button)
            self.fields[key] = visible, alternate, primary, secondary, opacity, semantic
            self.layer_stack.addTab(page, label)
        self.category.currentIndexChanged.connect(self.layer_stack.setCurrentIndex)
        layout.addWidget(QPushButton("Reset timeline settings", clicked=lambda: self._load(timeline_preferences())))
        self._load(timeline_preferences(settings))

    def _color_button(self):
        button = QPushButton()

        def choose():
            color = QColorDialog.getColor(QColor(button.text()), self, "Timeline color")
            if color.isValid():
                self._set_color(button, color.name())

        button.clicked.connect(choose)
        return button

    @staticmethod
    def _set_color(button, color):
        button.setText(color)
        button.setStyleSheet(f"border-left: 16px solid {color}; padding-left: 5px;")

    def _load(self, settings):
        self.style.setCurrentText(settings["style"])
        self.auto.setChecked(settings["auto"])
        for spin, seconds in zip(self.thresholds, settings["thresholds"]):
            spin.setValue(seconds)
        for key, (visible, alternate, primary, secondary, opacity, semantic) in self.fields.items():
            layer = settings["layers"][key]
            visible.setChecked(layer["visible"])
            alternate.setChecked(layer["alternate"])
            secondary.setEnabled(layer["alternate"])
            self._set_color(primary, layer["color"])
            self._set_color(secondary, layer["alternate_color"])
            opacity.setValue(round(layer["opacity"] * 100))
            for name, button in semantic.items():
                self._set_color(button, layer["semantic"][name])

    def values(self):
        return {
            "style": self.style.currentText(), "auto": self.auto.isChecked(),
            "thresholds": [field.value() for field in self.thresholds],
            "layers": {key: {"visible": visible.isChecked(), "alternate": alternate.isChecked(),
                             "color": primary.text(), "alternate_color": secondary.text(),
                             "opacity": opacity.value() / 100,
                             "semantic": {name: button.text() for name, button in semantic.items()}}
                       for key, (visible, alternate, primary, secondary, opacity, semantic) in self.fields.items()},
        }
