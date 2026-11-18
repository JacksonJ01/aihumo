"""Human review dialog for interpretable exercise suggestions."""
from __future__ import annotations

from typing import Callable, Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout


class ExerciseMappingReviewDialog(QDialog):
    def __init__(self, suggestions: Sequence, *, on_accept: Callable[[object], None], parent=None):
        super().__init__(parent)
        self.suggestions = list(suggestions)
        self.on_accept = on_accept
        self.setWindowTitle("Review exercise mapping suggestions")
        self.resize(900, 480)
        layout = QVBoxLayout(self)
        intro = QLabel("These classifications are provisional. Select one to load it into the annotation editor, then save the annotation to confirm it.")
        intro.setWordWrap(True); layout.addWidget(intro)
        self.table = QTableWidget(len(self.suggestions), 5)
        self.table.setHorizontalHeaderLabels(["Exercise", "Family", "Score", "Uncertainty", "Evidence"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for row, suggestion in enumerate(self.suggestions):
            values = [suggestion.name, suggestion.family, f"{suggestion.score:.3f}", f"{suggestion.uncertainty:.3f}", " · ".join(suggestion.evidence)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value)); item.setData(Qt.ItemDataRole.UserRole, suggestion)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents(); layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        accept = QPushButton("Use selected suggestion")
        accept.clicked.connect(self._accept_selected)
        actions.addWidget(accept); actions.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject); actions.addWidget(close)
        layout.addLayout(actions)

    def _accept_selected(self):
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return
        self.on_accept(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
        self.accept()

