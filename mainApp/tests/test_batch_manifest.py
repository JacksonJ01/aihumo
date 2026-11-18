from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from aihumo.batch_manifest import BatchManifest
from aihumo.resource_estimation import EstimateRange, ResourceEstimate, VideoResourceInfo
from aihumo.resource_estimation import InsufficientStorageError
from app.mode0_batch import BatchProcessingWorker


def _estimate(source: Path, destination: Path) -> ResourceEstimate:
    video = VideoResourceInfo(
        path=str(source.resolve()), size_bytes=12, width=640, height=480, fps=30.0,
        frame_count=300, duration_s=10.0, codec="mp4v", bitrate_bps=9.6,
        work_units=300.0,
    )
    categories = {
        "source_copies": EstimateRange(0, 0),
        "skeleton_mp4": EstimateRange(10, 20),
        "raw_landmarks_parquet": EstimateRange(5, 10),
        "feature_parquet": EstimateRange(5, 10),
        "annotations_and_quality": EstimateRange(1, 2),
        "graphs_and_visualizations": EstimateRange(1, 2),
    }
    return ResourceEstimate(
        profile="standard", videos=(video,), categories=categories,
        source_storage_bytes=12, final_output=EstimateRange(22, 44),
        temporary_overhead=EstimateRange(2, 4), peak_additional=EstimateRange(24, 48),
        processing_time_s=EstimateRange(9, 51), destination=str(destination),
        available_bytes=10_000, safety_margin_bytes=100,
        expected_remaining=EstimateRange(9_852, 9_876), warnings=(),
    )


def _job(source: Path, model: Path, output: Path) -> dict:
    return {
        "source_video": source,
        "model_path": model,
        "cfg": {"pose": {"model": "full"}},
        "identifiers": {
            "participant_id": "P001", "session_id": "S001",
            "video_id": "V001", "camera_id": "camera_01",
        },
        "optional_metadata": {"camera_angle": "Front"},
        "output_root": output,
        "processing_profile_name": "standard",
    }


def test_batch_manifest_tracks_recovery_state_and_outputs(tmp_path):
    source = tmp_path / "source.mp4"
    model = tmp_path / "model.task"
    source.write_bytes(b"source-video")
    model.write_bytes(b"model")
    output = tmp_path / "processed"
    manifest = BatchManifest.create(
        output_root=output,
        jobs=[_job(source, model, output)],
        profile="standard",
        estimate=_estimate(source, output),
    )

    loaded = BatchManifest.load(manifest.path)
    assert loaded.document["status"] == "pending"
    assert loaded.jobs[0]["job_id"] == "S001/V001"
    assert loaded.recoverable_job_indices() == [0]

    loaded.update_job(0, status="running", stage="pose_estimation", progress=0.4)
    loaded.update_job(0, stage="feature_extraction", progress=0.2, completed_stage="pose_estimation")
    assert loaded.jobs[0]["progress"] == 0.4
    assert loaded.jobs[0]["completed_stages"] == ["pose_estimation"]

    result = SimpleNamespace(
        output_dir=output / "S001" / "V001",
        landmarks_path=output / "landmarks.parquet",
        features_path=output / "features.parquet",
        processed_video_path=output / "skeleton.mp4",
        metadata_path=output / "metadata.json",
        feature_manifest_path=output / "features.json",
        quality_report_path=output / "quality.json",
        processing_state_path=output / "state.json",
        graph_manifest_path=None,
    )
    loaded.update_job(0, status="completed", stage="completed", progress=1.0, result=result)
    loaded.set_batch_status("completed")

    final = BatchManifest.load(manifest.path)
    assert final.document["status"] == "completed"
    assert final.jobs[0]["status"] == "completed"
    assert final.jobs[0]["validation"] == "passed"
    assert final.jobs[0]["outputs"]["features_path"].endswith("features.parquet")
    assert final.recoverable_job_indices() == []


def test_batch_manifest_preserves_failure_for_retry(tmp_path):
    source = tmp_path / "source.mp4"
    model = tmp_path / "model.task"
    source.write_bytes(b"source-video")
    model.write_bytes(b"model")
    output = tmp_path / "processed"
    manifest = BatchManifest.create(
        output_root=output,
        jobs=[_job(source, model, output)],
        profile="minimal",
        estimate=_estimate(source, output),
    )
    manifest.update_job(0, status="failed", stage="pose_estimation", progress=0.3, error="decode failed")
    manifest.set_batch_status("failed")

    recovered = BatchManifest.load(manifest.path)
    assert recovered.recoverable_job_indices() == [0]
    assert recovered.jobs[0]["error"] == "decode failed"
    assert recovered.jobs[0]["source"]["size_bytes"] == len(b"source-video")


def test_batch_pauses_before_next_job_when_projected_peak_crosses_reserve(
    qt_app, tmp_path, monkeypatch,
):
    source = tmp_path / "source.mp4"
    model = tmp_path / "model.task"
    source.write_bytes(b"source-video")
    model.write_bytes(b"model")
    output = tmp_path / "processed"
    job = _job(source, model, output)
    job["disk_safety_margin_bytes"] = 5_000
    manifest = BatchManifest.create(
        output_root=output, jobs=[job], profile="standard", estimate=_estimate(source, output),
    )

    class RejectingGuard:
        def __init__(self, *_args, **_kwargs):
            pass

        def check_projected(self, required_peak_bytes, stage):
            assert required_peak_bytes == 2_000
            assert stage == "S001/V001"
            raise InsufficientStorageError("projected storage crosses reserve")

    monkeypatch.setattr("app.mode0_batch.DiskSpaceGuard", RejectingGuard)
    monkeypatch.setattr(
        "app.mode0_batch.process_video",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("job must not start")),
    )
    messages = []
    worker = BatchProcessingWorker(
        [job], manifest_path=manifest.path, projected_peak_bytes=[2_000],
    )
    worker.paused.connect(messages.append)
    worker.run()

    recovered = BatchManifest.load(manifest.path)
    assert messages == ["projected storage crosses reserve"]
    assert recovered.document["status"] == "paused_storage"
    assert recovered.jobs[0]["status"] == "paused_storage"
    assert recovered.recoverable_job_indices() == [0]

