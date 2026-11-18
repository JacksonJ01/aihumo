"""Local, technical-only Mode 0 processing measurements."""
from __future__ import annotations

from pathlib import Path
import statistics
import time
from typing import Any, Iterable

from .metadata import utc_now_iso
from .resource_estimation import EstimateRange
from .storage import load_json, save_json_atomic


PERFORMANCE_SCHEMA_VERSION = "1.0"


def _path_size(path: Path) -> int:
    try:
        if path.is_file():
            return int(path.stat().st_size)
        if path.is_dir():
            return int(sum(item.stat().st_size for item in path.rglob("*") if item.is_file()))
    except OSError:
        return 0
    return 0


class ProcessingPerformanceTracker:
    """Measure stage time and output sizes without storing exercise labels."""

    def __init__(self, *, temp_path: str | Path):
        self.started = time.monotonic()
        self.active_stage: str | None = None
        self.active_stage_started = self.started
        self.stage_durations: dict[str, float] = {}
        self.pose_fps_samples: list[float] = []
        self.temp_path = Path(temp_path)
        self.peak_temporary_bytes = 0
        self._last_temp_measurement = 0.0

    def observe(self, stage: str, *, throughput_fps: float | None = None) -> None:
        now = time.monotonic()
        if self.active_stage is None:
            self.active_stage = stage
            self.active_stage_started = now
        elif stage != self.active_stage:
            self.stage_durations[self.active_stage] = (
                self.stage_durations.get(self.active_stage, 0.0)
                + now - self.active_stage_started
            )
            self.active_stage = stage
            self.active_stage_started = now
        if throughput_fps is not None and throughput_fps > 0:
            self.pose_fps_samples.append(float(throughput_fps))
        if now - self._last_temp_measurement >= 2.0:
            self.peak_temporary_bytes = max(self.peak_temporary_bytes, _path_size(self.temp_path))
            self._last_temp_measurement = now

    def finish(
        self,
        *,
        performance_path: str | Path,
        history_path: str | Path,
        video_info: dict[str, Any],
        source_video: str | Path,
        model_path: str | Path,
        profile: str,
        output_paths: Iterable[str | Path | None],
    ) -> dict[str, Any]:
        now = time.monotonic()
        if self.active_stage is not None:
            self.stage_durations[self.active_stage] = (
                self.stage_durations.get(self.active_stage, 0.0)
                + now - self.active_stage_started
            )
        self.peak_temporary_bytes = max(self.peak_temporary_bytes, _path_size(self.temp_path))
        output_sizes = {
            str(Path(path).name): _path_size(Path(path))
            for path in output_paths if path is not None and Path(path).exists()
        }
        total_s = max(0.0, now - self.started)
        frame_count = int(video_info.get("frame_count", 0))
        document = {
            "schema_version": PERFORMANCE_SCHEMA_VERSION,
            "recorded_at": utc_now_iso(),
            "input": {
                "source_name": Path(source_video).name,
                "duration_s": float(video_info.get("duration_s", 0.0)),
                "frame_count": frame_count,
                "width": int(video_info.get("width", 0)),
                "height": int(video_info.get("height", 0)),
                "source_fps": float(video_info.get("source_fps", 0.0)),
                "source_size_bytes": _path_size(Path(source_video)),
            },
            "pose_model": Path(model_path).name,
            "processing_profile": str(profile),
            "pose_estimation_fps": (
                statistics.median(self.pose_fps_samples) if self.pose_fps_samples else None
            ),
            "effective_total_fps": frame_count / total_s if total_s > 0 else None,
            "stage_durations_s": {
                stage: round(duration, 6) for stage, duration in self.stage_durations.items()
            },
            "total_processing_s": round(total_s, 6),
            "output_sizes_bytes": output_sizes,
            "final_output_bytes": int(sum(output_sizes.values())),
            "peak_temporary_bytes": int(self.peak_temporary_bytes),
        }
        save_json_atomic(document, performance_path)
        _append_history(document, history_path)
        return document


def _append_history(document: dict[str, Any], history_path: str | Path) -> None:
    path = Path(history_path)
    try:
        existing = load_json(path) if path.exists() else {
            "schema_version": PERFORMANCE_SCHEMA_VERSION,
            "records": [],
        }
        records = existing.setdefault("records", [])
        # History is deliberately technical-only and excludes full source
        # paths, participant IDs, annotations, and exercise labels.
        records.append({
            "recorded_at": document["recorded_at"],
            "duration_s": document["input"]["duration_s"],
            "frame_count": document["input"]["frame_count"],
            "width": document["input"]["width"],
            "height": document["input"]["height"],
            "source_fps": document["input"]["source_fps"],
            "pose_model": document["pose_model"],
            "processing_profile": document["processing_profile"],
            "pose_estimation_fps": document["pose_estimation_fps"],
            "effective_total_fps": document["effective_total_fps"],
            "stage_durations_s": document["stage_durations_s"],
            "total_processing_s": document["total_processing_s"],
            "final_output_bytes": document["final_output_bytes"],
            "peak_temporary_bytes": document["peak_temporary_bytes"],
        })
        existing["records"] = records[-500:]
        save_json_atomic(existing, path)
    except (OSError, TypeError, ValueError):
        # A completed video remains valid if optional local analytics cannot be
        # appended. The per-video performance document was already attempted.
        return


def observed_processing_fps(history_path: str | Path, *, profile: str | None = None) -> EstimateRange | None:
    path = Path(history_path)
    if not path.is_file():
        return None
    try:
        records = load_json(path).get("records", [])
    except (OSError, TypeError, ValueError):
        return None
    values = sorted(
        float(record["effective_total_fps"])
        for record in records
        if record.get("effective_total_fps")
        and (profile is None or record.get("processing_profile") == profile)
    )
    if not values:
        return None
    low_index = max(0, int(len(values) * 0.10) - 1)
    high_index = min(len(values) - 1, int(len(values) * 0.90))
    return EstimateRange(
        max(1, int(values[low_index] * 0.85)),
        max(1, int(values[high_index] * 1.15)),
    )

