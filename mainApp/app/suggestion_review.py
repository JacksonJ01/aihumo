"""Human review controls for non-authoritative Mode 0 annotation proposals."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)


class SuggestionReviewDialog(QDialog):
    def __init__(
        self,
        document: dict[str, Any],
        *,
        on_accept: Callable[[dict[str, Any]], bool],
        on_reject: Callable[[dict[str, Any]], bool],
        on_edit: Callable[[dict[str, Any]], bool],
        on_goto: Callable[[dict[str, Any]], bool],
        parent=None,
    ):
        super().__init__(parent)
        self.document = document
        self.on_accept = on_accept
        self.on_reject = on_reject
        self.on_edit = on_edit
        self.on_goto = on_goto
        self.setWindowTitle("Review Mode 0 Annotation Suggestions")
        self.resize(980, 620)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Suggestions are provisional. Accepted or edited rows are copied into annotations.json; "
            "the original proposal and review decision remain in the separate suggestion file."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        filters = QHBoxLayout()
        self.layer = QComboBox()
        self.layer.addItem("All layers", "")
        for value in ("activity_state", "set", "rep", "phase", "form_interval"):
            self.layer.addItem(value.replace("_", " ").title(), value)
        self.pending_only = QCheckBox("Pending only")
        self.pending_only.setChecked(True)
        self.uncertain_first = QCheckBox("Uncertain first")
        self.uncertain_first.setChecked(True)
        filters.addWidget(QLabel("Layer"))
        filters.addWidget(self.layer)
        filters.addWidget(self.pending_only)
        filters.addWidget(self.uncertain_first)
        filters.addStretch(1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Layer", "Label", "Frames", "Time", "Confidence", "Method", "Review"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.doubleClicked.connect(lambda _index: self._invoke(self.on_goto))
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addWidget(QPushButton("Go to", clicked=lambda: self._invoke(self.on_goto)))
        actions.addWidget(QPushButton("Edit boundaries/labels…", clicked=lambda: self._invoke(self.on_edit)))
        actions.addWidget(QPushButton("Accept selected", clicked=lambda: self._invoke(self.on_accept)))
        actions.addWidget(QPushButton("Reject selected", clicked=lambda: self._invoke(self.on_reject)))
        self.accept_visible_button = QPushButton("Accept visible pending…")
        self.accept_visible_button.clicked.connect(self._accept_visible)
        actions.addWidget(self.accept_visible_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.layer.currentIndexChanged.connect(self.refresh)
        self.pending_only.toggled.connect(self.refresh)
        self.uncertain_first.toggled.connect(self.refresh)
        self.refresh()

    def set_document(self, document: dict[str, Any]) -> None:
        self.document = document
        self.refresh()

    def _visible(self) -> list[dict[str, Any]]:
        selected_layer = str(self.layer.currentData() or "")
        rows = [
            item for item in self.document.get("suggestions", [])
            if (not selected_layer or item.get("annotation_layer") == selected_layer)
            and (not self.pending_only.isChecked() or item.get("review_status", "pending") == "pending")
        ]
        if self.uncertain_first.isChecked():
            rows.sort(key=lambda item: (float(item.get("confidence", 0.0)), item.get("start_time_s", 0.0)))
        else:
            rows.sort(key=lambda item: (item.get("start_time_s", 0.0), item.get("annotation_layer", "")))
        return rows

    def refresh(self) -> None:
        rows = self._visible()
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                str(row.get("annotation_layer", "")).replace("_", " ").title(),
                str(row.get("suggested_label", "")),
                f"{row.get('start_frame')}–{row.get('end_frame')}",
                f"{float(row.get('start_time_s', 0.0)):.3f}–{float(row.get('end_time_s', 0.0)):.3f} s",
                f"{float(row.get('confidence', 0.0)):.0%}",
                str(row.get("detection_method", "")),
                str(row.get("review_status", "pending")).title(),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row.get("suggestion_id"))
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
        if rows:
            self.table.selectRow(0)
        self.accept_visible_button.setEnabled(any(row.get("review_status", "pending") == "pending" for row in rows))

    def _selected(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return None
        suggestion_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return next(
            (item for item in self.document.get("suggestions", []) if item.get("suggestion_id") == suggestion_id),
            None,
        )

    def _invoke(self, callback) -> None:
        selected = self._selected()
        if selected is None:
            return
        if callback(selected):
            self.refresh()

    def _accept_visible(self) -> None:
        rows = [row for row in self._visible() if row.get("review_status", "pending") == "pending"]
        if not rows:
            return
        answer = QMessageBox.question(
            self,
            "Accept visible suggestions",
            f"Accept {len(rows)} visible pending suggestion(s) in hierarchy order?\n\n"
            "Each row is validated before annotations.json is changed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        priority = {"activity_state": 0, "set": 1, "rep": 2, "phase": 3, "form_interval": 4}
        accepted = 0
        for row in sorted(rows, key=lambda item: (priority.get(item.get("annotation_layer"), 99), item.get("start_frame", 0))):
            if not self.on_accept(row):
                break
            accepted += 1
        self.refresh()
        if accepted != len(rows):
            QMessageBox.warning(
                self, "Review stopped",
                f"Accepted {accepted} of {len(rows)} suggestions. The next row did not pass annotation validation."
            )

