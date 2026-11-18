"""Persistent, atomic recovery manifest for Mode 0 batches.

The manifest coordinates video-level recovery.  Frame-level landmark resume
continues to be owned by each video's ``processing_state.json``; this document
never claims that an MP4 encoder can resume in the middle of a file.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .metadata import utc_now_iso
from .processing_state import fingerprint_file, stable_json_hash
from .resource_estimation import ResourceEstimate
from .storage import load_json, save_json_atomic


BATCH_MANIFEST_SCHEMA_VERSION = "1.0"
RECOVERABLE_JOB_STATES = {"pending", "running", "failed", "cancelled", "interrupted", "paused_storage"}


def _serializable_job(job: dict[str, Any], index: int) -> dict[str, Any]:
    identifiers = {key: str(value) for key, value in dict(job["identifiers"]).items()}
    source = Path(job["source_video"]).expanduser().resolve(strict=True)
    model = Path(job["model_path"]).expanduser().resolve(strict=True)
    output_root = Path(job["output_root"]).expanduser().resolve(strict=False)
    session_id = identifiers["session_id"]
    video_id = identifiers["video_id"]
    output_dir = output_root / session_id / video_id
    return {
        "index": index,
        "job_id": f"{session_id}/{video_id}",
        "status": "pending",
        "stage": "queued",
        "progress": 0.0,
        "completed_stages": [],
        "source": fingerprint_file(source, include_hash=False),
        "model": fingerprint_file(model, include_hash=False),
        "config_fingerprint": stable_json_hash(job["cfg"]),
        "identifiers": identifiers,
        "optional_metadata": deepcopy(dict(job.get("optional_metadata", {}))),
        "processing_profile": str(job.get("processing_profile_name", "standard")),
        "output_dir": str(output_dir),
        "outputs": {},
        "validation": None,
        "error": None,
        "started_at": None,
        "completed_at": None,
        "updated_at": utc_now_iso(),
    }


@dataclass
class BatchManifest:
    path: Path
    document: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        output_root: str | Path,
        jobs: Iterable[dict[str, Any]],
        profile: str,
        estimate: ResourceEstimate,
    ) -> "BatchManifest":
        root = Path(output_root).expanduser().resolve(strict=False)
        batch_id = f"{utc_now_iso().replace(':', '').replace('-', '')}_{uuid4().hex[:8]}"
        path = root / ".aihumo_batches" / f"batch_{batch_id}.json"
        serialized_jobs = [_serializable_job(job, index) for index, job in enumerate(jobs)]
        now = utc_now_iso()
        document = {
            "schema_version": BATCH_MANIFEST_SCHEMA_VERSION,
            "batch_id": batch_id,
            "status": "pending",
            "profile": str(profile),
            "destination": str(root),
            "created_at": now,
            "updated_at": now,
            "resource_estimate": estimate.to_document(),
            "jobs": serialized_jobs,
        }
        manifest = cls(path=path, document=document)
        manifest.save()
        return manifest

    @classmethod
    def load(cls, path: str | Path) -> "BatchManifest":
        manifest_path = Path(path).expanduser().resolve(strict=True)
        document = load_json(manifest_path)
        if not isinstance(document, dict):
            raise ValueError("Batch manifest must be a JSON object.")
        if document.get("schema_version") != BATCH_MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported batch manifest schema: {document.get('schema_version')}"
            )
        jobs = document.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise ValueError("Batch manifest must contain at least one job.")
        return cls(path=manifest_path, document=document)

    def save(self) -> None:
        self.document["updated_at"] = utc_now_iso()
        save_json_atomic(self.document, self.path)

    @property
    def jobs(self) -> list[dict[str, Any]]:
        return self.document["jobs"]

    def set_batch_status(self, status: str) -> None:
        self.document["status"] = str(status)
        self.save()

    def update_job(
        self,
        index: int,
        *,
        status: str | None = None,
        stage: str | None = None,
        progress: float | None = None,
        completed_stage: str | None = None,
        result: Any | None = None,
        error: str | None = None,
    ) -> None:
        job = self.jobs[index]
        now = utc_now_iso()
        if status is not None:
            job["status"] = str(status)
            if status == "running" and job.get("started_at") is None:
                job["started_at"] = now
            if status == "completed":
                job["completed_at"] = now
        if stage is not None:
            job["stage"] = str(stage)
        if progress is not None:
            job["progress"] = max(float(job.get("progress", 0.0)), min(1.0, float(progress)))
        if completed_stage:
            completed = job.setdefault("completed_stages", [])
            if completed_stage not in completed:
                completed.append(completed_stage)
        if result is not None:
            job["outputs"] = {
                key: str(getattr(result, key))
                for key in (
                    "output_dir", "landmarks_path", "features_path", "processed_video_path",
                    "metadata_path", "feature_manifest_path", "quality_report_path",
                    "processing_state_path", "graph_manifest_path",
                    "annotation_suggestions_path", "processing_performance_path",
                )
                if getattr(result, key, None) is not None
            }
            job["validation"] = "passed"
            job["error"] = None
        elif error is not None:
            job["error"] = str(error)
        job["updated_at"] = now
        self.save()

    def recoverable_job_indices(self) -> list[int]:
        """Return jobs safe to retry using their per-video recovery states."""
        return [
            index for index, job in enumerate(self.jobs)
            if str(job.get("status", "pending")) in RECOVERABLE_JOB_STATES
        ]

