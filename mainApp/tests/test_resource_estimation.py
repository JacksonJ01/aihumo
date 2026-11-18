from collections import namedtuple
from pathlib import Path

import pytest

from aihumo.resource_estimation import (
    DiskSpaceGuard, EstimateRange, GIB, InsufficientStorageError,
    apply_processing_profile, estimate_processing_resources, estimate_video_peak_bytes,
    processing_profile,
)


Disk = namedtuple("Disk", "total used free")


def fake_inspector(_path):
    return {
        "width": 1920, "height": 1080, "source_fps": 30.0,
        "frame_count": 1800, "duration_s": 60.0, "codec": "h264",
    }


def make_video(tmp_path: Path, name: str, size: int = 12_000_000) -> Path:
    path = tmp_path / name
    path.write_bytes(b"x" * size)
    return path


def test_profiles_preserve_standard_and_change_only_requested_outputs():
    cfg = {"graphs": {"enabled": True, "export_images": True}, "pose": {"model": "full"}}
    standard = apply_processing_profile(cfg, "standard")
    minimal = apply_processing_profile(cfg, "minimal")
    research = apply_processing_profile(cfg, "research")
    assert cfg == {"graphs": {"enabled": True, "export_images": True}, "pose": {"model": "full"}}
    assert processing_profile("Standard").skeleton_overlay
    assert not processing_profile("minimal").skeleton_overlay
    assert standard["graphs"]["enabled"]
    assert "processing_profile" not in standard
    assert not minimal["graphs"]["enabled"]
    assert research["processing_profile"]["detailed_diagnostics"]


def test_preflight_separates_source_final_temp_and_peak(tmp_path):
    videos = [make_video(tmp_path, "one.mp4"), make_video(tmp_path, "two.mp4", 8_000_000)]
    estimate = estimate_processing_resources(
        videos, tmp_path / "future" / "processed", profile="standard", inspector=fake_inspector,
        disk_usage=lambda _path: Disk(100 * GIB, 20 * GIB, 80 * GIB),
        safety_margin_bytes=2 * GIB,
    )
    assert len(estimate.videos) == 2 and estimate.total_duration_s == 120
    assert estimate.source_storage_bytes == 20_000_000
    assert estimate.categories["source_copies"] == EstimateRange(0, 0)
    assert estimate.categories["skeleton_mp4"].high > estimate.categories["skeleton_mp4"].low > 0
    assert estimate.final_output.high < estimate.peak_additional.high
    assert estimate.temporary_overhead.high > 0
    assert estimate.expected_remaining.low > 0
    assert estimate.processing_time_s.low < estimate.processing_time_s.high
    assert estimate.total_work_units > estimate.total_frames


def test_minimal_profile_removes_skeleton_and_graph_estimates(tmp_path):
    video = make_video(tmp_path, "one.mp4")
    estimate = estimate_processing_resources(
        [video], tmp_path, profile="minimal", inspector=fake_inspector,
        disk_usage=lambda _path: Disk(20 * GIB, 2 * GIB, 18 * GIB), safety_margin_bytes=GIB,
    )
    assert estimate.categories["skeleton_mp4"] == EstimateRange(0, 0)
    assert estimate.categories["graphs_and_visualizations"] == EstimateRange(0, 0)
    assert estimate.categories["feature_parquet"].high > 0


def test_preflight_warns_and_guard_stops_before_low_space(tmp_path):
    video = make_video(tmp_path, "one.mp4")
    estimate = estimate_processing_resources(
        [video], tmp_path, profile="research", inspector=fake_inspector,
        disk_usage=lambda _path: Disk(2 * GIB, int(1.9 * GIB), int(0.1 * GIB)),
        safety_margin_bytes=GIB,
    )
    assert estimate.warnings and estimate.expected_remaining.low < 0
    guard = DiskSpaceGuard(tmp_path, minimum_free_bytes=GIB,
                           disk_usage=lambda _path: Disk(2 * GIB, int(1.9 * GIB), int(0.1 * GIB)))
    with pytest.raises(InsufficientStorageError, match="preserved"):
        guard.check("Parquet export")


def test_batch_boundary_guard_preserves_user_reserve_before_next_video(tmp_path):
    video = make_video(tmp_path, "next.mp4")
    estimate = estimate_processing_resources(
        [video], tmp_path, profile="standard", inspector=fake_inspector,
        disk_usage=lambda _path: Disk(20 * GIB, 10 * GIB, 10 * GIB),
        safety_margin_bytes=4 * GIB,
    )
    peak = estimate_video_peak_bytes(estimate.videos[0], "standard")
    guard = DiskSpaceGuard(
        tmp_path,
        minimum_free_bytes=4 * GIB,
        disk_usage=lambda _path: Disk(20 * GIB, 16 * GIB, 4 * GIB + peak - 1),
    )
    with pytest.raises(InsufficientStorageError, match="Batch paused before S002/V002"):
        guard.check_projected(peak, "S002/V002")


def test_preflight_rejects_empty_or_unknown_profile(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        estimate_processing_resources([], tmp_path)
    with pytest.raises(ValueError, match="Unknown"):
        processing_profile("maximum")
