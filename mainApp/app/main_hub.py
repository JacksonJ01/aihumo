"""Primary AIHuMo desktop hub and app catalogue."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
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
        for section in self.filterables:
            section.filter(query, auto_expand=section in self.home_sections.values())

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
