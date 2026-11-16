"""Primary AIHuMo desktop hub and app catalogue."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, pyqtSignal
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
from .movement_games import MovementGameDialog, load_game_definitions
from .preferences import PreferenceStore, PreferencesDialog

HUB_CARD_DIR = Path(__file__).resolve().parents[1] / "assets" / "hub_cards_v2"


@dataclass(frozen=True)
class HubApp:
    id: str
    title: str
    subtitle: str
    description: str
    section: str
    art: str = ""
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
    ),
    HubApp(
        "annotation", "Annotation Studio", "Mode 1 · Layered annotation",
        "Label activities, sets, repetitions, phases, form observations, notes, and synchronized frame context.",
        "Movement Analysis", art="annotation.jpg", mode=1,
    ),
    HubApp(
        "alignment", "Session Alignment", "Mode 2 · Multi-camera alignment",
        "Align related recordings and annotations across cameras, trimmed clips, and session timelines.",
        "Movement Analysis", art="alignment.jpg", mode=2,
    ),
    HubApp(
        "graph_2d", "Interactive Graph Viewer (2D)", "Mode 3 · Image-plane measurements",
        "Review synchronized skeleton video, 2D joint angles, landmark motion, distances, and annotation overlays.",
        "Movement Analysis", art="graph_2d.jpg", mode=3,
    ),
    HubApp(
        "graph_3d", "Interactive Graph Viewer (3D)", "Mode 4 · Estimated world measurements",
        "Inspect the rotatable pose and synchronized estimated-world timelines alongside the source video.",
        "Movement Analysis", art="graph_3d.jpg", mode=4,
    ),
)


COGNITIVE_APPS = (
    HubApp(
        "spelling_bee", "Spelling Bee", "Words · Definitions · Recall",
        "Practice spelling from the AIHuMo dictionary with definitions, difficulty controls, rounds, and score feedback.",
        "Cognitive Games", art="spelling_bee.jpg", cognitive_game_id="spelling_bee",
    ),
    HubApp(
        "math_challenge", "Math Challenge", "Arithmetic · Accuracy · Recall",
        "Solve addition, subtraction, multiplication, and division prompts with adjustable rounds and scoring.",
        "Cognitive Games", art="math_challenge.jpg", cognitive_game_id="math_challenge",
    ),
)


GAME_SECTIONS = {
    "path": "Training",
    "freeze": "Training",
    "balance": "Training",
    "sports": "Training",
    "rehab": "Rehabilitation",
    "ergonomics": "Rehabilitation",
    "gait": "Rehabilitation",
    "sequence": "Cognitive Games",
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
            art=f"{definition.id}.jpg",
            game_id=definition.id,
        ))
    return (*PIPELINE_APPS, *games, *COGNITIVE_APPS)


class ThumbnailPlaceholder(QLabel):
    """Card artwork, or a blank reserved area when no recent app exists."""

    def __init__(self, art: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("thumbnailPlaceholder")
        self.image_path = HUB_CARD_DIR / art if art else None
        self.source = QPixmap(str(self.image_path)) if self.image_path else QPixmap()
        self.setAccessibleName("App artwork" if not self.source.isNull() else "Thumbnail placeholder")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(176, 104)
        self.setMaximumHeight(126)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        self._last_emitted_index = 0
        self._sources = {
            app.id: QPixmap(str(HUB_CARD_DIR / app.art)) if app.art else QPixmap()
            for app in self.apps
        }
        self._card_cache: dict[tuple[str, bool, bool], QPixmap] = {}
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(420)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._animation_value_changed)
        self.setMinimumHeight(330)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("All Apps perspective carousel")
        self.setToolTip(
            "Drag, use the mouse wheel, or press Left and Right. "
            "Select the centered card again to open it."
        )

    @property
    def current_index(self) -> int:
        if not self.apps:
            return -1
        return int(max(0, min(len(self.apps) - 1, round(self._position))))

    @property
    def current_app(self) -> HubApp | None:
        return self.apps[self.current_index] if self.current_index >= 0 else None

    def set_dark(self, dark: bool) -> None:
        self._dark = bool(dark)
        self.update()

    def set_apps(self, apps: tuple[HubApp, ...]) -> None:
        current_id = self.current_app.id if self.current_app else None
        self.apps = tuple(apps)
        for app in self.apps:
            self._sources.setdefault(
                app.id, QPixmap(str(HUB_CARD_DIR / app.art)) if app.art else QPixmap()
            )
        index = next((i for i, app in enumerate(self.apps) if app.id == current_id), 0)
        self._last_emitted_index = -2
        self.set_current_index(index, animated=False)

    def set_current_index(self, index: int, *, animated: bool = True) -> None:
        if not self.apps:
            self._position = 0.0
            self._last_emitted_index = -1
            self.currentIndexChanged.emit(-1)
            self.update()
            return
        target = int(max(0, min(len(self.apps) - 1, index)))
        self._animation.stop()
        if not animated:
            self._set_position(float(target))
            return
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(float(target))
        self._animation.start()

    def previous(self) -> None:
        self.set_current_index(self.current_index - 1)

    def next(self) -> None:
        self.set_current_index(self.current_index + 1)

    def activate_current(self) -> None:
        if self.current_app is not None:
            self.launch(self.current_app)

    def _animation_value_changed(self, value) -> None:
        self._set_position(float(value))

    def _set_position(self, value: float) -> None:
        maximum = max(0, len(self.apps) - 1)
        self._position = max(0.0, min(float(maximum), value))
        index = self.current_index
        if index != self._last_emitted_index:
            self._last_emitted_index = index
            self.currentIndexChanged.emit(index)
        self.update()

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
            offset = index - self._position
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
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
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
            delta = event.position().x() - self._press_point.x()
            if abs(delta) >= 4:
                self._dragged = True
            spacing = self._metrics()[2]
            self._set_position(self._press_position - delta / max(1.0, spacing))
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
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y() or event.angleDelta().x()
        self.set_current_index(self.current_index + (1 if delta < 0 else -1))
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Left:
            self.previous()
            event.accept()
        elif event.key() == Qt.Key.Key_Right:
            self.next()
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activate_current()
            event.accept()
        else:
            super().keyPressEvent(event)


class RecentAppCard(QFrame):
    def __init__(self, app: HubApp | None, launch: Callable[[HubApp], None], parent=None):
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


class AppDetailCard(QFrame):
    def __init__(self, app: HubApp, launch: Callable[[HubApp], None], parent=None):
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
        self.open_button = QPushButton(f"{app.title}  →", objectName="primaryButton")
        self.open_button.setToolTip(f"Open {app.title}")
        self.open_button.clicked.connect(lambda: launch(app))
        layout.addWidget(self.open_button)

    def matches(self, query: str) -> bool:
        text = f"{self.app.title} {self.app.subtitle} {self.app.description} {self.app.section}".casefold()
        return not query or query in text


class AppDetailGrid(QWidget):
    """Responsive card grid that remains populated while its stacked page is hidden."""

    def __init__(self, apps: tuple[HubApp, ...], launch: Callable[[HubApp], None], parent=None):
        super().__init__(parent)
        self.cards = [AppDetailCard(app, launch) for app in apps]
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 8, 0, 8)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        self._columns = 0
        self._reflow(3)

    def filter(self, query: str) -> int:
        query = query.casefold().strip()
        count = 0
        for card in self.cards:
            card.filter_match = card.matches(query)
            card.setVisible(card.filter_match)
            count += int(card.filter_match)
        self._reflow()
        return count

    def resizeEvent(self, event):
        self._reflow()
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._reflow()

    def _reflow(self, columns: int | None = None) -> None:
        if columns is None:
            columns = max(1, min(3, max(1, self.width()) // 370))
        matches = [card for card in self.cards if card.filter_match]
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
                 launch: Callable[[HubApp], None], *, expanded: bool,
                 collapsible: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("categorySection")
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
        self.grid = AppDetailGrid(apps, launch)
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
        description_match = bool(query and query in f"{self.title} {self.description}".casefold())
        count = self.grid.filter("" if description_match else query)
        self.setVisible(bool(count))
        if auto_expand and query and count:
            self.set_expanded(True)
        return count


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
        self.state_dir = state_dir or Path(__file__).resolve().parents[1] / ".aihumo"
        self.preferences = preferences or PreferenceStore(self.state_dir / "settings.json")
        self.apps = hub_apps()
        self.app_by_id = {app.id: app for app in self.apps}
        self.recent_path = self.state_dir / "recent_hub_apps.json"
        self.category_descriptions: dict[str, QLabel] = {}
        self.category_grids: dict[str, AppDetailGrid] = {}
        self.home_sections: dict[str, CategorySection] = {}
        self.filterables: list[CategorySection] = []
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
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(("Light", "Dark"))
        self.theme_combo.currentTextChanged.connect(self._visual_option_changed)
        layout.addWidget(self.theme_combo)
        settings = QPushButton("Settings", objectName="quietButton")
        settings.clicked.connect(self._open_settings)
        layout.addWidget(settings)
        close = QPushButton("Exit", objectName="quietButton")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        return bar

    def _scroll_page(self) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(objectName="hubBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(18)
        scroll.setWidget(body)
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
        self.carousel_next = QPushButton("Next →", objectName="quietButton")
        self.carousel_next.clicked.connect(self.all_apps_carousel.next)
        carousel_controls.addWidget(self.carousel_previous)
        carousel_controls.addStretch(1)
        carousel_controls.addWidget(self.carousel_status)
        carousel_controls.addWidget(self.carousel_open)
        carousel_controls.addStretch(1)
        carousel_controls.addWidget(self.carousel_next)
        layout.addLayout(carousel_controls)
        self._carousel_index_changed(self.all_apps_carousel.current_index)
        layout.addWidget(QLabel("Browse by category", objectName="sectionTitle"))
        for section in self.NAV_ITEMS[1:]:
            apps = tuple(app for app in self.apps if app.section == section)
            category = CategorySection(section, CATEGORY_DESCRIPTIONS[section], apps, self._launch_app,
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
                                   expanded=True, collapsible=False)
        self.category_descriptions[section] = category.description_label
        self.category_grids[section] = category.grid
        self.filterables.append(category)
        layout.addWidget(category)
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
            card = RecentAppCard(app, self._launch_app)
            self.recent_cards.append(card)
            self.recent_cards_layout.addWidget(card, 0, index)
            self.recent_cards_layout.setColumnStretch(index, 1)

    def _launch_app(self, app: HubApp) -> None:
        self._remember_app(app)
        if app.cognitive_game_id:
            CognitiveGameDialog(app.cognitive_game_id, self).exec()
            return
        if app.game_id:
            MovementGameDialog(app.game_id, self).exec()
            return
        if app.mode is not None and self._open_pipeline_mode_callback is not None:
            self._open_pipeline_mode_callback(app.mode)
            return
        self.open_pipeline()

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
        MovementGameDialog(game_id, self).exec()

    def _select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.search.clear()

    def _filter_apps(self, text: str) -> None:
        query = text.casefold().strip()
        matching_apps = tuple(
            app for app in self.apps
            if not query or query in f"{app.title} {app.subtitle} {app.description} {app.section}".casefold()
        )
        self.all_apps_carousel.set_apps(matching_apps)
        for section in self.filterables:
            section.filter(query, auto_expand=section in self.home_sections.values())

    def _carousel_index_changed(self, index: int) -> None:
        app = self.all_apps_carousel.current_app
        if app is None:
            self.carousel_status.setText("No matching apps")
            self.carousel_open.setEnabled(False)
            return
        self.carousel_status.setText(f"{index + 1} / {len(self.all_apps_carousel.apps)}  ·  {app.title}")
        self.carousel_open.setEnabled(True)

    def _visual_option_changed(self, *_args) -> None:
        if not hasattr(self, "theme_combo"):
            return
        self.preferences.save(replace(self.preferences.values, theme=self.theme_combo.currentText()))
        self._apply_preferences()

    def _open_settings(self) -> None:
        if PreferencesDialog(self.preferences, self).exec() == QDialog.DialogCode.Accepted:
            self._apply_preferences()

    def _apply_preferences(self) -> None:
        theme = "Dark" if self.preferences.values.theme == "Dark" else "Light"
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentText(theme)
        self.theme_combo.blockSignals(False)
        self.setStyleSheet(self._stylesheet(theme == "Dark"))
        if hasattr(self, "all_apps_carousel"):
            self.all_apps_carousel.set_dark(theme == "Dark")

    @staticmethod
    def _stylesheet(dark: bool) -> str:
        if dark:
            colors = {
                "window": "#091426", "panel": "#101d33", "card": "#16263f", "text": "#f5f7ff",
                "muted": "#b7c2d8", "border": "#354967", "accent": "#36c9d8", "accent2": "#7867ef",
                "placeholder": "#0c192c",
            }
        else:
            colors = {
                "window": "#f5f7fb", "panel": "#ffffff", "card": "#ffffff", "text": "#15213d",
                "muted": "#63708a", "border": "#dce2ed", "accent": "#22bdd1", "accent2": "#7563e7",
                "placeholder": "#eef2f7",
            }
        return f"""
            QDialog, QWidget#hubBody {{ background: {colors['window']}; color: {colors['text']}; font-family: "Segoe UI"; }}
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
            QLabel#thumbnailPlaceholder {{ background: {colors['placeholder']}; border: 1px dashed {colors['border']}; border-radius: 12px; }}
            QFrame#recentAppCard, QFrame#appDetailCard {{ background: {colors['card']}; border: 1px solid {colors['border']}; border-radius: 15px; }}
            QFrame#recentAppCard:hover, QFrame#appDetailCard:hover {{ border: 2px solid {colors['accent']}; }}
            QFrame#categorySection {{ background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 14px; }}
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
            QLineEdit, QComboBox {{ color: {colors['text']}; background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 12px; padding: 7px 10px; }}
            QScrollArea {{ border: none; background: {colors['window']}; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px; }}
            QScrollBar::handle:vertical {{ background: {colors['border']}; min-height: 40px; border-radius: 5px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """
