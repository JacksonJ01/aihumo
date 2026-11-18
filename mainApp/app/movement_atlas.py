"""Mode 5 Movement Atlas: inspect versioned PCA encodings without training models."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class MovementAtlasWindow(QMainWindow):
    """A compact 2D/3D view over the exported Movement Atlas manifest."""

    def __init__(self, processed_root: str | Path | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AIHuMo Movement Atlas — Mode 5")
        self.resize(1100, 760)
        self.processed_root = Path(processed_root) if processed_root else None
        self.manifest_path: Path | None = None
        self.manifest: dict = {"encodings": [], "transforms": {}}
        self.figure = Figure(layout="constrained")
        self.canvas = FigureCanvas(self.figure)
        self.view = QComboBox(); self.view.addItems(["2D PCA", "3D PCA"])
        self.group = QComboBox(); self.group.addItems(["angles", "angles_distances", "angles_distances_motion"])
        self.family = QComboBox(); self.family.addItem("All families", "")
        self.exercise = QComboBox(); self.exercise.addItem("All exercises", "")
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Exercise", "Family", "Annotation", "Session", "Frames", "Duration (s)", "Source"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._build_ui()
        self._discover_manifest()

    def activate_review(self):
        """Match the shared review-window protocol used by other modes."""
        self.show(); self.raise_(); self.activateWindow()

    def _build_ui(self):
        central = QWidget(); layout = QVBoxLayout(central)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("Movement family")); heading.addWidget(self.family)
        heading.addWidget(QLabel("Exercise")); heading.addWidget(self.exercise)
        heading.addWidget(QLabel("Encoding")); heading.addWidget(self.group)
        heading.addWidget(self.view)
        choose = QPushButton("Load manifest…", clicked=self._choose_manifest)
        refresh = QPushButton("Refresh", clicked=self._reload)
        heading.addWidget(choose); heading.addWidget(refresh)
        layout.addLayout(heading); layout.addWidget(self.canvas, 3); layout.addWidget(self.table, 2)
        self.setCentralWidget(central)
        self.group.currentTextChanged.connect(self._render)
        self.view.currentTextChanged.connect(self._render)
        self.family.currentIndexChanged.connect(self._render)
        self.exercise.currentIndexChanged.connect(self._render)
        self.table.cellDoubleClicked.connect(self._open_source)

    def _discover_manifest(self):
        if self.processed_root and self.processed_root.is_dir():
            paths = sorted(self.processed_root.glob("**/movement_atlas/movement_encoding_manifest.json"))
            if paths:
                self.manifest_path = paths[-1]
        self._reload()

    def _choose_manifest(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Movement Atlas manifest", str(self.processed_root or Path.cwd()), "JSON (*.json)")
        if path:
            self.manifest_path = Path(path); self._reload()

    def _reload(self):
        if not self.manifest_path or not self.manifest_path.is_file():
            self.manifest = {"encodings": [], "transforms": {}}
        else:
            try:
                self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Movement Atlas", f"Could not load manifest: {exc}")
                self.manifest = {"encodings": [], "transforms": {}}
        families = sorted({str(item.get("family") or "") for item in self.manifest.get("encodings", []) if item.get("family")})
        exercises = sorted({str(item.get("exercise") or "") for item in self.manifest.get("encodings", []) if item.get("exercise")})
        self.family.blockSignals(True); self.family.clear(); self.family.addItem("All families", ""); self.family.addItems(families); self.family.blockSignals(False)
        self.exercise.blockSignals(True); self.exercise.clear(); self.exercise.addItem("All exercises", ""); self.exercise.addItems(exercises); self.exercise.blockSignals(False)
        self._render()

    def _filtered(self):
        family = self.family.currentData() or ""; exercise = self.exercise.currentData() or ""
        return [item for item in self.manifest.get("encodings", [])
                if (not family or str(item.get("family") or "") == family)
                and (not exercise or str(item.get("exercise") or "") == exercise)]

    def _render(self):
        group = self.group.currentText(); items = [item for item in self._filtered() if item.get("feature_group") == group]
        transform = self.manifest.get("transforms", {}).get(group, {})
        coordinates = np.asarray(transform.get("coordinates", []), dtype=float)
        self.figure.clear()
        axis = self.figure.add_subplot(111, projection="3d" if self.view.currentText().startswith("3D") else None)
        if len(coordinates):
            # Transform rows are in manifest order; filter by the matching rows.
            all_items = [item for item in self.manifest.get("encodings", []) if item.get("feature_group") == group]
            indices = [all_items.index(item) for item in items]
            points = coordinates[indices] if coordinates.ndim == 2 and len(coordinates) > max(indices, default=-1) else coordinates[:len(items)]
            labels = [str(item.get("exercise") or "unknown") for item in items]
            colors = np.arange(len(points))
            if points.shape[1] >= 3 and hasattr(axis, "scatter") and self.view.currentText().startswith("3D"):
                axis.scatter(points[:, 0], points[:, 1], points[:, 2], c=colors, cmap="viridis")
                axis.set_zlabel("PC3")
            elif points.shape[1] >= 2:
                axis.scatter(points[:, 0], points[:, 1], c=colors, cmap="viridis")
            elif points.shape[1] == 1:
                axis.scatter(points[:, 0], np.zeros(len(points)), c=colors, cmap="viridis")
            axis.set_xlabel("PC1"); axis.set_ylabel("PC2"); axis.set_title(f"Movement Atlas · {group}")
        else:
            axis.text(0.5, 0.5, "No confirmed encodings yet", ha="center", va="center", transform=axis.transAxes)
            axis.set_title(f"Movement Atlas · {group}")
        self.canvas.draw_idle()
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = [item.get("exercise") or "Unclassified", item.get("family") or "", item.get("annotation_id") or "", item.get("session_id") or "", f"{item.get('start_frame', '')}–{item.get('end_frame', '')}", f"{float(item.get('duration_s') or 0):.3f}", item.get("source_annotation") or ""]
            for column, value in enumerate(values): self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def _open_source(self, row: int, _column: int):
        items = [item for item in self._filtered() if item.get("feature_group") == self.group.currentText()]
        if not (0 <= row < len(items)):
            return
        source = items[row].get("source_annotation") or ""
        if source:
            QMessageBox.information(self, "Movement Atlas source", f"Source annotation:\n{source}\n\nFrames: {items[row].get('start_frame')}–{items[row].get('end_frame')}\n\nUse the annotation or graph viewer to inspect the original segment.")

