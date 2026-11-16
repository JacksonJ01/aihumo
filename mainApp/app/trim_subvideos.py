"""Create provenance-preserving trimmed AIHuMo recording sub-sessions.

The source recording is never modified.  Each exported sub-session receives a
new skeleton MP4, a frame-aligned feature Parquet, optional raw-landmark
Parquet, optional clipped annotation JSON/Parquet, metadata, and a trim
manifest describing the source frame/time range.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from tempfile import mkdtemp
from typing import Callable, Iterable

import cv2
import numpy as np
import pandas as pd

from aihumo.annotations import build_rep_summary, save_annotation_parquet
from aihumo.features import TIME_COLUMNS
from aihumo.storage import load_json, load_parquet, save_json_atomic, save_parquet_atomic

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QMessageBox, QProgressDialog, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)


Progress = Callable[[float, str], None]


@dataclass(frozen=True)
class TrimSegment:
    """A half-open time request entered by the operator."""

    start_s: float
    end_s: float
    label: str = ""

    def __post_init__(self) -> None:
        if not np.isfinite(self.start_s) or not np.isfinite(self.end_s) or self.start_s < 0:
            raise ValueError("Trim times must be finite and non-negative.")
        if self.end_s <= self.start_s:
            raise ValueError("Trim end time must be greater than the start time.")


def processed_inventory(processed_root: str | Path) -> dict[str, object]:
    """Return a lightweight count of existing processed sessions/recordings."""
    root = Path(processed_root)
    sessions = sorted(path for path in root.glob("S[0-9]*") if path.is_dir()) if root.is_dir() else []
    recordings = [child for session in sessions for child in session.iterdir() if child.is_dir()]
    return {
        "root": str(root),
        "sessionCount": len(sessions),
        "recordingCount": len(recordings),
        "nextSessionId": next_session_id(root),
    }


def next_session_id(processed_root: str | Path) -> str:
    """Choose the next stable S000x folder without overwriting an existing one."""
    root = Path(processed_root)
    values = []
    for path in root.glob("S[0-9]*") if root.is_dir() else ():
        match = re.fullmatch(r"S(\d+)", path.name)
        if match and path.is_dir():
            values.append(int(match.group(1)))
    return f"S{max(values, default=0) + 1:03d}"


def _time_column(columns: Iterable[str]) -> str:
    for name in TIME_COLUMNS:
        if name in columns:
            return name
    raise ValueError("The feature Parquet has no supported source-time column.")


def _frame_column(columns: Iterable[str]) -> str:
    for name in ("frame_id", "frameIndex", "frame_index"):
        if name in columns:
            return name
    raise ValueError("The feature Parquet has no supported frame column.")


def _source_artifacts(video_path: Path, features_path: Path, annotation_json_path: Path | None) -> dict[str, Path | None]:
    annotation = annotation_json_path
    if annotation is None:
        candidate = features_path.parent.parent / "annotations" / f"{features_path.stem.replace('_features', '_annotations')}.json"
        annotation = candidate if candidate.is_file() else None
    landmarks = features_path.with_name(features_path.name.replace("_features.parquet", "_landmarks.parquet"))
    return {
        "video": video_path,
        "features": features_path,
        "landmarks": landmarks if landmarks.is_file() else None,
        "annotations": annotation,
    }


def _frame_bounds(features: pd.DataFrame, segment: TrimSegment) -> tuple[int, int, str, np.ndarray]:
    time_name = _time_column(features.columns)
    frame_name = _frame_column(features.columns)
    times = pd.to_numeric(features[time_name], errors="coerce").to_numpy(dtype=float)
    if len(times) == 0 or not np.isfinite(times).all() or np.any(np.diff(times) < 0):
        raise ValueError("Feature timestamps must be finite and monotonic before trimming.")
    first_time = float(times[0])
    start = first_time + segment.start_s
    end = first_time + segment.end_s
    first = int(np.searchsorted(times, start, side="left"))
    last = int(np.searchsorted(times, end, side="right")) - 1
    if first > last or first >= len(times) or last < 0:
        raise ValueError(f"Trim {segment.start_s:g}–{segment.end_s:g}s contains no feature frames.")
    first = max(0, first)
    last = min(len(times) - 1, last)
    return first, last, time_name, times


def _normalise_frame_table(frame_df: pd.DataFrame, *, frame_name: str, time_name: str, source_first: int) -> pd.DataFrame:
    out = frame_df.reset_index(drop=True).copy()
    if frame_name in out:
        out[frame_name] = np.arange(len(out), dtype=np.int64)
    if "frame_id" in out and frame_name != "frame_id":
        out["frame_id"] = np.arange(len(out), dtype=np.int64)
    if "frameIndex" in out:
        out["frameIndex"] = np.arange(len(out), dtype=np.int64)
    if "frame_index" in out:
        out["frame_index"] = np.arange(len(out), dtype=np.int64)
    if "sourceFrameIndex" in out:
        # This column intentionally retains the original recording frame.
        out["sourceFrameIndex"] = pd.to_numeric(out["sourceFrameIndex"], errors="coerce")
    else:
        out["sourceFrameIndex"] = np.arange(source_first, source_first + len(out), dtype=np.int64)
    out[time_name] = pd.to_numeric(out[time_name], errors="coerce") - float(out[time_name].iloc[0])
    for name in ("timeElapsedS", "timestamp_s", "time_elapsed_s"):
        if name in out and name != time_name:
            out[name] = pd.to_numeric(out[name], errors="coerce") - float(out[name].iloc[0])
    for name in out.columns:
        lowered = str(name).casefold()
        if "delta" in lowered and "time" in lowered:
            out.loc[0, name] = np.nan
        elif "velocity" in lowered or "acceleration" in lowered:
            # The first retained frame has no valid derivative across the cut.
            out.loc[0, name] = np.nan
    return out


def _clip_annotations(path: Path, *, first: int, last: int, new_times: np.ndarray,
                      new_video_id: str, new_session_id: str) -> dict | None:
    if not path.is_file():
        return None
    document = load_json(path)
    kept = []
    for original in document.get("annotations", []):
        try:
            original_start = int(original["start_frame"])
            original_end = int(original["end_frame"])
        except (KeyError, TypeError, ValueError):
            continue
        if original_end < first or original_start > last:
            continue
        row = dict(original)
        clipped_start = max(first, original_start)
        clipped_end = min(last, original_end)
        row["start_frame"] = clipped_start - first
        row["end_frame"] = clipped_end - first
        row["start_time_s"] = float(new_times[row["start_frame"]])
        row["end_time_s"] = float(new_times[row["end_frame"]])
        row["duration_s"] = max(0.0, row["end_time_s"] - row["start_time_s"])
        row["source_start_frame"] = original_start
        row["source_end_frame"] = original_end
        kept.append(row)
    if not kept:
        return None
    result = dict(document)
    result["video_id"] = new_video_id
    result["session_id"] = new_session_id
    result["source_video_id"] = document.get("video_id")
    result["annotations"] = kept
    result["trimmed_from"] = {
        "source_annotation_file": str(path),
        "source_first_frame": first,
        "source_last_frame": last,
    }
    return result


def _write_video(source: Path, destination: Path, first: int, last: int, progress: Progress | None = None) -> None:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError(f"Could not open source video: {source}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if width <= 0 or height <= 0 or not np.isfinite(fps) or fps <= 0:
        capture.release()
        raise ValueError(f"Source video has invalid dimensions or FPS: {source}")
    partial = destination.with_suffix(".partial.mp4")
    partial.unlink(missing_ok=True)
    writer = cv2.VideoWriter(str(partial), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    try:
        if not writer.isOpened() or not capture.set(cv2.CAP_PROP_POS_FRAMES, first):
            raise ValueError(f"Could not start trimmed video export for {source.name}.")
        total = last - first + 1
        for index in range(total):
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f"Could not read source frame {first + index} from {source.name}.")
            writer.write(frame)
            if progress and index % max(1, total // 25) == 0:
                progress(index / max(1, total), f"Writing {destination.name}")
    finally:
        writer.release()
        capture.release()
    verify = cv2.VideoCapture(str(partial))
    try:
        if not verify.isOpened() or int(verify.get(cv2.CAP_PROP_FRAME_COUNT)) != total:
            raise ValueError(f"Trimmed video verification failed for {destination.name}.")
    finally:
        verify.release()
    os.replace(partial, destination)


def trim_recording_artifacts(*, video_path: str | Path, features_path: str | Path,
                             output_root: str | Path, segments: list[TrimSegment],
                             session_id: str | None = None,
                             annotation_json_path: str | Path | None = None,
                             segment_number_start: int = 1,
                             metadata_overrides: dict | None = None,
                             progress: Progress | None = None) -> list[Path]:
    """Export one or more time segments as new processed recording folders."""
    video = Path(video_path).resolve(strict=True)
    features_path = Path(features_path).resolve(strict=True)
    features = load_parquet(features_path)
    if len(features) == 0:
        raise ValueError("Cannot trim an empty feature Parquet.")
    artifacts = _source_artifacts(video, features_path, Path(annotation_json_path) if annotation_json_path else None)
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    source_stem = video.stem.removesuffix("_skeleton")
    outputs: list[Path] = []
    for segment_index, segment in enumerate(segments, segment_number_start):
        first, last, time_name, times = _frame_bounds(features, segment)
        # A supplied session ID is intentional: Mode 2 passes one shared ID
        # for every camera in the same aligned sub-segment.  Do not silently
        # replace it for later segment numbers, or the camera folders drift
        # into different sessions.
        segment_session = session_id or next_session_id(root)
        video_id = f"{source_stem}_sub{segment_index:02d}"
        output_dir = root / segment_session / video_id
        if output_dir.exists():
            raise FileExistsError(f"Refusing to overwrite existing trim output: {output_dir}")
        temp_dir = Path(mkdtemp(prefix=f".{video_id}-", dir=root))
        try:
            video_dir, parquet_dir, metadata_dir, annotations_dir = [temp_dir / name for name in ("video", "parquet", "metadata", "annotations")]
            for directory in (video_dir, parquet_dir, metadata_dir, annotations_dir):
                directory.mkdir(parents=True)
            sliced = features.iloc[first:last + 1]
            trimmed = _normalise_frame_table(sliced, frame_name=_frame_column(features.columns), time_name=time_name, source_first=first)
            feature_destination = parquet_dir / f"{video_id}_features.parquet"
            save_parquet_atomic(trimmed, feature_destination)
            if artifacts["landmarks"]:
                landmarks = load_parquet(artifacts["landmarks"])
                if len(landmarks) >= last + 1:
                    landmark_trimmed = _normalise_frame_table(landmarks.iloc[first:last + 1], frame_name=_frame_column(landmarks.columns), time_name=_time_column(landmarks.columns), source_first=first)
                    save_parquet_atomic(landmark_trimmed, parquet_dir / f"{video_id}_landmarks.parquet")
            video_destination = video_dir / f"{video_id}_skeleton.mp4"
            _write_video(video, video_destination, first, last, progress)
            source_times = times[first:last + 1] - times[first]
            annotation_document = _clip_annotations(
                artifacts["annotations"], first=first, last=last, new_times=source_times,
                new_video_id=video_id, new_session_id=segment_session,
            ) if artifacts["annotations"] else None
            if annotation_document is not None:
                annotation_destination = annotations_dir / f"{video_id}_annotations.json"
                save_json_atomic(annotation_document, annotation_destination)
                save_annotation_parquet(annotation_document, annotations_dir / f"{video_id}_annotations.parquet")
                save_json_atomic({"schema_version": "1.0", "source": "derived_from_annotations.json", "repetitions": build_rep_summary(annotation_document)}, annotations_dir / f"{video_id}_rep_summary.json")
            metadata = {}
            source_metadata = features_path.parent.parent / "metadata" / f"{source_stem}_metadata.json"
            if source_metadata.is_file():
                metadata = load_json(source_metadata)
            metadata.update({
                "session_id": segment_session,
                "video_id": video_id,
                "source_video_id": metadata.get("video_id", source_stem),
                "source_video_path": str(video),
                "trim_start_time_s": float(segment.start_s),
                "trim_end_time_s": float(segment.end_s),
                "source_first_frame": first,
                "source_last_frame": last,
                "trim_label": segment.label,
                "trim_type": "sub_video",
            })
            if metadata_overrides:
                metadata.update(metadata_overrides)
            save_json_atomic(metadata, metadata_dir / f"{video_id}_metadata.json")
            save_json_atomic({
                "version": 1,
                "sourceVideo": str(video),
                "sourceFeatures": str(features_path),
                "sourceAnnotation": str(artifacts["annotations"]) if artifacts["annotations"] else None,
                "sessionId": segment_session,
                "videoId": video_id,
                "sourceFirstFrame": first,
                "sourceLastFrame": last,
                "sourceStartTimeS": float(times[first]),
                "sourceEndTimeS": float(times[last]),
                "trimStartS": float(segment.start_s),
                "trimEndS": float(segment.end_s),
            }, temp_dir / "trim_manifest.json")
            output_dir.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temp_dir, output_dir)
            outputs.append(output_dir)
        except Exception:
            for path in sorted(temp_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            temp_dir.rmdir()
            raise
    return outputs


def trim_aligned_recordings(*, sources: list[dict], segments: list[TrimSegment],
                            output_root: str | Path, progress: Progress | None = None) -> list[Path]:
    """Trim several aligned cameras into matching sub-session folders.

    ``segments`` use aligned/session-relative seconds. Each source entry must
    contain ``video_path``, ``features_path``, and a mapping with ``offset`` and
    ``rate``. Every camera for a segment receives the same generated session ID.
    """
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    reserved: set[str] = set()
    for segment_index, segment in enumerate(segments, 1):
        session_id = next_session_id(root)
        while session_id in reserved:
            match = re.fullmatch(r"S(\d+)", session_id)
            session_id = f"S{(int(match.group(1)) + 1 if match else segment_index):03d}"
        reserved.add(session_id)
        for source_index, source in enumerate(sources):
            recording = source["recording"]
            mapping = source["mapping"]
            first_source_time = float(recording.times[0])
            start = (segment.start_s - float(mapping.offset)) / float(mapping.rate) - first_source_time
            end = (segment.end_s - float(mapping.offset)) / float(mapping.rate) - first_source_time
            if start < 0 or end <= start:
                raise ValueError(f"Aligned trim does not overlap {recording.label} for {segment.label or 'sub-video'}.")
            outputs.extend(trim_recording_artifacts(
                video_path=recording.video,
                features_path=recording.features,
                output_root=root,
                segments=[TrimSegment(start, end, segment.label)],
                session_id=session_id,
                annotation_json_path=source.get("annotation_json_path"),
                segment_number_start=segment_index,
                metadata_overrides={
                    "alignment_session_start_s": float(segment.start_s),
                    "alignment_session_end_s": float(segment.end_s),
                    "alignment_offset_seconds": float(mapping.offset),
                    "alignment_clock_rate": float(mapping.rate),
                    "alignment_camera_index": source_index,
                },
                progress=progress,
            ))
    for segment_index, segment in enumerate(segments, 1):
        session_id = sorted({path.parent.name for path in outputs})[segment_index - 1]
        segment_outputs = [path for path in outputs if path.parent.name == session_id]
        save_json_atomic({
            "version": 1,
            "trimType": "aligned_sub_session",
            "sessionId": session_id,
            "startSeconds": float(segment.start_s),
            "endSeconds": float(segment.end_s),
            "outputs": [str(path) for path in segment_outputs],
        }, root / session_id / "trim_session.json")
    return outputs


class TrimSubVideosDialog(QDialog):
    """Editable time-range table for creating one or more sub-sessions."""

    def __init__(self, *, video_path: str | Path, features_path: str | Path,
                 output_root: str | Path, parent=None, title="Trim 2 Sub Videos",
                 export_callback: Callable[[list[TrimSegment], Path, Progress], list[Path]] | None = None,
                 time_start: float = 0.0, time_end: float | None = None):
        super().__init__(parent)
        self.video_path = Path(video_path)
        self.features_path = Path(features_path)
        self.output_root = Path(output_root)
        self.export_callback = export_callback
        self.time_start = float(time_start)
        self.time_end = time_end
        self.setWindowTitle(title)
        self.resize(760, 430)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Create one or more sub-sessions from this recording. Each row becomes a new "
            "skeleton MP4 with matching feature rows and clipped annotations. Source files "
            "are never overwritten."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        form.addRow("Source video", QLabel(str(self.video_path)))
        self.output_label = QLabel(str(self.output_root))
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_label, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_output)
        output_row.addWidget(browse)
        form.addRow("Processed root", output_row)
        self.processed_inventory_label = QLabel()
        self.processed_inventory_label.setWordWrap(True)
        form.addRow("Current inventory", self.processed_inventory_label)
        layout.addLayout(form)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(("Label", "Start (s)", "End (s)"))
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        add = QPushButton("Add sub-video")
        add.clicked.connect(self.add_segment)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self.remove_segment)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        actions.button(QDialogButtonBox.StandardButton.Save).setText("Save and trim")
        actions.accepted.connect(self._save)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)
        self.refresh_processed_inventory()
        self.add_segment()

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Export sub-sessions to", str(self.output_root))
        if path:
            self.output_root = Path(path)
            self.output_label.setText(str(self.output_root))
            self.refresh_processed_inventory()

    def refresh_processed_inventory(self) -> None:
        inventory = processed_inventory(self.output_root)
        self.processed_inventory_label.setText(
            f"{inventory['sessionCount']} session folder(s), "
            f"{inventory['recordingCount']} recording folder(s); "
            f"next available session: {inventory['nextSessionId']}"
        )

    def add_segment(self) -> None:
        try:
            feature_rows = load_parquet(self.features_path)
            time_name = _time_column(feature_rows.columns)
            duration = float(feature_rows[time_name].iloc[-1] - feature_rows[time_name].iloc[0])
            default_start = self.time_start
            default_end = self.time_end if self.time_end is not None else default_start + duration
        except Exception:
            default_start = self.time_start
            default_end = self.time_end if self.time_end is not None else default_start + 1.0
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(f"Sub {row + 1}"))
        self.table.setItem(row, 1, QTableWidgetItem(f"{default_start:.3f}"))
        self.table.setItem(row, 2, QTableWidgetItem(f"{default_end:.3f}"))
        self.table.selectRow(row)

    def remove_segment(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def segments(self) -> list[TrimSegment]:
        segments = []
        for row in range(self.table.rowCount()):
            try:
                label = self.table.item(row, 0).text().strip()
                start = float(self.table.item(row, 1).text())
                end = float(self.table.item(row, 2).text())
                segments.append(TrimSegment(start, end, label))
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(f"Row {row + 1} needs a valid label, start, and end time.") from exc
        if not segments:
            raise ValueError("Add at least one sub-video range.")
        return segments

    def _save(self) -> None:
        try:
            segments = self.segments()
            progress = QProgressDialog("Preparing trim…", "Cancel", 0, 100, self)
            progress.setWindowTitle("Creating sub-sessions")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setAutoClose(False)
            progress.show()

            def report(fraction: float, message: str) -> None:
                progress.setValue(min(100, max(0, int(fraction * 100))))
                progress.setLabelText(message)
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                if progress.wasCanceled():
                    raise InterruptedError("Trim cancelled by the user.")

            if self.export_callback is not None:
                outputs = self.export_callback(segments, self.output_root, report)
            else:
                outputs = trim_recording_artifacts(
                    video_path=self.video_path,
                    features_path=self.features_path,
                    output_root=self.output_root,
                    segments=segments,
                    progress=report,
                )
            self.refresh_processed_inventory()
            progress.close()
        except InterruptedError:
            progress.close()
            self.status.setText("Trim cancelled. Existing source files were preserved.")
            return
        except Exception as exc:
            if "progress" in locals():
                progress.close()
            QMessageBox.warning(self, "Could not create sub-sessions", str(exc))
            return
        self.status.setText("Created:\n" + "\n".join(str(path) for path in outputs))
        QMessageBox.information(self, "Trim complete", f"Created {len(outputs)} new sub-session(s).\n\n" + "\n".join(str(path) for path in outputs))
        self.accept()
