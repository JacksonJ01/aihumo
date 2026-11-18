"""PyQt6 presentation for the pure Mode 0 resource estimate."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QGroupBox, QLabel, QProgressBar,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from aihumo.resource_estimation import GIB, ResourceEstimate


def format_bytes(value: int) -> str:
    sign = "−" if value < 0 else ""
    amount = abs(int(value))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{sign}{amount:.0f} {unit}" if unit == "B" else f"{sign}{amount:.2f} {unit}"
        amount /= 1024
    return f"{sign}{amount:.2f} TB"


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "calculating…"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


class PreflightDialog(QDialog):
    """Require an explicit review of estimates before Mode 0 starts."""

    CATEGORY_LABELS = {
        "source_copies": "Source copies",
        "skeleton_mp4": "Skeleton-overlay MP4s",
        "raw_landmarks_parquet": "Raw landmark Parquet",
        "feature_parquet": "Feature Parquet",
        "annotations_and_quality": "Suggestions and quality metadata",
        "graphs_and_visualizations": "Graphs and visualizations",
    }

    def __init__(self, estimate: ResourceEstimate, parent=None):
        super().__init__(parent)
        self.estimate = estimate
        self.setWindowTitle("AIHuMo Mode 0 — Preflight Review")
        self.resize(760, 680)
        layout = QVBoxLayout(self)
        title = QLabel(f"{len(estimate.videos)} video(s) · {estimate.profile.title()} profile")
        title.setStyleSheet("font-size: 20px; font-weight: 750;")
        layout.addWidget(title)
        summary = QLabel(
            f"Recording duration: {format_duration(int(estimate.total_duration_s))}  ·  "
            f"Frames: {estimate.total_frames:,}  ·  Source storage: {format_bytes(estimate.source_storage_bytes)}"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        metrics = QGroupBox("Capacity and time estimate")
        grid = QGridLayout(metrics)
        items = (
            ("Estimated processing time", f"{format_duration(estimate.processing_time_s.low)}–{format_duration(estimate.processing_time_s.high)}"),
            ("Estimated final new output", f"{format_bytes(estimate.final_output.low)}–{format_bytes(estimate.final_output.high)}"),
            ("Estimated peak additional", f"{format_bytes(estimate.peak_additional.low)}–{format_bytes(estimate.peak_additional.high)}"),
            ("Available destination storage", format_bytes(estimate.available_bytes)),
            ("Reserved safety margin", format_bytes(estimate.safety_margin_bytes)),
            ("Expected remaining storage", f"{format_bytes(estimate.expected_remaining.low)}–{format_bytes(estimate.expected_remaining.high)}"),
        )
        for index, (label, value) in enumerate(items):
            row, column = divmod(index, 2)
            card = QLabel(f"<span style='color:#7894bd'>{label}</span><br><b style='font-size:17px'>{value}</b>")
            card.setTextFormat(Qt.TextFormat.RichText)
            card.setMargin(10)
            grid.addWidget(card, row, column)
        layout.addWidget(metrics)

        self.table = QTableWidget(len(estimate.categories) + 1, 3)
        self.table.setHorizontalHeaderLabels(("Output category", "Low estimate", "High estimate"))
        self.table.horizontalHeader().setStretchLastSection(True)
        for row, (name, value) in enumerate(estimate.categories.items()):
            self.table.setItem(row, 0, QTableWidgetItem(self.CATEGORY_LABELS.get(name, name.replace("_", " ").title())))
            self.table.setItem(row, 1, QTableWidgetItem(format_bytes(value.low)))
            self.table.setItem(row, 2, QTableWidgetItem(format_bytes(value.high)))
        row = len(estimate.categories)
        self.table.setItem(row, 0, QTableWidgetItem("Temporary overhead"))
        self.table.setItem(row, 1, QTableWidgetItem(format_bytes(estimate.temporary_overhead.low)))
        self.table.setItem(row, 2, QTableWidgetItem(format_bytes(estimate.temporary_overhead.high)))
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table, 1)

        capacity = QProgressBar()
        capacity.setRange(0, 1000)
        capacity.setValue(min(1000, int(estimate.peak_additional.high / max(1, estimate.available_bytes) * 1000)))
        capacity.setFormat("High peak estimate uses %p% of currently available storage")
        layout.addWidget(capacity)
        safe = estimate.expected_remaining.low >= 0
        warning_text = "\n".join(f"• {item}" for item in estimate.warnings)
        if not warning_text:
            warning_text = "Estimate is within the available capacity and configured safety margin."
        self.warning = QLabel(warning_text)
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet(
            "padding:10px; border-radius:8px; "
            + ("background:#3b1220; color:#ffd6df;" if not safe else "background:#123426; color:#d4ffe8;")
        )
        layout.addWidget(self.warning)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continue processing")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(safe)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
