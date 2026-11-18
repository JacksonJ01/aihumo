"""Primary AIHuMo desktop hub and app catalogue."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap, QPolygonF,
    QTextOption, QTransform,
)
from PyQt6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout,
    QWidget,
)

from aihumo.storage import load_json, save_json_atomic
from .cognitive_games import CognitiveGameDialog
from .app_guides import guide_for
from .how_to_dialog import HowToDialog
from .movement_games import MovementGameDialog, load_game_definitions
from .preferences import DesktopPreferences, HUB_BACKGROUND_DIR, PreferenceStore, PreferencesDialog
from .app_paths import user_data_dir

HUB_CARD_DIR = Path(__file__).resolve().parents[1] / "assets" / "hub_cards_v2"
HUB_PROFESSIONAL_CARD_DIR = Path(__file__).resolve().parents[1] / "assets" / "hub_cards_professional"


def hub_card_directory(style: str) -> Path:
    """Resolve the persisted Hub artwork style without mutating global state."""
    return HUB_PROFESSIONAL_CARD_DIR if style == "Professional" else HUB_CARD_DIR


@dataclass(frozen=True)
class HubApp:
    id: str
    title: str
    subtitle: str
    description: str
    section: str
    art: str = ""
    keywords: tuple[str, ...] = ()
    mode: int | None = None
    game_id: str | None = None
    cognitive_game_id: str | None = None


CATEGORY_DESCRIPTIONS = {
    "Movement Analysis": (
        "Prepare recordings, create layered annotations, align sessions, and inspect synchronized "
        "2D or 3D measurements. These workspaces share the same processed videos and feature files."
    ),
    "Games": (
        "Reaction, rhythm, coordination, agility, and social movement experiences driven by the "
        "shared AIHuMo pose and game-rule engines."
    ),
    "Training": (
        "Focused drills for balance, controlled movement, sport reaction, and repeatable skills. "
        "Difficulty and scoring can build on each participant's movement range."
    ),
    "Rehabilitation": (
        "Controlled range-of-motion, gait, posture, and ergonomic review tools. These workspaces are "
        "analysis aids and do not replace professional medical judgment."
    ),
    "Cognitive Games": (
        "Memory, sequencing, spelling, and mathematics activities. Some combine thinking with movement; "
        "others can be played without a camera or pose features."
    ),
}


PIPELINE_APPS = (
    HubApp(
        "pipeline", "AIHuMo Pipeline", "Process · Annotate · Analyze",
        "Open the complete AIHuMo Data Studio launcher and choose any processing, annotation, alignment, or graph workflow.",
        "Movement Analysis", art="pipeline.jpg",
        keywords=("processing", "video", "features", "mediapipe", "skeleton", "workflow", "parquet", "dataset"),
    ),
)


COGNITIVE_APPS = (
    HubApp(
        "spelling_bee", "Spelling Bee", "Words · Definitions · Recall",
        "Practice spelling from the AIHuMo dictionary with definitions, difficulty controls, rounds, and score feedback.",
        "Cognitive Games", art="spelling_bee.jpg",
        keywords=("words", "letters", "vocabulary", "definition", "recall", "language", "bee", "literacy"),
        cognitive_game_id="spelling_bee",
    ),
    HubApp(
        "math_challenge", "Math Challenge", "Arithmetic · Accuracy · Recall",
        "Solve addition, subtraction, multiplication, and division prompts with adjustable rounds and scoring.",
        "Cognitive Games", art="math_challenge.jpg",
        keywords=("arithmetic", "numbers", "addition", "subtraction", "multiplication", "division", "calculation", "recall"),
        cognitive_game_id="math_challenge",
    ),
)


GAME_SECTIONS = {
    "just_dance": "Games",
    "flow_zone": "Games",
    "mirror_match": "Games",
    "balance": "Training",
    "path_precision": "Training",
    "sports": "Training",
    "rehab": "Rehabilitation",
    "ergonomics": "Rehabilitation",
    "gait": "Rehabilitation",
    "sequence": "Cognitive Games",
}


GAME_SEARCH_TERMS = {
    "just_dance": ("dance", "music", "choreography", "beat", "tempo", "rhythm", "timing", "coordination"),
    "flow_zone": ("zones", "grid", "targets", "reaction", "avoidance", "dodge", "agility", "precision"),
    "mirror_match": ("pose", "symmetry", "imitation", "freeze", "partner", "social", "alignment", "control"),
    "path_precision": ("trajectory", "tracing", "route", "smoothness", "reach", "precision", "accuracy", "coordination"),
    "sequence": ("memory", "order", "colors", "numbers", "recall", "pattern", "cognitive", "zones"),
    "balance": ("stability", "sway", "center", "posture", "control", "equilibrium", "reach", "coordination"),
    "sports": ("athletics", "reflexes", "reach", "stance", "boxing", "tennis", "goalkeeper", "reaction"),
    "rehab": ("rehabilitation", "therapy", "range", "mobility", "controlled", "recovery", "assessment", "movement"),
    "ergonomics": ("posture", "lifting", "desk", "workplace", "reaching", "bending", "risk", "assessment"),
    "gait": ("walking", "stride", "steps", "symmetry", "cadence", "locomotion", "turning", "balance"),
}


# Consolidated apps use dedicated artwork that communicates every merged
# challenge family rather than inheriting one retired mode's thumbnail.
GAME_ART = {
    "flow_zone": "flow_zone.jpg",
    "mirror_match": "mirror_match.jpg",
    "path_precision": "path_precision.jpg",
}


def hub_apps() -> tuple[HubApp, ...]:
    games: list[HubApp] = []
    for definition in load_game_definitions():
        section = GAME_SECTIONS.get(definition.id, "Games")
        games.append(HubApp(
            definition.id,
            definition.title,
            definition.category,
            f"{definition.description} Objective: {definition.objective}",
            section,
            art=GAME_ART.get(definition.id, f"{definition.id}.jpg"),
            keywords=GAME_SEARCH_TERMS[definition.id],
            game_id=definition.id,
        ))
    return (*PIPELINE_APPS, *games, *COGNITIVE_APPS)


def hub_app_search_rank(app: HubApp, query: str) -> tuple[int, str] | None:
    """Return a stable relevance rank; secondary matches tie by app title."""
    query = query.casefold().strip()
    title = app.title.casefold()
    subtitle = app.subtitle.casefold()
    description = app.description.casefold()
    section = app.section.casefold()
    keywords = tuple(term.casefold() for term in app.keywords)
    if not query:
        return 0, title
    if title == query:
        return 0, title
    if title.startswith(query):
        return 1, title
    if query in title:
        return 2, title
    if query in subtitle:
        return 3, title
    if query in keywords:
        return 4, title
    if any(term.startswith(query) for term in keywords):
        return 5, title
    if any(query in term for term in keywords):
        return 6, title
    if query in description:
        return 7, title
    if query in section:
        return 8, title
    return None


def ranked_hub_apps(apps: tuple[HubApp, ...], query: str) -> tuple[HubApp, ...]:
    if not query.strip():
        return tuple(apps)
    matches = ((rank, app) for app in apps if (rank := hub_app_search_rank(app, query)) is not None)
    return tuple(app for _, app in sorted(matches, key=lambda item: item[0]))


class ThumbnailPlaceholder(QLabel):
    """Card artwork, or a blank reserved area when no recent app exists."""

    def __init__(self, art: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("thumbnailPlaceholder")
        self.art = art
        self.artwork_style = "Focus Mode"
        self.image_path = hub_card_directory(self.artwork_style) / art if art else None
        self.source = QPixmap(str(self.image_path)) if self.image_path else QPixmap()
        self.setAccessibleName("App artwork" if not self.source.isNull() else "Thumbnail placeholder")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(176, 104)
        self.setMaximumHeight(126)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._update_pixmap()

    def set_artwork_style(self, style: str) -> None:
        style = "Professional" if style == "Professional" else "Focus Mode"
        if style == self.artwork_style:
            return
        self.artwork_style = style
        self.image_path = hub_card_directory(style) / self.art if self.art else None
        self.source = QPixmap(str(self.image_path)) if self.image_path else QPixmap()
        self.setAccessibleName("App artwork" if not self.source.isNull() else "Thumbnail placeholder")
        self.clear()
        self._update_pixmap()

    def resizeEvent(self, event):
        self._update_pixmap()
        super().resizeEvent(event)

    def _update_pixmap(self) -> None:
        if self.source.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        scaled = self.source.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - self.width()) // 2)
        y = max(0, (scaled.height() - self.height()) // 2)
        self.setPixmap(scaled.copy(x, y, self.width(), self.height()))


class PerspectiveAppCarousel(QWidget):
    """Smooth, image-first 2.5D carousel for the complete app catalogue."""

    currentIndexChanged = pyqtSignal(int)
    EDGE_DWELL_MS = 3000
    EDGE_INITIAL_INTERVAL_MS = 1000
    EDGE_FAST_INTERVAL_MS = 500
    EDGE_ACCELERATE_AFTER_STEPS = 3

    def __init__(self, apps: tuple[HubApp, ...], launch: Callable[[HubApp], None], parent=None):
        super().__init__(parent)
        self.apps = tuple(apps)
        self.launch = launch
        self._position = 0.0
        self._dark = False
        self._hit_polygons: list[tuple[int, QPolygonF]] = []
        self._press_point: QPointF | None = None
        self._press_position = 0.0
        self._dragged = False
        self._hover_x: float | None = None
        self._edge_direction = 0
        self._edge_active = False
        self._edge_step_count = 0
        self._last_emitted_index = 0
        self._sources = {
            app.id: QPixmap(str(HUB_CARD_DIR / app.art)) if app.art else QPixmap()
            for app in self.apps
        }
        self._artwork_style = "Focus Mode"
        self._card_cache: dict[tuple[str, bool, bool], QPixmap] = {}
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(420)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._animation_value_changed)
        self._animation.finished.connect(self._normalize_position)
        self._edge_delay_timer = QTimer(self)
        self._edge_delay_timer.setSingleShot(True)
        self._edge_delay_timer.setInterval(self.EDGE_DWELL_MS)
        self._edge_delay_timer.timeout.connect(self._begin_edge_scroll)
        self._edge_step_timer = QTimer(self)
        self._edge_step_timer.setInterval(self.EDGE_INITIAL_INTERVAL_MS)
        self._edge_step_timer.timeout.connect(self._edge_advance)
        self.setMinimumHeight(330)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("All Apps perspective carousel")
        self.setToolTip(
            "Drag, use the mouse wheel, press Left and Right, or hold the pointer "
            "at either edge for three seconds to auto-browse. "
            "Select the centered card again to open it."
        )

    @property
    def current_index(self) -> int:
        if not self.apps:
            return -1
        return int(round(self._position)) % len(self.apps)

    @property
    def current_app(self) -> HubApp | None:
        return self.apps[self.current_index] if self.current_index >= 0 else None

    def set_dark(self, dark: bool) -> None:
        self._dark = bool(dark)
        self.update()

    def set_artwork_style(self, style: str) -> None:
        style = "Professional" if style == "Professional" else "Focus Mode"
        if style == self._artwork_style:
            return
        self._artwork_style = style
        directory = hub_card_directory(style)
        self._sources = {
            app.id: QPixmap(str(directory / app.art)) if app.art else QPixmap()
            for app in self.apps
        }
        self._card_cache.clear()
        self.update()

    def set_apps(self, apps: tuple[HubApp, ...]) -> None:
        self._stop_edge_hover()
        current_id = self.current_app.id if self.current_app else None
        self.apps = tuple(apps)
        directory = hub_card_directory(self._artwork_style)
        for app in self.apps:
            self._sources.setdefault(
                app.id, QPixmap(str(directory / app.art)) if app.art else QPixmap()
            )
        index = next((i for i, app in enumerate(self.apps) if app.id == current_id), 0)
        self._last_emitted_index = -2
        self._animation.stop()
        self._set_position(float(index))

    def set_current_index(self, index: int, *, animated: bool = True) -> None:
        if not self.apps:
            self._position = 0.0
            self._last_emitted_index = -1
            self.currentIndexChanged.emit(-1)
            self.update()
            return
        normalized = int(index) % len(self.apps)
        cycle = round((self._position - normalized) / len(self.apps))
        target = float(normalized + cycle * len(self.apps))
        self._animation.stop()
        if not animated:
            self._set_position(target)
            return
        self._animate_to_position(target)

    def previous(self) -> None:
        if self.apps:
            self._animate_to_position(round(self._position) - 1)

    def next(self) -> None:
        if self.apps:
            self._animate_to_position(round(self._position) + 1)

    def activate_current(self) -> None:
        if self.current_app is not None:
            self.launch(self.current_app)

    def _animation_value_changed(self, value) -> None:
        self._set_position(float(value))

    def _animate_to_position(self, target: float) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(float(target))
        self._animation.start()

    def _normalize_position(self) -> None:
        if self.apps:
            self._position = float(self.current_index)
            self.update()

    def _set_position(self, value: float) -> None:
        self._position = float(value)
        index = self.current_index
        if index != self._last_emitted_index:
            self._last_emitted_index = index
            self.currentIndexChanged.emit(index)
        self.update()

    def _edge_zone(self, x: float) -> int:
        if len(self.apps) <= 1 or self.width() <= 0:
            return 0
        edge_width = min(160.0, max(84.0, self.width() * 0.14))
        if x <= edge_width:
            return -1
        if x >= self.width() - edge_width:
            return 1
        return 0

    def _update_edge_hover(self, x: float) -> None:
        direction = self._edge_zone(x)
        if direction == self._edge_direction:
            return
        self._stop_edge_hover()
        self._edge_direction = direction
        if direction and self._press_point is None:
            self._edge_delay_timer.start(self.EDGE_DWELL_MS)
        self.update()

    def _stop_edge_hover(self) -> None:
        self._edge_delay_timer.stop()
        self._edge_step_timer.stop()
        self._edge_direction = 0
        self._edge_active = False
        self._edge_step_count = 0
        self.update()

    def _begin_edge_scroll(self) -> None:
        if not self._edge_direction or self._press_point is not None or len(self.apps) <= 1:
            return
        self._edge_active = True
        self._edge_step_count = 0
        self._edge_step_timer.setInterval(self.EDGE_INITIAL_INTERVAL_MS)
        self._edge_advance()
        self._edge_step_timer.start()
        self.update()

    def _edge_advance(self) -> None:
        if not self._edge_direction or len(self.apps) <= 1:
            self._stop_edge_hover()
            return
        if self._edge_direction < 0:
            self.previous()
        else:
            self.next()
        self._edge_step_count += 1
        if self._edge_step_count >= self.EDGE_ACCELERATE_AFTER_STEPS:
            self._edge_step_timer.setInterval(self.EDGE_FAST_INTERVAL_MS)

    def _metrics(self) -> tuple[float, float, float, float]:
        card_width = min(470.0, max(310.0, self.width() * 0.39))
        card_height = card_width * 0.60
        spacing = min(card_width * 0.63, max(175.0, self.width() * 0.225))
        center_y = max(card_height / 2 + 24.0, self.height() / 2 - 2.0)
        return card_width, card_height, spacing, center_y

    @staticmethod
    def _quad_for_offset(center_x: float, center_y: float, width: float, height: float,
                         offset: float) -> QPolygonF:
        depth = min(1.0, abs(offset))
        inner_inset = height * 0.018 * depth
        outer_inset = height * 0.145 * depth
        left = center_x - width / 2
        right = center_x + width / 2
        top = center_y - height / 2
        bottom = center_y + height / 2
        if offset > 0:
            return QPolygonF([
                QPointF(left, top + inner_inset), QPointF(right, top + outer_inset),
                QPointF(right, bottom - outer_inset), QPointF(left, bottom - inner_inset),
            ])
        if offset < 0:
            return QPolygonF([
                QPointF(left, top + outer_inset), QPointF(right, top + inner_inset),
                QPointF(right, bottom - inner_inset), QPointF(left, bottom - outer_inset),
            ])
        return QPolygonF([
            QPointF(left, top), QPointF(right, top), QPointF(right, bottom), QPointF(left, bottom),
        ])

    def _card_pixmap(self, app: HubApp) -> QPixmap:
        cache_key = (app.id, self._dark, self.current_app == app)
        cached = self._card_cache.get(cache_key)
        if cached is not None:
            return cached
        card = QPixmap(720, 432)
        card.fill(Qt.GlobalColor.transparent)
        painter = QPainter(card)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(3, 3, 714, 426), 24, 24)
        painter.setClipPath(path)
        painter.fillPath(path, QColor("#111d33" if self._dark else "#ffffff"))

        source = self._sources.get(app.id, QPixmap())
        if not source.isNull():
            scaled = source.scaled(
                720, 432, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            crop_x = max(0, (scaled.width() - 720) // 2)
            crop_y = max(0, (scaled.height() - 432) // 2)
            painter.drawPixmap(0, 0, scaled.copy(crop_x, crop_y, 720, 432))

        gradient = QLinearGradient(0, 220, 0, 432)
        gradient.setColorAt(0.0, QColor(4, 10, 25, 0))
        gradient.setColorAt(0.42, QColor(4, 10, 25, 145))
        gradient.setColorAt(1.0, QColor(4, 10, 25, 235))
        painter.fillRect(QRectF(0, 210, 720, 222), gradient)

        painter.setPen(QColor("#ffffff"))
        title_font = QFont("Segoe UI", 22)
        title_font.setWeight(QFont.Weight.Bold)
        painter.setFont(title_font)
        title_option = QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        title_option.setWrapMode(QTextOption.WrapMode.WordWrap)
        painter.drawText(QRectF(28, 294, 664, 70), app.title, title_option)
        painter.setPen(QColor("#c9d8f5"))
        painter.setFont(QFont("Segoe UI", 12))
        painter.drawText(
            QRectF(28, 370, 664, 34), app.subtitle,
            QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        )
        painter.setClipping(False)
        painter.setPen(QColor("#4de1e8" if self.current_app == app else "#627493"))
        painter.drawRoundedRect(QRectF(3, 3, 714, 426), 24, 24)
        painter.end()
        self._card_cache[cache_key] = card
        return card

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._hit_polygons = []
        if not self.apps:
            painter.end()
            return
        card_width, card_height, spacing, center_y = self._metrics()
        items: list[tuple[float, int, QPolygonF, QPixmap]] = []
        for index, app in enumerate(self.apps):
            cycle = round((self._position - index) / len(self.apps))
            offset = index + cycle * len(self.apps) - self._position
            if abs(offset) > 3.25:
                continue
            scale = max(0.58, 1.0 - 0.145 * abs(offset))
            width = card_width * scale
            height = card_height * scale
            center_x = self.width() / 2 + offset * spacing
            quad = self._quad_for_offset(center_x, center_y, width, height, offset)
            items.append((abs(offset), index, quad, self._card_pixmap(app)))
        for _, index, quad, card in sorted(items, reverse=True, key=lambda item: item[0]):
            source_quad = QPolygonF([
                QPointF(0, 0), QPointF(card.width(), 0),
                QPointF(card.width(), card.height()), QPointF(0, card.height()),
            ])
            transform = QTransform()
            if QTransform.quadToQuad(source_quad, quad, transform):
                painter.save()
                painter.setTransform(transform, combine=True)
                painter.drawPixmap(0, 0, card)
                painter.restore()
            self._hit_polygons.append((index, quad))
        if self._edge_direction:
            cue_width = min(145.0, self.width() * 0.18)
            cue_rect = QRectF(
                10.0 if self._edge_direction < 0 else self.width() - cue_width - 10.0,
                max(12.0, center_y - 27.0), cue_width, 54.0,
            )
            painter.setPen(QColor("#4de1e8"))
            painter.setBrush(QColor(8, 23, 45, 205 if self._dark else 175))
            painter.drawRoundedRect(cue_rect, 16.0, 16.0)
            painter.setPen(QColor("#ffffff"))
            cue = "◀  Auto browsing" if self._edge_active and self._edge_direction < 0 else (
                "Auto browsing  ▶" if self._edge_active else (
                    "◀  Hold to browse" if self._edge_direction < 0 else "Hold to browse  ▶"
                )
            )
            painter.drawText(cue_rect, Qt.AlignmentFlag.AlignCenter, cue)
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._stop_edge_hover()
            self.setFocus()
            self._animation.stop()
            self._press_point = event.position()
            self._press_position = self._position
            self._dragged = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._press_point is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._stop_edge_hover()
            delta = event.position().x() - self._press_point.x()
            if abs(delta) >= 4:
                self._dragged = True
            spacing = self._metrics()[2]
            self._set_position(self._press_position - delta / max(1.0, spacing))
            event.accept()
            return
        if event.buttons() == Qt.MouseButton.NoButton:
            x = event.position().x()
            self._update_edge_hover(x)
            if self._hover_x is None:
                self._hover_x = x
            else:
                delta = x - self._hover_x
                self._hover_x = x
                if abs(delta) >= 0.5:
                    self._animation.stop()
                    spacing = self._metrics()[2]
                    self._set_position(self._position - delta / max(1.0, spacing * 1.35))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._press_point is not None:
            point = event.position()
            if self._dragged:
                self.set_current_index(self.current_index)
            else:
                selected = next(
                    (index for index, polygon in reversed(self._hit_polygons)
                     if polygon.containsPoint(point, Qt.FillRule.WindingFill)), None,
                )
                if selected is not None:
                    if selected == self.current_index:
                        self.activate_current()
                    else:
                        self.set_current_index(selected)
            self._press_point = None
            self._hover_x = point.x()
            self._update_edge_hover(point.x())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        self._stop_edge_hover()
        horizontal = event.angleDelta().x()
        vertical = event.angleDelta().y()
        if horizontal and abs(horizontal) >= abs(vertical):
            if horizontal > 0:
                self.previous()
            else:
                self.next()
            event.accept()
            return
        # The carousel sits inside the Hub's vertical scroll area. Ignoring a
        # vertical wheel gesture lets Qt pass it to that parent scroll area.
        event.ignore()

    def enterEvent(self, event) -> None:
        self._hover_x = None
        position = getattr(event, "position", None)
        if callable(position):
            self._update_edge_hover(position().x())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_x = None
        self._stop_edge_hover()
        if self._press_point is None and self.apps:
            self.set_current_index(self.current_index)
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Left:
            self._stop_edge_hover()
            self.previous()
            event.accept()
        elif event.key() == Qt.Key.Key_Right:
            self._stop_edge_hover()
            self.next()
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activate_current()
            event.accept()
        else:
            super().keyPressEvent(event)


class RecentAppCard(QFrame):
    def __init__(self, app: HubApp | None, launch: Callable[[HubApp], None],
                 how_to: Callable[[HubApp], None], parent=None):
        super().__init__(parent)
        self.app = app
        self.setObjectName("recentAppCard")
        self.setMinimumWidth(230)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        layout.addWidget(ThumbnailPlaceholder(app.art if app else ""))
        title = QLabel(app.title if app else "No recent app yet", objectName="cardTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        subtitle = QLabel(app.subtitle if app else "Your recently opened apps will appear here.", objectName="mutedText")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addStretch(1)
        button = QPushButton(f"Open {app.title}" if app else "Empty slot", objectName="primaryButton")
        button.setEnabled(app is not None)
        if app is not None:
            button.clicked.connect(lambda: launch(app))
        layout.addWidget(button)
        guide = QPushButton("How to use", objectName="quietButton")
        guide.setEnabled(app is not None)
        if app is not None:
            guide.clicked.connect(lambda: how_to(app))
        layout.addWidget(guide)


class AppDetailCard(QFrame):
    def __init__(self, app: HubApp, launch: Callable[[HubApp], None],
                 how_to: Callable[[HubApp], None], parent=None):
        super().__init__(parent)
        self.app = app
        self.filter_match = True
        self.setObjectName("appDetailCard")
        self.setMinimumWidth(0)
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(9)
        layout.addWidget(ThumbnailPlaceholder(app.art))
        title = QLabel(app.title, objectName="cardTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        subtitle = QLabel(app.subtitle, objectName="categoryChip")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        description = QLabel(app.description, objectName="cardDescription")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        description.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(description)
        layout.addStretch(1)
        actions = QHBoxLayout()
        self.guide_button = QPushButton("How to use", objectName="quietButton")
        self.guide_button.setToolTip(f"Read the purpose and instructions for {app.title}")
        self.guide_button.clicked.connect(lambda: how_to(app))
        actions.addWidget(self.guide_button)
        self.open_button = QPushButton(f"{app.title}  →", objectName="primaryButton")
        self.open_button.setToolTip(f"Open {app.title}")
        self.open_button.clicked.connect(lambda: launch(app))
        actions.addWidget(self.open_button, 1)
        layout.addLayout(actions)

    def matches(self, query: str) -> bool:
        return hub_app_search_rank(self.app, query) is not None


class AppDetailGrid(QWidget):
    """Responsive card grid that remains populated while its stacked page is hidden."""

    def __init__(self, apps: tuple[HubApp, ...], launch: Callable[[HubApp], None],
                 how_to: Callable[[HubApp], None], parent=None):
        super().__init__(parent)
        self.cards = [AppDetailCard(app, launch, how_to) for app in apps]
        self._display_cards = list(self.cards)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 8, 0, 8)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        self._columns = 0
        self._reflow(3)

    def filter(self, query: str) -> int:
        query = query.casefold().strip()
        ranked_cards: list[tuple[tuple[int, str], AppDetailCard]] = []
        for card in self.cards:
            rank = hub_app_search_rank(card.app, query)
            card.filter_match = rank is not None
            card.setVisible(card.filter_match)
            if rank is not None:
                ranked_cards.append((rank, card))
        self._display_cards = (
            [card for _, card in sorted(ranked_cards, key=lambda item: item[0])]
            if query else list(self.cards)
        )
        self._reflow()
        return len(self._display_cards)

    def resizeEvent(self, event):
        self._reflow()
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._reflow()

    def _reflow(self, columns: int | None = None) -> None:
        if columns is None:
            columns = max(1, min(3, max(1, self.width()) // 370))
        matches = [card for card in self._display_cards if card.filter_match]
        for card in self.cards:
            self.grid.removeWidget(card)
        for index, card in enumerate(matches):
            self.grid.addWidget(card, index // columns, index % columns)
        for column in range(3):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        self._columns = columns
        self.updateGeometry()


class CategorySection(QFrame):
    def __init__(self, title: str, description: str, apps: tuple[HubApp, ...],
                 launch: Callable[[HubApp], None], how_to: Callable[[HubApp], None], *, expanded: bool,
                 collapsible: bool = True, framed: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("categorySection" if framed else "focusedCategorySection")
        self.title = title
        self.description = description
        self.collapsible = collapsible
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = QPushButton(objectName="categoryHeader")
        self.header.setCheckable(collapsible)
        self.header.clicked.connect(self._toggle)
        outer.addWidget(self.header)
        self.content = QWidget(objectName="categoryContent")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(20, 16, 20, 20)
        content_layout.setSpacing(10)
        self.description_label = QLabel(description, objectName="categoryDescription")
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.description_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        content_layout.addWidget(self.description_label)
        self.grid = AppDetailGrid(apps, launch, how_to)
        content_layout.addWidget(self.grid)
        outer.addWidget(self.content)
        self.set_expanded(expanded)

    def _toggle(self) -> None:
        if self.collapsible:
            self.set_expanded(self.header.isChecked())

    def set_expanded(self, expanded: bool) -> None:
        self.header.setChecked(expanded if self.collapsible else False)
        self.content.setVisible(expanded)
        arrow = "v" if expanded else ">"
        self.header.setText(f"{arrow}  {self.title}")
        self.header.setAccessibleName(f"{self.title}, {'expanded' if expanded else 'collapsed'}")

    def filter(self, query: str, *, auto_expand: bool = False) -> int:
        count = self.grid.filter(query)
        self.setVisible(bool(count))
        if auto_expand and query and count:
            self.set_expanded(True)
        return count


class HubBackgroundViewport(QWidget):
    """Faded, crop-aware background that moves more slowly than Hub content."""

    def __init__(self, values: DesktopPreferences, parent=None):
        super().__init__(parent)
        self.values = values
        self.dark = False
        self.scroll_value = 0
        self.scroll_maximum = 0
        self.source = QPixmap()
        self._blurred_key: tuple[str, int] | None = None
        self._blurred = QPixmap()
        self.setAutoFillBackground(False)
        self.apply_preferences(values, False)

    def apply_preferences(self, values: DesktopPreferences, dark: bool) -> None:
        self.values = values
        self.dark = dark
        custom = Path(values.hub_custom_background)
        path = custom if values.hub_background_mode == "Custom" and custom.is_file() else (
            HUB_BACKGROUND_DIR / ("dark.png" if dark else "light.png")
        )
        self.source = QPixmap(str(path))
        self._blurred_key = None
        self._blurred = QPixmap()
        self.update()

    def set_scroll_state(self, value: int, maximum: int) -> None:
        self.scroll_value = value
        self.scroll_maximum = maximum
        self.update()

    def _display_source(self) -> QPixmap:
        if self.source.isNull() or not self.values.hub_background_blur or self.values.hub_background_blur_strength <= 0:
            return self.source
        path_key = str(self.values.hub_custom_background) if self.values.hub_background_mode == "Custom" else ("dark" if self.dark else "light")
        key = (path_key, self.values.hub_background_blur_strength)
        if self._blurred_key == key and not self._blurred.isNull():
            return self._blurred
        factor = max(2, 1 + self.values.hub_background_blur_strength // 2)
        small = self.source.scaled(
            max(1, self.source.width() // factor), max(1, self.source.height() // factor),
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self._blurred = small.scaled(
            self.source.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._blurred_key = key
        return self._blurred

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#091426" if self.dark else "#f5f7fb"))
        source = self._display_source()
        if source.isNull() or self.values.hub_background_opacity <= 0:
            painter.end()
            return
        parallax = self.values.hub_parallax_strength
        overscan = 1.12 + 0.36 * parallax
        target_width = max(1, round(self.width() * overscan))
        target_height = max(1, round(self.height() * overscan))
        scaled = source.scaled(
            target_width, target_height, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        max_x = max(0, scaled.width() - self.width())
        max_y = max(0, scaled.height() - self.height())
        ratio = self.scroll_value / self.scroll_maximum if self.scroll_maximum else 0.0
        crop_x = max_x * self.values.hub_background_crop_x
        crop_y = max_y * self.values.hub_background_crop_y
        crop_y += (ratio - 0.5) * parallax * max_y
        crop_y = max(0.0, min(float(max_y), crop_y))
        painter.setOpacity(self.values.hub_background_opacity)
        painter.drawPixmap(
            QRectF(self.rect()), scaled,
            QRectF(crop_x, crop_y, self.width(), self.height()),
        )
        painter.end()


class HubBackgroundBody(HubBackgroundViewport):
    """Paint the parallax layer inside the scrolling page, behind its controls."""

    def __init__(self, values: DesktopPreferences, parent=None):
        super().__init__(values, parent)
        self.viewport_height = 1

    def set_viewport_height(self, height: int) -> None:
        self.viewport_height = max(1, height)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(event.rect(), QColor("#091426" if self.dark else "#f5f7fb"))
        source = self._display_source()
        if source.isNull() or self.values.hub_background_opacity <= 0:
            painter.end()
            return

        height = min(self.viewport_height, self.height())
        target = QRectF(0, self.scroll_value, self.width(), height)
        parallax = self.values.hub_parallax_strength
        overscan = 1.12 + 0.36 * parallax
        scaled = source.scaled(
            max(1, round(target.width() * overscan)),
            max(1, round(target.height() * overscan)),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        max_x = max(0, scaled.width() - round(target.width()))
        max_y = max(0, scaled.height() - round(target.height()))
        ratio = self.scroll_value / self.scroll_maximum if self.scroll_maximum else 0.0
        crop_x = max_x * self.values.hub_background_crop_x
        crop_y = max_y * self.values.hub_background_crop_y
        crop_y += (ratio - 0.5) * parallax * max_y
        crop_y = max(0.0, min(float(max_y), crop_y))
        painter.setOpacity(self.values.hub_background_opacity)
        painter.drawPixmap(
            target,
            scaled,
            QRectF(crop_x, crop_y, target.width(), target.height()),
        )
        painter.end()


class HubParallaxScrollArea(QScrollArea):
    def __init__(self, values: DesktopPreferences, parent=None):
        super().__init__(parent)
        self.values = values
        self.dark = False
        self.background_body: HubBackgroundBody | None = None
        self.verticalScrollBar().valueChanged.connect(self._sync_background)
        self.verticalScrollBar().rangeChanged.connect(lambda *_: self._sync_background())

    def set_background_body(self, body: HubBackgroundBody) -> None:
        self.background_body = body
        body.apply_preferences(self.values, self.dark)
        self._sync_background()

    def apply_preferences(self, values: DesktopPreferences, dark: bool) -> None:
        self.values = values
        self.dark = dark
        if self.background_body is not None:
            self.background_body.apply_preferences(values, dark)
        self._sync_background()

    def _sync_background(self, *_args) -> None:
        bar = self.verticalScrollBar()
        if self.background_body is not None:
            self.background_body.set_scroll_state(bar.value(), bar.maximum())
            self.background_body.set_viewport_height(self.viewport().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_background()


class MainHubDialog(QDialog):
    """Project entry point with recent apps and a categorized app catalogue."""

    NAV_ITEMS = ("Home", "Movement Analysis", "Games", "Training", "Rehabilitation", "Cognitive Games")

    def __init__(self, parent=None, *, open_pipeline: Callable[[], None] | None = None,
                 open_pipeline_mode: Callable[[int], None] | None = None,
                 resume_mode: Callable[[int], None] | None = None,
                 state_dir: Path | None = None,
                 preferences: PreferenceStore | None = None):
        super().__init__(parent)
        self._open_pipeline_callback = open_pipeline
        self._open_pipeline_mode_callback = open_pipeline_mode
        self._resume_mode_callback = resume_mode
        self.state_dir = state_dir or user_data_dir()
        self.preferences = preferences or PreferenceStore(self.state_dir / "settings.json")
        self.apps = hub_apps()
        self.app_by_id = {app.id: app for app in self.apps}
        self.recent_path = self.state_dir / "recent_hub_apps.json"
        self.category_descriptions: dict[str, QLabel] = {}
        self.category_grids: dict[str, AppDetailGrid] = {}
        self.home_sections: dict[str, CategorySection] = {}
        self.filterables: list[CategorySection] = []
        self.parallax_scrolls: list[HubParallaxScrollArea] = []
        self.setWindowTitle("AIHuMo Main Hub")
        self.resize(1380, 850)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._navigation())
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        self.pages.addWidget(self._home_page())
        for section in self.NAV_ITEMS[1:]:
            self.pages.addWidget(self._category_page(section))
        self._apply_preferences()

    def _navigation(self) -> QWidget:
        bar = QFrame(objectName="navBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 11, 20, 11)
        layout.setSpacing(6)
        layout.addWidget(QLabel("AIHuMo", objectName="hubBrand"))
        layout.addSpacing(12)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for index, text in enumerate(self.NAV_ITEMS):
            button = QPushButton(text, objectName="navButton")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, page=index: self._select_page(page))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)
        layout.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search apps…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(220)
        self.search.textChanged.connect(self._filter_apps)
        layout.addWidget(self.search)
        self.theme_button = QPushButton(objectName="themeToggle")
        self.theme_button.setCheckable(True)
        self.theme_button.setToolTip("Switch between light and dark mode")
        self.theme_button.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_button)
        self.artwork_button = QPushButton(objectName="artworkToggle")
        self.artwork_button.setCheckable(True)
        self.artwork_button.setToolTip("Switch between Focus Mode and Professional Hub artwork")
        self.artwork_button.clicked.connect(self._toggle_artwork_style)
        layout.addWidget(self.artwork_button)
        settings = QPushButton("Settings", objectName="quietButton")
        settings.clicked.connect(self._open_settings)
        layout.addWidget(settings)
        close = QPushButton("Exit", objectName="quietButton")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        return bar

    def _scroll_page(self) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
        scroll = HubParallaxScrollArea(self.preferences.values)
        self.parallax_scrolls.append(scroll)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = HubBackgroundBody(self.preferences.values)
        body.setObjectName("hubBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(18)
        scroll.setWidget(body)
        scroll.set_background_body(body)
        return scroll, body, layout

    def _home_page(self) -> QWidget:
        self.home_scroll, _, layout = self._scroll_page()
        hero = QLabel("Your movement workspace", objectName="heroTitle")
        hero.setWordWrap(True)
        layout.addWidget(hero)
        intro = QLabel("Continue a recent app or browse the complete AIHuMo collection by category.", objectName="heroSubtitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(QLabel("Recent Apps", objectName="sectionTitle"))
        self.recent_cards_host = QWidget()
        self.recent_cards_layout = QGridLayout(self.recent_cards_host)
        self.recent_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_cards_layout.setHorizontalSpacing(16)
        layout.addWidget(self.recent_cards_host)
        self._refresh_recent_cards()
        layout.addSpacing(14)
        layout.addWidget(QLabel("All Apps", objectName="sectionTitle"))
        all_apps_intro = QLabel(
            "Select a category to expand it. The same categories are available in the navigation bar for a focused view.",
            objectName="mutedText",
        )
        all_apps_intro.setWordWrap(True)
        layout.addWidget(all_apps_intro)
        self.all_apps_carousel = PerspectiveAppCarousel(self.apps, self._launch_app)
        self.all_apps_carousel.currentIndexChanged.connect(self._carousel_index_changed)
        layout.addWidget(self.all_apps_carousel)
        carousel_controls = QHBoxLayout()
        self.carousel_previous = QPushButton("← Previous", objectName="quietButton")
        self.carousel_previous.clicked.connect(self.all_apps_carousel.previous)
        self.carousel_status = QLabel(objectName="carouselStatus")
        self.carousel_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.carousel_open = QPushButton("Open selected app", objectName="primaryButton")
        self.carousel_open.clicked.connect(self.all_apps_carousel.activate_current)
        self.carousel_guide = QPushButton("How to use selected", objectName="quietButton")
        self.carousel_guide.clicked.connect(self._show_current_carousel_guide)
        self.carousel_next = QPushButton("Next →", objectName="quietButton")
        self.carousel_next.clicked.connect(self.all_apps_carousel.next)
        carousel_controls.addWidget(self.carousel_previous)
        carousel_controls.addStretch(1)
        carousel_controls.addWidget(self.carousel_status)
        carousel_controls.addWidget(self.carousel_guide)
        carousel_controls.addWidget(self.carousel_open)
        carousel_controls.addStretch(1)
        carousel_controls.addWidget(self.carousel_next)
        layout.addLayout(carousel_controls)
        self._carousel_index_changed(self.all_apps_carousel.current_index)
        layout.addWidget(QLabel("Browse by category", objectName="sectionTitle"))
        for section in self.NAV_ITEMS[1:]:
            apps = tuple(app for app in self.apps if app.section == section)
            category = CategorySection(section, CATEGORY_DESCRIPTIONS[section], apps, self._launch_app,
                                       self._show_guide,
                                       expanded=False, collapsible=True)
            self.home_sections[section] = category
            self.filterables.append(category)
            layout.addWidget(category)
        layout.addSpacing(24)
        layout.addWidget(self._footer())

        home_cards = {card.app.id: card for section in self.home_sections.values() for card in section.grid.cards}
        self.aihumo_button = home_cards["pipeline"].open_button
        self.justice_dance_button = home_cards["just_dance"].open_button
        self.game_buttons = {
            card.app.game_id: card.open_button for card in home_cards.values() if card.app.game_id is not None
        }
        return self.home_scroll

    def _category_page(self, section: str) -> QWidget:
        scroll, _, layout = self._scroll_page()
        heading = QLabel(section, objectName="heroTitle")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        apps = tuple(app for app in self.apps if app.section == section)
        category = CategorySection(section, CATEGORY_DESCRIPTIONS[section], apps, self._launch_app,
                                   self._show_guide,
                                   expanded=True, collapsible=False, framed=False)
        self.category_descriptions[section] = category.description_label
        self.category_grids[section] = category.grid
        self.filterables.append(category)
        layout.addWidget(category)
        layout.addWidget(self._getting_started(section))
        layout.addStretch(1)
        layout.addWidget(self._footer())
        return scroll

    @staticmethod
    def _footer() -> QFrame:
        footer = QFrame(objectName="hubFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 18, 12, 18)
        label = QLabel("Sir Jax Big Boi J", objectName="footerText")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_layout.addWidget(label)
        return footer

    def _recent_app_ids(self) -> list[str]:
        try:
            document = load_json(self.recent_path)
        except (OSError, ValueError, TypeError):
            return []
        items = document.get("items", []) if isinstance(document, dict) else []
        result: list[str] = []
        for item in items:
            app_id = item.get("appId") if isinstance(item, dict) else None
            if app_id in self.app_by_id and app_id not in result:
                result.append(app_id)
        return result[:3]

    def _remember_app(self, app: HubApp) -> None:
        ids = [app.id, *(item for item in self._recent_app_ids() if item != app.id)][:3]
        document = {
            "version": 1,
            "items": [{"appId": app_id, "openedAt": datetime.now(timezone.utc).isoformat()} for app_id in ids],
        }
        save_json_atomic(document, self.recent_path)
        self._refresh_recent_cards()

    def _refresh_recent_cards(self) -> None:
        while self.recent_cards_layout.count():
            item = self.recent_cards_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        recent = [self.app_by_id[app_id] for app_id in self._recent_app_ids()]
        slots: list[HubApp | None] = [*recent, *([None] * (3 - len(recent)))]
        self.recent_cards: list[RecentAppCard] = []
        for index, app in enumerate(slots[:3]):
            card = RecentAppCard(app, self._launch_app, self._show_guide)
            self.recent_cards.append(card)
            self.recent_cards_layout.addWidget(card, 0, index)
            self.recent_cards_layout.setColumnStretch(index, 1)

    def _launch_app(self, app: HubApp) -> None:
        self._remember_app(app)
        if app.cognitive_game_id:
            self._exec_subapp_dialog(CognitiveGameDialog(
                app.cognitive_game_id, self, preferences=self.preferences
            ))
            return
        if app.game_id:
            self._exec_subapp_dialog(MovementGameDialog(
                app.game_id, self, preferences=self.preferences
            ))
            return
        if app.mode is not None and self._open_pipeline_mode_callback is not None:
            self._open_pipeline_mode_callback(app.mode)
            return
        self.open_pipeline()

    def _show_guide(self, app: HubApp) -> None:
        guide = guide_for(app.id)
        if guide is None:
            return
        dialog = HowToDialog(app.title, guide, lambda: self._launch_app(app), self)
        dialog.setStyleSheet(self.styleSheet())
        dialog.exec()

    def _show_current_carousel_guide(self) -> None:
        app = self.all_apps_carousel.current_app
        if app is not None:
            self._show_guide(app)

    @staticmethod
    def _getting_started(section: str) -> QFrame:
        content = {
            "Movement Analysis": (
                ("1 · Prepare", "Choose the recording and matching AIHuMo workspace files."),
                ("2 · Work", "Open the processing, annotation, alignment, or graph workflow."),
                ("3 · Review", "Check warnings, verify session identity, and save or export."),
            ),
            "Cognitive Games": (
                ("1 · Choose", "Select the skill, difficulty, and number of rounds."),
                ("2 · Play", "Complete each prompt at a comfortable, focused pace."),
                ("3 · Review", "Use accuracy and timing to choose the next difficulty."),
            ),
        }.get(section, (
            ("1 · Prepare", "Clear the play area, position the camera, and choose a safe level."),
            ("2 · Calibrate", "Complete the movement-range check before beginning the round."),
            ("3 · Review", "Inspect accuracy, timing, control, and consistency after play."),
        ))
        panel = QFrame(objectName="gettingStartedPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Getting started", objectName="sectionTitle"))
        row = QHBoxLayout()
        row.setSpacing(12)
        for title, description in content:
            item = QFrame(objectName="gettingStartedStep")
            item_layout = QVBoxLayout(item)
            title_label = QLabel(title, objectName="guideSectionTitle")
            body = QLabel(description, objectName="mutedText")
            body.setWordWrap(True)
            item_layout.addWidget(title_label)
            item_layout.addWidget(body)
            item_layout.addStretch(1)
            row.addWidget(item, 1)
        layout.addLayout(row)
        return panel

    def _resume_mode(self, mode: int) -> None:
        if self._resume_mode_callback is not None:
            self._resume_mode_callback(mode)
        elif self._open_pipeline_mode_callback is not None:
            self._open_pipeline_mode_callback(mode)
        else:
            self.open_pipeline()

    def open_pipeline(self) -> None:
        if self._open_pipeline_callback is None:
            self.accept()
        else:
            self._open_pipeline_callback()

    def open_game(self, game_id: str) -> None:
        app = self.app_by_id.get(game_id)
        if app is not None:
            self._remember_app(app)
        self._exec_subapp_dialog(MovementGameDialog(
            game_id, self, preferences=self.preferences
        ))

    @staticmethod
    def _exec_subapp_dialog(dialog: QDialog) -> int:
        """Open games maximized while retaining the native title-bar controls."""
        dialog.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        dialog.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        dialog.showMaximized()
        return dialog.exec()

    def _select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.search.clear()

    def _filter_apps(self, text: str) -> None:
        query = text.casefold().strip()
        matching_apps = ranked_hub_apps(self.apps, query)
        self.all_apps_carousel.set_apps(matching_apps)
        for section in self.filterables:
            section.filter(query, auto_expand=section in self.home_sections.values())

    def _carousel_index_changed(self, index: int) -> None:
        app = self.all_apps_carousel.current_app
        if app is None:
            self.carousel_status.setText("No matching apps")
            self.carousel_open.setEnabled(False)
            self.carousel_guide.setEnabled(False)
            return
        self.carousel_status.setText(f"{index + 1} / {len(self.all_apps_carousel.apps)}  ·  {app.title}")
        self.carousel_open.setEnabled(True)
        self.carousel_guide.setEnabled(True)

    def _toggle_theme(self, *_args) -> None:
        theme = "Light" if self.preferences.values.theme == "Dark" else "Dark"
        self.preferences.save(replace(self.preferences.values, theme=theme))
        self._apply_preferences()

    def _toggle_artwork_style(self, *_args) -> None:
        style = "Focus Mode" if self.preferences.values.hub_artwork_style == "Professional" else "Professional"
        self.preferences.save(replace(self.preferences.values, hub_artwork_style=style))
        self._apply_preferences()

    def _open_settings(self) -> None:
        if PreferencesDialog(self.preferences, self).exec() == QDialog.DialogCode.Accepted:
            self._apply_preferences()

    def _apply_preferences(self) -> None:
        theme = "Dark" if self.preferences.values.theme == "Dark" else "Light"
        self.theme_button.blockSignals(True)
        self.theme_button.setChecked(theme == "Dark")
        self.theme_button.setText("☾  Dark" if theme == "Dark" else "☀  Light")
        self.theme_button.blockSignals(False)
        artwork_style = self.preferences.values.hub_artwork_style
        self.artwork_button.blockSignals(True)
        self.artwork_button.setChecked(artwork_style == "Professional")
        self.artwork_button.setText("Professional" if artwork_style == "Professional" else "Focus Mode")
        self.artwork_button.blockSignals(False)
        self.setStyleSheet(self._stylesheet(theme == "Dark"))
        for scroll in self.parallax_scrolls:
            scroll.apply_preferences(self.preferences.values, theme == "Dark")
        if hasattr(self, "all_apps_carousel"):
            self.all_apps_carousel.set_dark(theme == "Dark")
            self.all_apps_carousel.set_artwork_style(artwork_style)
        for thumbnail in self.findChildren(ThumbnailPlaceholder):
            thumbnail.set_artwork_style(artwork_style)

    @staticmethod
    def _stylesheet(dark: bool) -> str:
        if dark:
            colors = {
                "window": "#091426", "panel": "#101d33", "card": "#16263f", "text": "#f5f7ff",
                "muted": "#b7c2d8", "border": "#354967", "accent": "#36c9d8", "accent2": "#7867ef",
                "placeholder": "#0c192c", "scroll": "#7894bd", "scroll_hover": "#36c9d8",
            }
        else:
            colors = {
                "window": "#f5f7fb", "panel": "#ffffff", "card": "#ffffff", "text": "#15213d",
                "muted": "#63708a", "border": "#dce2ed", "accent": "#22bdd1", "accent2": "#7563e7",
                "placeholder": "#eef2f7", "scroll": "#a8b6ca", "scroll_hover": "#22bdd1",
            }
        return f"""
            QDialog {{ background: {colors['window']}; color: {colors['text']}; font-family: "Segoe UI"; }}
            QWidget#hubBody {{ background: transparent; color: {colors['text']}; font-family: "Segoe UI"; }}
            QWidget, QLabel, QPushButton, QCheckBox, QRadioButton, QGroupBox, QTabWidget {{ color: {colors['text']}; }}
            QPushButton {{ background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 9px; padding: 7px 10px; }}
            QPushButton:hover {{ border-color: {colors['accent']}; }}
            QPushButton:disabled {{ color: {colors['muted']}; background: {colors['placeholder']}; }}
            QTabBar::tab {{ color: {colors['muted']}; background: {colors['panel']}; border: 1px solid {colors['border']}; padding: 8px 13px; }}
            QTabBar::tab:selected {{ color: {colors['text']}; background: {colors['card']}; border-bottom: 2px solid {colors['accent']}; }}
            QTabBar::tab:hover {{ color: {colors['text']}; border-color: {colors['accent']}; }}
            QFrame#navBar {{ background: {colors['panel']}; border-bottom: 1px solid {colors['border']}; }}
            QLabel {{ color: {colors['text']}; }}
            QLabel#hubBrand {{ font-size: 21px; font-weight: 800; padding-right: 5px; }}
            QLabel#heroTitle {{ font-size: 31px; font-weight: 800; padding-top: 8px; }}
            QLabel#heroSubtitle, QLabel#mutedText, QLabel#cardDescription, QLabel#categoryDescription {{ color: {colors['muted']}; font-size: 14px; }}
            QLabel#sectionTitle {{ font-size: 21px; font-weight: 750; padding-top: 8px; }}
            QLabel#carouselStatus {{ color: {colors['muted']}; font-size: 14px; font-weight: 700; min-width: 220px; }}
            QLabel#cardTitle {{ font-size: 17px; font-weight: 750; }}
            QLabel#categoryChip {{ color: {colors['accent']}; font-weight: 700; }}
            QLabel#footerText {{ color: {colors['muted']}; font-weight: 650; }}
            QFrame#hubFooter {{ border-top: 1px solid {colors['border']}; }}
            QLabel#thumbnailPlaceholder {{ background: {colors['placeholder']}; border: 2px solid {colors['border']}; border-radius: 12px; }}
            QFrame#recentAppCard, QFrame#appDetailCard {{ background: {colors['card']}; border: 2px solid {colors['border']}; border-radius: 15px; }}
            QFrame#recentAppCard:hover, QFrame#appDetailCard:hover {{ border: 2px solid {colors['accent']}; }}
            QFrame#gettingStartedPanel {{ background: {colors['panel']}; border: 2px solid {colors['border']}; border-radius: 15px; }}
            QFrame#gettingStartedStep {{ background: {colors['card']}; border: 1px solid {colors['border']}; border-radius: 12px; }}
            QLabel#guideTitle {{ font-size: 27px; font-weight: 800; }}
            QLabel#guidePurpose {{ color: {colors['muted']}; font-size: 15px; padding-bottom: 8px; }}
            QLabel#guideSectionTitle {{ font-size: 16px; font-weight: 750; padding-top: 6px; }}
            QLabel#guideText {{ color: {colors['text']}; font-size: 14px; line-height: 1.35; }}
            QLabel#guideSafety {{ color: {colors['text']}; background: {colors['placeholder']}; border: 1px solid {colors['border']}; border-radius: 10px; padding: 12px; }}
            QFrame#guideVideoPlaceholder {{ background: {colors['placeholder']}; border: 2px dashed {colors['border']}; border-radius: 12px; }}
            QFrame#categorySection {{ background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 14px; }}
            QFrame#focusedCategorySection {{ background: transparent; border: none; }}
            QWidget#categoryContent {{ background: transparent; }}
            QPushButton#categoryHeader {{ color: {colors['text']}; background: transparent; border: none; padding: 16px 18px; text-align: left; font-size: 17px; font-weight: 750; }}
            QPushButton#categoryHeader:hover {{ color: {colors['accent']}; }}
            QPushButton#navButton {{ color: {colors['muted']}; background: transparent; border: none; border-radius: 15px; padding: 8px 10px; font-weight: 650; }}
            QPushButton#navButton:hover {{ color: {colors['text']}; background: {colors['window']}; }}
            QPushButton#navButton:checked {{ color: #07152f; background: {colors['accent']}; }}
            QPushButton#primaryButton {{ color: white; background: {colors['accent2']}; border: none; border-radius: 12px; padding: 9px 13px; font-weight: 700; }}
            QPushButton#primaryButton:hover {{ background: {colors['accent']}; color: #07152f; }}
            QPushButton#primaryButton:disabled {{ background: {colors['border']}; color: {colors['muted']}; }}
            QPushButton#quietButton {{ color: {colors['text']}; background: transparent; border: 1px solid {colors['border']}; border-radius: 11px; padding: 7px 10px; }}
            QPushButton#themeToggle {{ color: {colors['text']}; background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 11px; min-width: 84px; padding: 7px 11px; font-weight: 700; }}
            QPushButton#themeToggle:hover, QPushButton#themeToggle:checked {{ border-color: {colors['accent']}; background: {colors['card']}; }}
            QPushButton#artworkToggle {{ color: {colors['text']}; background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 11px; min-width: 106px; padding: 7px 11px; font-weight: 700; }}
            QPushButton#artworkToggle:hover, QPushButton#artworkToggle:checked {{ border-color: {colors['accent2']}; background: {colors['card']}; }}
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QTableView, QTreeView {{ color: {colors['text']}; background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 12px; padding: 7px 10px; selection-background-color: {colors['accent2']}; selection-color: white; }}
            QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {colors['muted']}; background: {colors['placeholder']}; }}
            QComboBox QAbstractItemView, QMenu {{ color: {colors['text']}; background: {colors['panel']}; border: 1px solid {colors['border']}; selection-background-color: {colors['accent2']}; selection-color: white; outline: none; }}
            QComboBox QAbstractItemView::item {{ color: {colors['text']}; min-height: 28px; padding: 4px 8px; }}
            QComboBox QAbstractItemView::item:selected {{ color: white; background: {colors['accent2']}; }}
            QToolTip {{ color: {colors['text']}; background: {colors['card']}; border: 1px solid {colors['accent']}; padding: 5px; }}
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px; }}
            QScrollBar::handle:vertical {{ background: {colors['scroll']}; min-height: 40px; border-radius: 5px; }}
            QScrollBar::handle:vertical:hover {{ background: {colors['scroll_hover']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 3px; }}
            QScrollBar::handle:horizontal {{ background: {colors['scroll']}; min-width: 40px; border-radius: 5px; }}
            QScrollBar::handle:horizontal:hover {{ background: {colors['scroll_hover']}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        """
