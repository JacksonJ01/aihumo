"""Primary AIHuMo desktop Hub with dashboard and App Galaxy views."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from aihumo.storage import load_json
from .movement_games import MovementGameDialog, load_game_definitions
from .preferences import PreferenceStore, PreferencesDialog


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "hub_cards"


def hub_art_path(filename: str) -> Path:
    return ASSET_DIR / filename


@dataclass(frozen=True)
class HubApp:
    id: str
    title: str
    subtitle: str
    section: str
    accent: str
    art: str = "processing.jpg"
    mode: int | None = None
    game_id: str | None = None
    featured: bool = False


PIPELINE_APPS = (
    HubApp("pipeline", "AIHuMo Pipeline", "Process · Annotate · Analyze", "Movement Analysis", "#2dc7e8", "processing.jpg", featured=True),
    HubApp("annotation", "Annotation Studio", "Layered movement labels", "Movement Analysis", "#8a6df1", "annotation.jpg", mode=1),
    HubApp("alignment", "Session Alignment", "Multi-camera synchronization", "Movement Analysis", "#5a8dee", "partner-sync.jpg", mode=2),
    HubApp("graph_2d", "Graph Viewer 2D", "Angles · Motion · Timelines", "Movement Analysis", "#28c8a2", "graphs-3d.jpg", mode=3, featured=True),
    HubApp("graph_3d", "Graph Viewer 3D", "Pose space · 3D review", "Movement Analysis", "#e58c55", "graphs-3d.jpg", mode=4),
)


GAME_ACCENTS = (
    "#ef6f6c", "#9b72f2", "#21c7d9", "#58c98b", "#e6a14a", "#d95fa5",
    "#4f8fea", "#62c26f", "#ef8354", "#7b6de5", "#35b7a5", "#d977c7",
)

GAME_ART = {
    "just_dance": "dance-rhythm.jpg",
    "rhythm": "dance-rhythm.jpg",
    "mirror": "partner-sync.jpg",
    "partner": "partner-sync.jpg",
    "path": "balance-rehab.jpg",
    "freeze": "balance-rehab.jpg",
    "balance": "balance-rehab.jpg",
    "rehab": "balance-rehab.jpg",
    "ergonomics": "balance-rehab.jpg",
    "gait": "balance-rehab.jpg",
}


def hub_apps() -> tuple[HubApp, ...]:
    games: list[HubApp] = []
    training_ids = {"path", "freeze", "balance", "rehab", "ergonomics", "gait"}
    featured_ids = {"just_dance", "target_grid_6", "reaction", "balance"}
    for index, definition in enumerate(load_game_definitions()):
        section = "Training & Rehab" if definition.id in training_ids else "Games"
        games.append(HubApp(
            definition.id,
            definition.title,
            f"{definition.category} · {definition.objective}",
            section,
            GAME_ACCENTS[index % len(GAME_ACCENTS)],
            art=GAME_ART.get(definition.id, "targets-agility.jpg"),
            game_id=definition.id,
            featured=definition.id in featured_ids,
        ))
    return (*PIPELINE_APPS, *games)


class SkeletonPreview(QWidget):
    """Small inexpensive preview used until a cached video thumbnail exists."""

    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self.accent = QColor(accent)
        self.setFixedSize(150, 78)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#111827"))
        painter.drawRoundedRect(self.rect(), 12, 12)
        pen = QPen(self.accent, 3)
        painter.setPen(pen)
        w, h = self.width(), self.height()
        points = {
            "head": QPoint(w // 2, 15), "neck": QPoint(w // 2, 26),
            "left_hand": QPoint(w // 2 - 30, 38), "right_hand": QPoint(w // 2 + 30, 37),
            "hip": QPoint(w // 2, 49), "left_foot": QPoint(w // 2 - 20, 69),
            "right_foot": QPoint(w // 2 + 22, 69),
        }
        for first, second in (("head", "neck"), ("neck", "left_hand"), ("neck", "right_hand"),
                              ("neck", "hip"), ("hip", "left_foot"), ("hip", "right_foot")):
            painter.drawLine(points[first], points[second])
        painter.setBrush(self.accent)
        for point in points.values():
            painter.drawEllipse(point, 4, 4)


class ArtworkPreview(QLabel):
    """Fast, cropped preview of a Hub artwork asset."""

    def __init__(self, art: str, accent: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 78)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        source = QPixmap(str(hub_art_path(art)))
        if source.isNull():
            self.setText("●")
            self.setStyleSheet(f"background: #111827; color: {accent}; border-radius: 12px; font-size: 34px;")
            return
        scaled = source.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
        x = max(0, (scaled.width() - self.width()) // 2)
        y = max(0, (scaled.height() - self.height()) // 2)
        self.setPixmap(scaled.copy(x, y, self.width(), self.height()))
        self.setStyleSheet("border-radius: 12px;")


class RecentCard(QFrame):
    def __init__(self, record: dict, resume: Callable[[], None], dark: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("recentCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(16)
        layout.addWidget(ArtworkPreview(record["art"], record["accent"]))
        details = QVBoxLayout()
        title = QLabel(record["title"])
        title.setObjectName("recentTitle")
        title.setStyleSheet("font-weight: 700; font-size: 16px;")
        details.addWidget(title)
        file_label = QLabel(record["file"])
        file_label.setObjectName("mutedText")
        file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.addWidget(file_label)
        details.addWidget(QLabel(record["detail"], objectName="mutedText"))
        layout.addLayout(details, 1)
        status = QLabel(record["status"])
        status.setObjectName("statusChip")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setMinimumWidth(130)
        layout.addWidget(status)
        button = QPushButton("Resume  ▶")
        button.setObjectName("primaryButton")
        button.clicked.connect(resume)
        layout.addWidget(button)


class AppCard(QToolButton):
    def __init__(self, app: HubApp, launch: Callable[[HubApp], None], parent=None):
        super().__init__(parent)
        self.app = app
        self.setObjectName("appCard")
        self.setText(f"{app.title}\n{app.section}")
        self.setToolTip(f"{app.subtitle}\nClick to open {app.title}.")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIcon(QIcon(str(hub_art_path(app.art))))
        self.setIconSize(QSize(148, 148))
        self.setMinimumHeight(218)
        # Ignore long subtitle size hints so the responsive grid can contract
        # without creating a horizontal page scrollbar.
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.clicked.connect(lambda: launch(app))

    def resizeEvent(self, event):
        side = max(112, min(154, self.width() - 34))
        self.setIconSize(QSize(side, side))
        super().resizeEvent(event)


class AppGrid(QWidget):
    def __init__(self, apps: tuple[HubApp, ...], launch: Callable[[HubApp], None], parent=None):
        super().__init__(parent)
        self.cards: list[AppCard] = []
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        for index, app in enumerate(apps):
            card = AppCard(app, launch)
            self.cards.append(card)
            grid.addWidget(card, index // 4, index % 4)
        for column in range(4):
            grid.setColumnStretch(column, 1)

    def filter(self, query: str) -> None:
        query = query.casefold().strip()
        for card in self.cards:
            card.setVisible(not query or query in f"{card.app.title} {card.app.subtitle} {card.app.section}".casefold())


class BubbleButton(QPushButton):
    def __init__(self, app: HubApp, launch: Callable[[HubApp], None], diameter: int, parent=None):
        super().__init__(parent)
        self.app = app
        self.diameter = diameter
        self.setText(f"{app.title}\n{app.section}")
        self.setToolTip(app.subtitle)
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"{app.title}. {app.subtitle}")
        self.artwork = QPixmap(str(hub_art_path(app.art)))
        self.clicked.connect(lambda: launch(app))
        self.setText("")
        self.setIcon(self._circular_icon())
        self.setIconSize(QSize(diameter - 12, diameter - 12))
        self.setStyleSheet(
            f"QPushButton {{ background: {app.accent}; border: 3px solid rgba(255,255,255,175); "
            f"border-radius: {diameter // 2}px; }}"
            "QPushButton:hover { border: 5px solid white; }"
            "QPushButton:focus { border: 5px solid #ffe66d; }"
        )
        self.caption = QLabel(app.title, self)
        self.caption.setWordWrap(True)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.caption.setStyleSheet(
            "color: white; background: rgba(4, 12, 30, 175); border-radius: 9px; "
            "font-family: 'Segoe UI'; font-weight: 700; padding: 4px;"
        )
        self.caption.setGeometry(12, int(diameter * 0.57), diameter - 24, int(diameter * 0.30))

    def _circular_icon(self) -> QIcon:
        side = self.diameter - 12
        canvas = QPixmap(side, side)
        canvas.fill(Qt.GlobalColor.transparent)
        if self.artwork.isNull():
            return QIcon(canvas)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addEllipse(0.0, 0.0, float(side), float(side))
        painter.setClipPath(clip)
        scaled = self.artwork.scaled(canvas.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                     Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap((side - scaled.width()) // 2, (side - scaled.height()) // 2, scaled)
        painter.end()
        return QIcon(canvas)


class GalaxyWidget(QWidget):
    """Full-height, responsive bubble view with light-sun and dark-moon scenes."""

    def __init__(self, apps: tuple[HubApp, ...], launch: Callable[[HubApp], None], dark=False, parent=None):
        super().__init__(parent)
        self.dark = dark
        self.bubbles: list[BubbleButton] = []
        self.setMinimumHeight(720)
        for app in apps:
            diameter = 174 if app.id == "pipeline" else 142 if app.featured else 112
            self.bubbles.append(BubbleButton(app, launch, diameter, self))

    def set_dark(self, dark: bool) -> None:
        self.dark = dark
        self.update()

    def filter(self, query: str) -> None:
        query = query.casefold().strip()
        for bubble in self.bubbles:
            bubble.setVisible(not query or query in f"{bubble.app.title} {bubble.app.subtitle} {bubble.app.section}".casefold())
        self._arrange_bubbles()

    def resizeEvent(self, event):
        self._arrange_bubbles()
        super().resizeEvent(event)

    def showEvent(self, event):
        # QStackedWidget can size this page while it is hidden, in which case
        # no useful resize event reaches the child bubbles. Arrange once more
        # at the moment Galaxy mode becomes visible.
        super().showEvent(event)
        self._arrange_bubbles()

    def _arrange_bubbles(self) -> None:
        visible = [bubble for bubble in self.bubbles if bubble.isVisible()]
        width = max(700, self.width())
        columns = max(4, min(7, width // 190))
        cell_w = width / columns
        row_h = 170
        for index, bubble in enumerate(visible):
            row, column = divmod(index, columns)
            offset = cell_w * 0.22 if row % 2 else 0
            x = int(column * cell_w + (cell_w - bubble.width()) / 2 + offset)
            max_x = max(0, width - bubble.width() - 8)
            y = int(120 + row * row_h + (18 if column % 2 else 0))
            bubble.move(max(8, min(max_x, x)), y)
        rows = (len(visible) + columns - 1) // columns
        self.setMinimumHeight(max(720, 160 + rows * row_h))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, 0, self.height())
        if self.dark:
            gradient.setColorAt(0, QColor("#07152f"))
            gradient.setColorAt(1, QColor("#17113d"))
        else:
            gradient.setColorAt(0, QColor("#eaf8ff"))
            gradient.setColorAt(1, QColor("#fff4dc"))
        painter.fillRect(self.rect(), gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.dark:
            painter.setBrush(QColor("#f4f1cf"))
            painter.drawEllipse(self.width() - 150, 38, 72, 72)
            painter.setBrush(QColor("#07152f"))
            painter.drawEllipse(self.width() - 128, 25, 72, 72)
            painter.setBrush(QColor(255, 255, 255, 160))
            for index in range(38):
                x = (index * 137 + 31) % max(1, self.width())
                y = (index * 83 + 17) % max(1, self.height())
                painter.drawEllipse(x, y, 3, 3)
        else:
            painter.setBrush(QColor("#ffd166"))
            painter.drawEllipse(self.width() - 150, 36, 78, 78)
            painter.setPen(QPen(QColor(255, 193, 66, 120), 3))
            center = QPoint(self.width() - 111, 75)
            for dx, dy in ((0, -58), (0, 58), (-58, 0), (58, 0), (-42, -42), (42, 42), (-42, 42), (42, -42)):
                painter.drawLine(center, center + QPoint(dx, dy))


class MainHubDialog(QDialog):
    """Persistent Main Hub with fixed navigation and four visual combinations."""

    NAV_ITEMS = ("Home", "Movement Analysis", "Games", "Training & Rehab")

    def __init__(
        self,
        parent=None,
        *,
        open_pipeline: Callable[[], None] | None = None,
        open_pipeline_mode: Callable[[int], None] | None = None,
        resume_mode: Callable[[int], None] | None = None,
        state_dir: Path | None = None,
        preferences: PreferenceStore | None = None,
    ):
        super().__init__(parent)
        self._open_pipeline_callback = open_pipeline
        self._open_pipeline_mode_callback = open_pipeline_mode
        self._resume_mode_callback = resume_mode
        self.state_dir = state_dir or Path(__file__).resolve().parents[1] / ".aihumo"
        self.preferences = preferences or PreferenceStore(self.state_dir / "settings.json")
        self.apps = hub_apps()
        self.setWindowTitle("AIHuMo Main Hub")
        self.resize(1320, 820)
        self.filterables: list[AppGrid | GalaxyWidget] = []

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
        layout.setContentsMargins(22, 12, 22, 12)
        title = QLabel("◒  AIHuMo Main Hub", objectName="hubBrand")
        layout.addWidget(title)
        layout.addSpacing(18)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for index, text in enumerate(self.NAV_ITEMS):
            button = QPushButton(text, objectName="navButton")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, page=index: self.pages.setCurrentIndex(page))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)
        layout.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search apps, sessions, files…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(300)
        self.search.textChanged.connect(self._filter_apps)
        layout.addWidget(self.search)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(("Light", "Dark"))
        self.theme_combo.currentTextChanged.connect(self._visual_option_changed)
        layout.addWidget(self.theme_combo)
        self.galaxy_toggle = QCheckBox("Galaxy")
        self.galaxy_toggle.toggled.connect(self._visual_option_changed)
        layout.addWidget(self.galaxy_toggle)
        settings = QPushButton("⚙", objectName="iconButton")
        settings.setToolTip("Open AIHuMo settings")
        settings.clicked.connect(self._open_settings)
        layout.addWidget(settings)
        close = QPushButton("Exit", objectName="quietButton")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        return bar

    def _home_page(self) -> QWidget:
        self.home_scroll = QScrollArea()
        self.home_scroll.setWidgetResizable(True)
        self.home_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.home_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(objectName="hubBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(18)
        hero = QLabel("Welcome back\nContinue movement analysis, training, or play.", objectName="heroTitle")
        layout.addWidget(hero)
        heading = QLabel("Recent Work", objectName="sectionTitle")
        layout.addWidget(heading)
        records = self._recent_records()
        if records:
            for record in records:
                layout.addWidget(RecentCard(record, lambda mode=record["mode"]: self._resume_mode(mode), False))
        else:
            empty = QLabel("No recent sessions yet. Open the AIHuMo Pipeline or a game to begin.", objectName="emptyState")
            empty.setMinimumHeight(150)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty)
        layout.addSpacing(12)
        all_heading = QLabel("All Apps", objectName="sectionTitle")
        layout.addWidget(all_heading)
        self.all_apps_stack = QStackedWidget()
        standard = AppGrid(self.apps, self._launch_app)
        # Keep the original public button handles so existing integrations and
        # automation can continue launching the same workspaces after the Hub
        # visual redesign.
        cards = {card.app.id: card for card in standard.cards}
        self.aihumo_button = cards["pipeline"]
        self.justice_dance_button = cards["just_dance"]
        self.game_buttons = {
            card.app.game_id: card for card in standard.cards if card.app.game_id is not None
        }
        self.galaxy = GalaxyWidget(self.apps, self._launch_app)
        self.filterables.extend((standard, self.galaxy))
        self.all_apps_stack.addWidget(standard)
        self.all_apps_stack.addWidget(self.galaxy)
        layout.addWidget(self.all_apps_stack)
        self.home_scroll.setWidget(body)
        return self.home_scroll

    def _category_page(self, section: str) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(objectName="hubBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 28, 28, 28)
        heading = QLabel(section, objectName="heroTitle")
        layout.addWidget(heading)
        description = {
            "Movement Analysis": "Process recordings, annotate movement, align cameras, and inspect synchronized graphs.",
            "Games": "Reaction, rhythm, coordination, social, and movement-play experiences.",
            "Training & Rehab": "Controlled balance, mobility, rehabilitation, gait, and ergonomic workspaces.",
        }[section]
        layout.addWidget(QLabel(description, objectName="mutedText"))
        apps = tuple(app for app in self.apps if app.section == section)
        grid = AppGrid(apps, self._launch_app)
        self.filterables.append(grid)
        layout.addWidget(grid)
        layout.addStretch(1)
        scroll.setWidget(body)
        return scroll

    def _recent_records(self) -> list[dict]:
        stores = (
            (0, "AIHuMo Processing", "recent_processing.json", "#2dc7e8", "processing.jpg"),
            (1, "Annotation Studio", "recent_work.json", "#8a6df1", "annotation.jpg"),
            (2, "Session Alignment", "recent_alignments.json", "#5a8dee", "partner-sync.jpg"),
            (3, "Graph Viewer 2D", "recent_graphs.json", "#28c8a2", "graphs-3d.jpg"),
            (4, "Graph Viewer 3D", "recent_poses.json", "#e58c55", "graphs-3d.jpg"),
        )
        records = []
        for mode, title, filename, accent, art in stores:
            path = self.state_dir / filename
            if not path.is_file():
                continue
            try:
                document = load_json(path)
                items = document.get("items", [])
                if not items:
                    continue
                item = items[0]
                files = item.get("files", {})
                preferred = next((value for key, value in files.items() if key in {
                    "sourceVideo", "processedVideo", "featuresParquet", "alignmentJson", "annotationJson"
                } and value), "Saved workspace")
                records.append({
                    "mode": mode, "title": title, "file": Path(str(preferred)).name,
                    "detail": item.get("name", "Recent AIHuMo workspace"),
                    "status": f"Frame {item.get('lastFrame', 0):,}" if item.get("lastFrame") is not None else "Ready",
                    "accent": accent, "art": art, "mtime": path.stat().st_mtime,
                })
            except (OSError, ValueError, TypeError):
                continue
        return sorted(records, key=lambda record: record["mtime"], reverse=True)[:3]

    def _launch_app(self, app: HubApp) -> None:
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
        MovementGameDialog(game_id, self).exec()

    def _filter_apps(self, text: str) -> None:
        for widget in self.filterables:
            widget.filter(text)

    def _visual_option_changed(self, *_args) -> None:
        if not hasattr(self, "all_apps_stack"):
            return
        self.preferences.save(replace(
            self.preferences.values,
            theme=self.theme_combo.currentText(),
            hub_galaxy_mode=self.galaxy_toggle.isChecked(),
        ))
        self._apply_preferences()

    def _open_settings(self) -> None:
        if PreferencesDialog(self.preferences, self).exec() == QDialog.DialogCode.Accepted:
            self._apply_preferences()

    def _apply_preferences(self) -> None:
        values = self.preferences.values
        theme = "Dark" if values.theme == "Dark" else "Light"
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentText(theme)
        self.theme_combo.blockSignals(False)
        self.galaxy_toggle.blockSignals(True)
        self.galaxy_toggle.setChecked(values.hub_galaxy_mode)
        self.galaxy_toggle.blockSignals(False)
        self.all_apps_stack.setCurrentIndex(1 if values.hub_galaxy_mode else 0)
        self.galaxy.set_dark(theme == "Dark")
        self.setStyleSheet(self._stylesheet(theme == "Dark"))

    @staticmethod
    def _stylesheet(dark: bool) -> str:
        if dark:
            colors = {
                "window": "#07152f", "panel": "#101f3e", "card": "#17284a", "text": "#f5f7ff",
                "muted": "#b8c2dc", "border": "#33466d", "accent": "#24d7e6", "accent2": "#806cf2",
            }
        else:
            colors = {
                "window": "#f7f6fb", "panel": "#ffffff", "card": "#ffffff", "text": "#10214a",
                "muted": "#65708a", "border": "#dde2ee", "accent": "#27c7df", "accent2": "#826cf0",
            }
        return f"""
            QDialog, QWidget#hubBody {{ background: {colors['window']}; color: {colors['text']}; }}
            QFrame#navBar {{ background: {colors['panel']}; border-bottom: 1px solid {colors['border']}; }}
            QLabel {{ color: {colors['text']}; }}
            QLabel#hubBrand {{ font-size: 20px; font-weight: 800; }}
            QLabel#heroTitle {{ font-size: 27px; font-weight: 800; padding: 8px 2px; }}
            QLabel#sectionTitle {{ font-size: 19px; font-weight: 750; padding-top: 8px; }}
            QLabel#mutedText {{ color: {colors['muted']}; }}
            QLabel#emptyState {{ color: {colors['muted']}; background: {colors['card']}; border: 1px dashed {colors['border']}; border-radius: 16px; }}
            QLabel#statusChip {{ color: {colors['text']}; background: {colors['window']}; border-radius: 13px; padding: 7px 12px; }}
            QFrame#recentCard {{ background: {colors['card']}; border: 1px solid {colors['border']}; border-radius: 16px; }}
            QPushButton#navButton {{ color: {colors['muted']}; background: transparent; border: none; border-radius: 17px; padding: 8px 14px; font-weight: 650; }}
            QPushButton#navButton:hover {{ color: {colors['text']}; background: {colors['window']}; }}
            QPushButton#navButton:checked {{ color: #07152f; background: {colors['accent']}; }}
            QToolButton#appCard {{ color: {colors['text']}; background: {colors['card']}; border: 1px solid {colors['border']}; border-radius: 15px; padding: 10px; font-weight: 700; }}
            QToolButton#appCard:hover {{ border: 2px solid {colors['accent']}; background: {colors['panel']}; }}
            QPushButton#primaryButton {{ color: white; background: {colors['accent2']}; border: none; border-radius: 15px; padding: 9px 18px; font-weight: 700; }}
            QPushButton#primaryButton:hover {{ background: {colors['accent']}; color: #07152f; }}
            QPushButton#quietButton, QPushButton#iconButton {{ color: {colors['text']}; background: transparent; border: 1px solid {colors['border']}; border-radius: 12px; padding: 7px 11px; }}
            QLineEdit, QComboBox {{ color: {colors['text']}; background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 14px; padding: 7px 12px; }}
            QCheckBox {{ color: {colors['text']}; spacing: 7px; }}
            QScrollArea {{ border: none; background: {colors['window']}; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px; }}
            QScrollBar::handle:vertical {{ background: {colors['border']}; min-height: 40px; border-radius: 5px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """

    def resizeEvent(self, event):
        if hasattr(self, "galaxy") and hasattr(self, "home_scroll"):
            self.galaxy.setMinimumHeight(max(650, self.home_scroll.viewport().height() - 20))
        super().resizeEvent(event)
