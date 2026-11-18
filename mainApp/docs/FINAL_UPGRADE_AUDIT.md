# AIHuMo Final Upgrade Audit

This audit maps the Final Codex Upgrade Specification to the repository as inspected before implementation. It deliberately separates working foundations from partial and missing behavior.

## Existing and preserved

- Modes 0–4 retain their current responsibilities. Mode 5 remains a future/model workspace and is not redefined by this upgrade.
- Mode 0 writes canonical landmark and feature Parquet files, metadata, quality reports, graph manifests, and a skeleton-overlay MP4.
- Raw landmark extraction supports cancellation and persistent checkpoint chunks.
- `processing_state.json` fingerprints source video, pose model, configuration, recording identity, stage, persisted frames, status, and errors.
- Completed jobs are validated before they are reused. Incompatible outputs are not overwritten automatically.
- Parquet and JSON writes use temporary files and atomic replacement.
- Fresh processing can render the skeleton video through a bounded background queue while pose extraction continues.
- Batch processing preserves completed videos when a later video fails or the user cancels.
- Batch progress is weighted by source frame count and displays observed current-video and batch ETA.
- Tracking produces pose-presence, confidence, target-status, occlusion, loss, and reacquisition measurements.
- Quality reports summarize missing pose/features, landmark visibility, and target-tracking status.
- Repetition detection already uses timestamp-aware smoothing, extrema, prominence, amplitude, autocorrelation, overlapping windows, unilateral signal candidates, and confidence thresholds.
- Rep detection writes a separate suggestion file and never overwrites human annotations.
- Mode 1 annotations remain the authoritative source of truth.
- Windows, macOS, and Linux build instructions/scripts exist, although only platform-local builds can be validated on their native operating systems.

## Partially implemented before this upgrade

- Progress had batch and current-video levels, but no explicit current-stage progress object or stage dashboard.
- Global processing percentages represented fixed pipeline regions, but stage durations were not learned from measured performance.
- Recovery was reliable at video level, but no persistent batch manifest summarized every job and output.
- Storage safety depended on normal write failures; there was no preflight capacity model or periodic low-space guard.
- Quality reports contained aggregate missingness and tracking status, but not timestamped local anomaly intervals with affected landmarks and reasons.
- Rep proposals existed, but activity, set, phase, and cautious form-review proposals did not share a versioned suggestion contract.
- Mode 1 could create rep suggestions for a selected segment, but Modes 1–4 did not provide a unified suggestion review overlay.
- MediaPipe model path and metadata existed, but the UI did not yet provide a complete Lite/Full/Heavy model-management workflow.

## Missing before this upgrade

- Output-profile presets with profile-specific estimates and behavior.
- Per-category output-size ranges, temporary peak estimates, destination capacity, safety margin, and expected remaining storage.
- Persistent local performance measurements used to improve future estimates.
- Structured stage progress and a three-level batch/video/stage dashboard.
- Periodic free-space checks that stop safely before unsafe writes.
- A batch-level persistent recovery manifest and explicit failed-video retry workflow.
- A five-layer suggestion data contract with pending/accepted/edited/rejected review states.
- Multiscale activity, set, and phase proposal generation.
- Timestamped Hampel/MAD/derivative/limb-length quality anomalies.
- Proposed-boundary overlays in Modes 1–3 and landmark warning overlays in Mode 4.
- GitHub Release update checking and separate pose-model update management.
- A formal pose-estimator adapter interface.
- Contribution-package export/validation and embedding exploration.

## Implementation order

1. Phase 1A: pure preflight/profile/storage estimator and tests.
2. Phase 1A: preflight UI and profile selection in single and batch Mode 0.
3. Phase 1A: structured stage progress, disk guards, batch manifest, and local performance history.
4. Phase 1B: local tracking anomalies and unified suggestion contract.
5. Phase 1B: activity/set/rep/phase suggestion generation and review integration.
6. Distribution and research phases only after Phase 1 acceptance tests pass.
