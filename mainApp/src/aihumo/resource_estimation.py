"""Mode 0 preflight estimation, profiles, and disk-space safety.

The estimator is intentionally independent of PyQt6. Estimates are ranges and
keep source storage, final output, and temporary peak overhead separate.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
import shutil
from typing import Any, Callable, Iterable

from .pose import inspect_video


GIB = 1024 ** 3
MIB = 1024 ** 2


@dataclass(frozen=True)
class ProcessingProfile:
    id: str
    title: str
    skeleton_overlay: bool
    graph_images: bool
    detailed_diagnostics: bool
    raw_landmarks: bool = True
    engineered_features: bool = True
    annotation_suggestions: bool = True


PROFILES: dict[str, ProcessingProfile] = {
    "minimal": ProcessingProfile("minimal", "Minimal", False, False, False),
    "standard": ProcessingProfile("standard", "Standard", True, True, False),
    "research": ProcessingProfile("research", "Research", True, True, True),
}


def processing_profile(value: str | ProcessingProfile) -> ProcessingProfile:
    if isinstance(value, ProcessingProfile):
        return value
    key = str(value).strip().casefold()
    if key not in PROFILES:
        raise ValueError(f"Unknown processing profile: {value!r}")
    return PROFILES[key]


def apply_processing_profile(cfg: dict[str, Any], profile: str | ProcessingProfile) -> dict[str, Any]:
    """Return a fingerprintable configuration without mutating the caller's data."""
    selected = processing_profile(profile)
    configured = deepcopy(cfg)
    # Standard is the historical behavior. Leaving its configuration byte-for-
    # byte equivalent preserves compatibility with existing recovery states.
    if selected.id == "standard":
        return configured
    configured["processing_profile"] = asdict(selected)
    graphs = configured.setdefault("graphs", {})
    if selected.id == "minimal":
        graphs["enabled"] = False
        graphs["export_images"] = False
    elif selected.id == "research":
        graphs["enabled"] = True
        graphs["export_images"] = True
    return configured


@dataclass(frozen=True)
class EstimateRange:
    low: int
    high: int

    def __post_init__(self) -> None:
        # Most byte/time estimates are non-negative, but projected remaining
        # storage intentionally becomes negative when the destination is unsafe.
        if self.high < self.low:
            raise ValueError("Estimate ranges must be ordered.")

    def __add__(self, other: "EstimateRange") -> "EstimateRange":
        return EstimateRange(self.low + other.low, self.high + other.high)


@dataclass(frozen=True)
class VideoResourceInfo:
    path: str
    size_bytes: int
    width: int
    height: int
    fps: float
    frame_count: int
    duration_s: float
    codec: str | None
    bitrate_bps: float
    work_units: float


@dataclass(frozen=True)
class ResourceEstimate:
    profile: str
    videos: tuple[VideoResourceInfo, ...]
    categories: dict[str, EstimateRange]
    source_storage_bytes: int
    final_output: EstimateRange
    temporary_overhead: EstimateRange
    peak_additional: EstimateRange
    processing_time_s: EstimateRange
    destination: str
    available_bytes: int
    safety_margin_bytes: int
    expected_remaining: EstimateRange
    warnings: tuple[str, ...]

    @property
    def total_duration_s(self) -> float:
        return float(sum(video.duration_s for video in self.videos))

    @property
    def total_frames(self) -> int:
        return int(sum(video.frame_count for video in self.videos))

    @property
    def total_work_units(self) -> float:
        return float(sum(video.work_units for video in self.videos))

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "profile": self.profile,
            "videos": [asdict(video) for video in self.videos],
            "categories": {name: asdict(value) for name, value in self.categories.items()},
            "source_storage_bytes": self.source_storage_bytes,
            "final_output": asdict(self.final_output),
            "temporary_overhead": asdict(self.temporary_overhead),
            "peak_additional": asdict(self.peak_additional),
            "processing_time_s": asdict(self.processing_time_s),
            "destination": self.destination,
            "available_bytes": self.available_bytes,
            "safety_margin_bytes": self.safety_margin_bytes,
            "expected_remaining": asdict(self.expected_remaining),
            "warnings": list(self.warnings),
        }


def _existing_volume_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve(strict=False)
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    if not candidate.exists():
        raise FileNotFoundError(f"No existing destination ancestor for {path}")
    return candidate


def inspect_resource_video(
    path: str | Path,
    *,
    inspector: Callable[[str | Path], dict[str, Any]] = inspect_video,
) -> VideoResourceInfo:
    source = Path(path).expanduser().resolve(strict=True)
    info = inspector(source)
    size = int(source.stat().st_size)
    duration = float(info["duration_s"])
    bitrate = size * 8 / max(duration, 1e-9)
    pixel_factor = max(0.35, float(info["width"] * info["height"]) / (1280 * 720))
    # Work is dominated by per-frame pose estimation, with a smaller pixel
    # decode/render component. It is intentionally relative, not a time unit.
    work = float(info["frame_count"]) * (0.80 + 0.20 * pixel_factor)
    return VideoResourceInfo(
        path=str(source), size_bytes=size, width=int(info["width"]), height=int(info["height"]),
        fps=float(info["source_fps"]), frame_count=int(info["frame_count"]), duration_s=duration,
        codec=info.get("codec"), bitrate_bps=bitrate, work_units=work,
    )


def _sum_ranges(values: Iterable[EstimateRange]) -> EstimateRange:
    result = EstimateRange(0, 0)
    for value in values:
        result += value
    return result


def _video_categories(video: VideoResourceInfo, profile: ProcessingProfile, feature_count: int) -> dict[str, EstimateRange]:
    frames = video.frame_count
    pixels_per_second = video.width * video.height * video.fps
    # Overlay estimates combine observed source bitrate with a resolution/FPS
    # floor. The range accounts for motion, codec, and encoder differences.
    overlay_floor_bps = pixels_per_second * 0.045
    overlay_mid_bps = max(video.bitrate_bps * 0.72, overlay_floor_bps)
    skeleton = EstimateRange(
        int(video.duration_s * overlay_mid_bps / 8 * 0.70),
        int(video.duration_s * overlay_mid_bps / 8 * 1.75),
    ) if profile.skeleton_overlay else EstimateRange(0, 0)

    # Parquet is columnar and compressed; ranges are deliberately broad. Raw
    # landmark rows contain image/world points, confidence, tracking, and IDs.
    landmarks = EstimateRange(int(frames * 420), int(frames * 1500))
    raw_feature_bytes = frames * max(1, feature_count) * 8
    features = EstimateRange(int(raw_feature_bytes * 0.16), int(raw_feature_bytes * 0.52))
    metadata = EstimateRange(48 * 1024, 512 * 1024 + int(frames * 4))
    if profile.detailed_diagnostics:
        metadata = EstimateRange(metadata.low * 2, metadata.high * 4)
    if profile.graph_images:
        graph_count = 10 if profile.detailed_diagnostics else 4
        graphs = EstimateRange(graph_count * 180 * 1024, graph_count * 1100 * 1024)
    else:
        graphs = EstimateRange(0, 0)
    suggestions = EstimateRange(16 * 1024, max(96 * 1024, int(frames * 16)))
    return {
        "source_copies": EstimateRange(0, 0),
        "skeleton_mp4": skeleton,
        "raw_landmarks_parquet": landmarks,
        "feature_parquet": features,
        "annotations_and_quality": metadata + suggestions,
        "graphs_and_visualizations": graphs,
    }


def estimate_video_peak_bytes(
    video: VideoResourceInfo,
    profile: str | ProcessingProfile,
    feature_count: int = 450,
) -> int:
    """Return a conservative peak-new-storage estimate for one video.

    This is used at batch boundaries. It intentionally includes the final
    artifacts plus atomic/checkpoint overhead so a job is not started when it
    is projected to consume the user's reserved free space.
    """
    categories = _video_categories(video, processing_profile(profile), feature_count)
    final = _sum_ranges(categories.values())
    parquet_high = categories["raw_landmarks_parquet"].high + categories["feature_parquet"].high
    temporary_high = int(parquet_high * 1.15 + categories["skeleton_mp4"].high * 0.12)
    return final.high + temporary_high


def estimate_processing_resources(
    video_paths: Iterable[str | Path],
    destination: str | Path,
    *,
    profile: str | ProcessingProfile = "standard",
    feature_count: int = 450,
    safety_margin_bytes: int | None = None,
    observed_processing_fps: EstimateRange | None = None,
    inspector: Callable[[str | Path], dict[str, Any]] = inspect_video,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> ResourceEstimate:
    selected = processing_profile(profile)
    videos = tuple(inspect_resource_video(path, inspector=inspector) for path in video_paths)
    if not videos:
        raise ValueError("Preflight requires at least one source video.")
    per_video = [_video_categories(video, selected, feature_count) for video in videos]
    categories = {
        name: _sum_ranges(items[name] for items in per_video)
        for name in per_video[0]
    }
    final_output = _sum_ranges(categories.values())
    parquet_high = categories["raw_landmarks_parquet"].high + categories["feature_parquet"].high
    # Temporary overhead includes checkpoint chunks, atomic Parquet replacement,
    # and encoder staging. Skeleton staging is not counted twice as both a temp
    # and final file; only additional overlap/atomic overhead is represented.
    temporary = EstimateRange(
        int(parquet_high * 0.20),
        int(parquet_high * 1.15 + categories["skeleton_mp4"].high * 0.12),
    )
    peak = EstimateRange(final_output.low + temporary.low, final_output.high + temporary.high)

    fps_range = observed_processing_fps or EstimateRange(8, 32)
    total_frames = sum(video.frame_count for video in videos)
    time_range = EstimateRange(
        int(total_frames / max(1, fps_range.high) * 0.90),
        int(total_frames / max(1, fps_range.low) * 1.35),
    )
    volume_path = _existing_volume_path(destination)
    usage = disk_usage(volume_path)
    available = int(usage.free)
    margin = int(safety_margin_bytes if safety_margin_bytes is not None else max(2 * GIB, available * 0.05))
    remaining = EstimateRange(
        available - peak.high - margin,
        available - peak.low - margin,
    )
    warnings: list[str] = []
    if available < peak.high + margin:
        warnings.append("Available destination storage may be insufficient for the high estimate and safety margin.")
    elif available < peak.high * 1.25 + margin:
        warnings.append("Destination storage is close to the estimated peak requirement.")
    if any(video.fps <= 15.5 for video in videos):
        warnings.append("Low-frame-rate input may reduce repetition and phase boundary precision.")
    if selected.skeleton_overlay and categories["skeleton_mp4"].high > sum(v.size_bytes for v in videos) * 1.2:
        warnings.append("Skeleton-overlay output may exceed source size because encoder and motion complexity differ.")
    return ResourceEstimate(
        profile=selected.id,
        videos=videos,
        categories=categories,
        source_storage_bytes=sum(video.size_bytes for video in videos),
        final_output=final_output,
        temporary_overhead=temporary,
        peak_additional=peak,
        processing_time_s=time_range,
        destination=str(Path(destination).expanduser().resolve(strict=False)),
        available_bytes=available,
        safety_margin_bytes=margin,
        expected_remaining=remaining,
        warnings=tuple(warnings),
    )


class InsufficientStorageError(OSError):
    pass


class DiskSpaceGuard:
    """Periodic low-space guard for the destination volume."""

    def __init__(self, destination: str | Path, *, minimum_free_bytes: int, disk_usage=shutil.disk_usage):
        self.destination = _existing_volume_path(destination)
        self.minimum_free_bytes = max(0, int(minimum_free_bytes))
        self._disk_usage = disk_usage

    def available_bytes(self) -> int:
        return int(self._disk_usage(self.destination).free)

    def check(self, stage: str = "processing") -> int:
        available = self.available_bytes()
        if available < self.minimum_free_bytes:
            raise InsufficientStorageError(
                f"Processing paused before {stage}: destination has {available / GIB:.2f} GiB free, "
                f"below the {self.minimum_free_bytes / GIB:.2f} GiB safety margin. "
                "Completed outputs and recovery checkpoints were preserved."
            )
        return available

    def check_projected(self, required_peak_bytes: int, stage: str = "the next video") -> int:
        """Refuse a new unit of work before it could cross the free-space reserve."""
        available = self.available_bytes()
        projected = max(0, int(required_peak_bytes))
        required = self.minimum_free_bytes + projected
        if available < required:
            raise InsufficientStorageError(
                f"Batch paused before {stage}: {available / GIB:.2f} GiB is available, but the "
                f"video may need up to {projected / GIB:.2f} GiB while preserving the configured "
                f"{self.minimum_free_bytes / GIB:.2f} GiB reserve. Completed outputs and recovery "
                "checkpoints were preserved; free storage or choose another destination, then resume."
            )
        return available
